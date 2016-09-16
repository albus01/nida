"""
author: shawnsha@tencent.com
date: 2016.08.16

A buffer wrapper for file or socket I/O.
"""
import collections
import socket
import errno
import numbers
import time

from nida.ioevent import IOLoop
from nida.log import app_log, gen_log
from nida import  context_manager
from nida.context_manager import NullStackContext

class StreamClosedError(IOError):
    pass

class BaseIOStream(object):
    """
    Base class for socket or file I/O.
    """
    def __init__(self, max_read_buf=134217728,
                 read_chunk_size=4096, write_chunk_size=128 * 1024):
        self.max_read_buf = max_read_buf
        self.read_chunk_size = read_chunk_size
        self.write_chunk_size = write_chunk_size
        self.ioloop = IOLoop.current()
        self._read_buf = collections.deque()
        self._write_buf = collections.deque()
        self._read_buf_size = 0
        #read some bytes or read until a delimiter occur
        self._read_delimiter = None
        self._read_bytes = None
        self._read_until_close = False

        self._read_callback = None
        self._write_callback = None
        self._connect_callback = None
        self._close_callback = None
        #for socket 
        self._connecting = False

        self._state = None
        self._closed = False

    def close_fd(self):
        raise NotImplementedError()

    def check_close(self):
        if self._closed:
            raise StreamClosedError("stream has closed")

    def fileno(self):
        raise NotImplementedError()

    def set_close_callback(self, callback):
        self._close_callback = context_manager.wrap(callback)

    def close(self):
        if not self._closed:
            if self._read_until_close:
                callback = self._read_callback
                self._read_callback = None
                self._read_until_close = False
                self._run_callback(callback,
                                   self._consume(self._read_buf_size))
            if self._close_callback:
                callback = self._close_callback
                self._close_callback = None
                self._run_callback(callback)

            if self._state is not None:
                self.ioloop.remove_handler(self.fileno())
                self._state = None
            self._closed = True
            self.close_fd()

    def closed(self):
        return self._closed

    def _add_io_state(self, event):
        if self._closed:
            return
        if self._state is None:
            self._state = self.ioloop.ERROR | event
            with NullStackContext():
                #print 'add io state:%s' % self.fileno()
                self.ioloop.add_handler(self.fileno(), self.handle_events, self._state)
        elif not self._state & event:
            self._state = event | self._state
            self.ioloop.update_handler(self.fileno(), self._state)


    #read 
    def _handle_read(self):
        while True:
            try:
                res = self._read_to_buf()
            except:
                print 'handle read except'
                self.close()
                return

            if res == 0:
                break
            else:
                #if read has completed then return,else loop.
                if self._read_from_buf():
                    return


    def _read_to_buf(self):
        try:
            chunk = self.read_from_fd()
        except socket.errno, e:
            if e.arg[0] in (errno.EAGAIN, errno.EWOULDBLOCK):
                return None
            self.close()
            raise
        if chunk is None:
            return 0
        self._read_buf.append(chunk)
        self._read_buf_size += len(chunk)
        if self._read_buf_size > self.max_read_buf:
            gen_log.error("Read buffer has overflow")
            self.close()
            raise IOError("Read buffer has overflow")
        return len(chunk)


    def _read_from_buf(self):
        if self._read_delimiter:
            _merge_pre_bysize(self._read_buf, self.max_read_buf)
            loc = self._read_buf[0].find(self._read_delimiter)
            if loc != -1:
                callback = self._read_callback
                delimi_len = len(self._read_delimiter)
                self._read_callback = None
                self._read_delimiter = None
                self._run_callback(callback, self._consume(loc + delimi_len))
                return True
        elif self._read_bytes:
            if self._read_buf_size >= self._read_bytes:
                num_readed = self._read_bytes
                callback = self._read_callback
                self._read_bytes = None
                self._read_callback = None
                self._run_callback(callback, self._consume(num_readed))
                return True
        #read_until_close or end?
        elif self._read_buf_size > self.max_read_buf:
            gen_log.warning("read buf overflow, close fileno:%d" %
                            self.fileno())
            self.close()
            return True

        return False

    def read_from_fd(self):
        raise NotImplementedError()

    def _run_callback(self, callback, *args, **kwargs):
        def wrapper():
            try:
                callback(*args, **kwargs)
            except:
                gen_log.error("Uncatched Exception in:%s, close connection" %
                              callback, exc_info = True)
                self.close()
                raise

        with NullStackContext():
            self.ioloop.add_callback(wrapper)

    def _consume(self, size):
        _merge_pre_bysize(self._read_buf, size)
        self._read_buf_size -= size
        return self._read_buf.popleft()
    #end read

    #write process
    def write(self, data, callback = None):
        assert isinstance(data, bytes)
        self.check_close()
        self._write_buf.append(data)
        if callback is not None:
            self._write_callback = context_manager.wrap(callback)
        #if not self._connecting:
        #    self._handle_write()
        #    if self._write_buf:
        #        self._add_io_state(self.ioloop.WRITE)
        self._add_io_state(self.ioloop.WRITE)

    def _handle_write(self):
        while self._write_buf:
            try:
                _merge_pre_bysize(self._write_buf, self.write_chunk_size)
                bytes_cnt = self.write_to_fd(self._write_buf[0])
                if bytes_cnt == 0:
                    break
                _merge_pre_bysize(self._write_buf, bytes_cnt)
                self._write_buf.popleft()
            except socket.error, e:
                if e.args[0] in (errno.EWOULDBLOCK, errno.EAGAIN):
                    break
                else:
                    gen_log.error("write error on %d : %s",self.fileno(), e)
                    self.close()
                    return
        if not self._write_buf and self._write_callback:
            callback = self._write_callback
            self._write_callback = None
            self._run_callback(callback)

    def write_to_fd(self):
        raise NotImplementedError()
    #end write process

    #handle events process
    def handle_events(self, fd, events):
        if self._closed:
            gen_log.warning("get events from closed stream")
            return
        try:
            if self._connecting:
                self._handle_connect()
            if events & self.ioloop.READ:
                self._handle_read()
            if self._closed:
                return
            if events & self.ioloop.WRITE:
                self._handle_write()
            if self._closed:
                return
            if events & self.ioloop.ERROR:
                self.ioloop.add_callback(self.close)
                return
            state = self.ioloop.ERROR
            if self.reading():
                state |= self.ioloop.READ
            if self.writing():
                state |= self.ioloop.WRITE
            if self._state != state:
                self._state = state
                self.ioloop.update_handler(self.fileno(), self._state)
        except:
            gen_log.error("Uncaught exception, close stream", exc_info = True)
            self.close()
            raise

    def reading(self):
        return self._read_callback is not None

    def writing(self):
        #write_callback is not Must, so it may always None
        #return self._write_callback is not None
        return bool(self._write_buf)

    #read logic process
    def _read_loop(self):
        self.check_close()
        while True:
            if self._read_from_buf():
                return
            if not self._closed:
                #this will raise EAGAIN when stream starting cause data hasn't
                #writed to fd.
                if self._read_to_buf() == 0:
                    break
        if self._read_from_buf():
            return
        self._add_io_state(self.ioloop.READ)

    def read_bytes(self, num, callback=None):
        assert isinstance(num, numbers.Integral)
        self._read_bytes = num
        self._read_callback = context_manager.wrap(callback)
        self._read_loop()
        #while True:
        #    if self._read_from_buf():
        #        return
        #    if not self._closed:
        #        if self._read_to_buf() == 0:
        #            break
        #self._add_io_state(self.ioloop.READ)

    def read_until(self, delimiter, callback=None):
        self._read_delimiter = delimiter
        self._read_callback = context_manager.wrap(callback)
        self._read_loop()

    def read_until_close(self, callback=None):
        self._read_callback = context_manager.wrap(callback)
        if self._closed:
            cb = self._read_callback
            self._read_callback = None
            self._run_callback(cb)
            self._read_until_close = False
            return
        self._read_until_close = True
        self._read_loop()
    #end read logic process


class IOStream(BaseIOStream):
    """
    A socket IOStream wrapper.
    """
    def __init__(self, socket, *args, **kwargs):
        self.socket = socket
        self.socket.setblocking(False)
        super(IOStream, self).__init__(*args, **kwargs)

    def fileno(self):
        return self.socket.fileno()

    def close_fd(self):
        self.socket.close()
        self.socket = None

    def read_from_fd(self):
        try:
            chunk = self.socket.recv(self.read_chunk_size)
        except socket.error, e:
            if e.args[0] in (errno.EWOULDBLOCK, errno.EAGAIN):
                return None
            else:
                raise
        if not chunk:
            #self.fd.close().....is a big BUG!
            self.close()
            return None
        return chunk

    def write_to_fd(self, data):
        gen_log.debug("in write_to_fd")
        return self.socket.send(data)

    def connect(self, address, callback):
        try:
            self.socket.connect(address)
        except socket.error as e:
            if e.args[0] not in (errno.EWOULDBLOCK, errno.EINPROGRESS):
                gen_log.error("connect error on fd %d : %s" % (self.fileno(),
                                                               e))
                self.close()
                return
        self._connect_callback = context_manager.wrap(callback)
        self._connecting = True
        self._add_io_state(self.ioloop.WRITE)

    def _handle_connect(self):
        if self._connect_callback is not None:
            callback = self._connect_callback
            self._connect_callback = None
            self._run_callback(callback)
        self._connecting = False


class PipeIOStream(BaseIOStream):
    pass

def _merge_pre_bysize(deque, size):
    if len(deque) == 1 and len(deque[0]) <= size:
        return
    prefix = []
    remaining = size
    while deque and remaining > 0:
        chunk = deque.popleft()
        if len(chunk) > remaining:
            deque.appendleft(chunk[remaining:])
            chunk = chunk[:remaining]
        prefix.append(chunk)
        remaining -= len(chunk)
    if prefix:
        deque.appendleft(''.join(prefix))
        #deque.appendleft(type(prefix[0])().join(prefix))
    if not deque:
        deque.appendleft(b"")

