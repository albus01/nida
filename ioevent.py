"""
author: shawnsha@tencent.com
date: 2016.08.10

An non-blocking I/O envent module.
"""
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division

import select
import threading
import thread
import time
import functools
import heapq
import errno
import numbers

from nida import context_manager
from nida.platform.posix import Waker, set_close_exec
from nida.log import app_log, gen_log
from nida.util.factory import Factory
from nida.util.util import get_errno


class IOLoop(Factory):
    """
    A level-triggered I/O event loop.

    Use epoll in linux and kqueue in BSD/Mac OS X.
    Examples:
        def conn_ready(sock):
            try:
                connection, address = sock.accept()
            except Exception as e:
                if e not in (error.EWOULDBLOCK, error.EAGAIN):
                    raise
                return
            connection.setblocking(0)
            handle_connection(connection, address)

        if __name__ == "__main__":
            socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
            socket.setblocking(0)
            socket.bind("" , port)
            socket.listen(128)

            callback = functools.partial(conn_ready, socket)
            ioloop = IOLoop.current()
            ioloop.add_handler(socket.fileno(), callback, ioloop.READ)
            ioloop.start()
    """
    #events
    _EPOLLIN  = select.POLLIN
    _EPOLLOUT = select.POLLOUT
    _EPOLLHUP = select.POLLHUP
    _EPOLLERR = select.POLLERR
    
    NONE  = 0
    READ  = _EPOLLIN
    WRITE = _EPOLLOUT
    ERROR = _EPOLLERR | _EPOLLHUP


    _current = threading.local()
    _thread_lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        #instance=False just want known if current instance is none, do not
        #wanna create instance 
        if IOLoop.current(instance=False) is None:
            self.make_current()

    @classmethod
    def config_base(cls):
        return IOLoop

    @classmethod
    def config_sub(cls):
        if hasattr(select, "epoll"):
            return EPollIOLoop

        if hasattr(select, "kqueue"):
            return KQueueIOLoop

    @staticmethod
    def instance():
        """
        IOLoop's global instance. If other thread wanna communicate with each
        other, call this.
        """
        if not hasattr(IOLoop, "_instance"):
            with IOLoop._thread_lock:
                if not hasattr(IOLoop, "_instance"):
                    #IOLoop() __init__ will make the _instance become current instance
                    IOLoop._instance = IOLoop()
        return IOLoop._instance

    @staticmethod
    def current(instance=True):
        current = getattr(IOLoop._current, "instance", None)
        if current is None and instance:
            current = IOLoop.instance()
        return current

    def make_current(self):
        """
        New thread's local instance.
        """
        IOLoop._current.instance = self

    def add_handler(self, fd, handler, events):
        raise NotImplementedError()

    def remove_handler(self, fd):
        raise NotImplementedError()

    def update_handler(self, fd, events):
        raise NotImplementedError()

    def add_callback(self, callback, *args, **kwargs):
        raise NotImplementedError()

    def add_timeout(self, deadline, callback):
        raise NotImplementedError()

    def remove_timeout(self, timeout):
        raise NotImplementedError()

    def start(self):
        pass

    def stop(self):
        pass

    def time(self):
        return time.time()

    def split_fd(self, fd):
        try:
            return fd.fileno(), fd
        except AttributeError:
            return fd, fd

    def close_fd(self, fd):
        try:
            fd.close()
        except AttributeError:
            try:
                os.close(fd)
            except:
                gen_log.error("close fd error", exc_info = True)

    def _run_callback(self, callback):
        try:
            callback()
        except:
            self.handle_exception(callback)

    def handle_exception(self, callback):
        app_log.error("Exception occured in callback:%s" % callback, exc_info
                      = True)

    def close(self):
        raise NotImplementedError()

class PollIOLoop(IOLoop):
    """
    I/O event loop through poll.
    """
    def __init__(self, impl):
        self._callbacks     = []
        self._timeouts      = []
        self._due_timeouts  = []
        self._callback_lock = threading.Lock()
        self._impl          = impl
        if hasattr(self._impl, 'fileno'):
            set_close_exec(self._impl.fileno())
        self._handlers      = {}
        self._events        = {}
        self._cancels       = 0
        self._running       = False
        self._stopped       = False
        self._closing       = False
        self._thread_id     = None
        self._waker         = Waker()
        self.add_handler(self._waker.fileno(), lambda fd, event:
                         self._waker.consume(), self.READ)

    def add_handler(self, fd, handler, events):
        fd_no, fd_obj = self.split_fd(fd)
        self._handlers[fd_no] = (fd_obj, context_manager.wrap(handler))
        self._impl.register(fd_no, events | self.ERROR)

    def update_handler(self, fd, events):
        fd_no, fd_obj = self.split_fd(fd)
        self._impl.modify(fd_no, events | self.ERROR)

    def remove_handler(self, fd):
        fd_no, fd_obj = self.split_fd(fd)
        self._handlers.pop(fd_no, None)
        self._events.pop(fd_no, None)
        try:
            self._impl.unregister(fd_no)
        except:
            gen_log.error("remove fd:%s from IOLoop error" % fd_no, exc_info = True)

    def add_timeout(self, deadline, callback):
        timeout = _Timeout(deadline, callback)
        heapq.heappush(self._timeouts, timeout)

    def remove_timeout(self, timeout):
        timeout.callback = None

    def add_callback(self, callback, *args, **kwargs):
        if self._closing:
            return

        if self._thread_id != thread.get_ident():
            with self._callback_lock:
                need_wake = not self._callbacks
                self._callbacks.append(functools.partial(context_manager.wrap(callback),
                                                         *args, **kwargs))
                if need_wake:
                    self._waker.wake()
        else:
            self._callbacks.append(functools.partial(context_manager.wrap(callback),
                                                       *args, **kwargs))

    def start(self):
        if self._stopped:
            self._stopped = False
            return
        if self._running:
            raise RuntimeError("ioloop is running")
        self._running = True
        self._thread_id = thread.get_ident()
        try:
            while True:
                with self._callback_lock:
                    callbacks = self._callbacks
                    self._callbacks = []

                due_timeouts = []
                now = self.time()
                while self._timeouts:
                    if _timeouts[0].callback is None:
                        heapq.heappop(self._timeouts)
                    elif _timeouts[0].callback <= now:
                        due_timeouts.append(heapq.heappop(self._timeouts))
                    else:
                        break

                for callback in callbacks:
                    self._run_callback(callback)

                for timeout in due_timeouts:
                    if timeout.callback is not None:
                        self._run_callback(timeout.callback)

                #In order to run all callbacks, can not put this code at the
                #bottom of poll()
                if not self._running:
                    break

                POLL_TIME = 3600
                if self._callbacks:
                    poll_timeout = 0
                elif self._timeouts:
                    poll_timeout = self._timeouts[0].deadline - self.time()
                    poll_timeout = min(poll_timeout,POLL_TIME) 
                else:
                    poll_timeout = POLL_TIME
                
                try:
                    fd_event_pairs = self._impl.poll(poll_timeout)
                except Exception as e:
                    if get_errno(e) == error.EINTR:
                        continue
                    else:
                        raise
                self._events.update(fd_event_pairs)
                while self._events:
                    fd_no, event = self._events.popitem()
                    fd_obj, handler = self._handlers[fd_no]
                    try:
                        handler(fd_obj, event)
                    except Exception as e:
                        if get_errno(e) == errno.EPIPE:
                            gen_log.debug("broken pipe")
                        else:
                            self.handle_exception(handler)
                
        finally:
            self._stopped = False
            self._running = False
            self._waker.wake()

    def stop(self):
        self._running = False
        self._stopped = True
        self._waker.wake()

    def close(self):
        for fd_obj, handler in self._handlers.values():
            self.close_fd(fd_obj)
        self.remove_handler(self._waker.fileno())
        self._impl.close()
        self._callbacks = None
        self._timeouts = None

class _Timeout(object):
    __slots__ = ['callback', 'deadline']
    
    def __init__(self, deadline, callback):
        if not isinstance(deadline, numbers.Real):
            raise TypeError("Unsupported deadline %s" % deadline)
        self._deadline = deadline
        self._callback = callback

    def __lt__(self, other):
        return self._deadline < other._deadline

    def __le__(self, other):
        return self._deadline < other._deadline


class EPollIOLoop(PollIOLoop):
    def __init__(self, *args, **kwargs):
        return super(EPollIOLoop, self).__init__(select.epoll(), *args, **kwargs)

class KQueueIOLoop(PollIOLoop):
    def __init__(self, *args, **kwargs):
        return super(KQueueIOLoop, self).__init__(_KQueue(), *args, **kwargs)

class _KQueue(object):
    """A kqueue-based event loop for BSD/Mac systems."""
    def __init__(self):
        self._kqueue = select.kqueue()
        self._active = {}

    def fileno(self):
        return self._kqueue.fileno()

    def close(self):
        self._kqueue.close()

    def register(self, fd, events):
        if fd in self._active:
            raise IOError("fd %s already registered" % fd)
        self._control(fd, events, select.KQ_EV_ADD)
        self._active[fd] = events

    def modify(self, fd, events):
        self.unregister(fd)
        self.register(fd, events)

    def unregister(self, fd):
        events = self._active.pop(fd)
        self._control(fd, events, select.KQ_EV_DELETE)

    def _control(self, fd, events, flags):
        kevents = []
        if events & IOLoop.WRITE:
            kevents.append(select.kevent(
                fd, filter=select.KQ_FILTER_WRITE, flags=flags))
        if events & IOLoop.READ:
            kevents.append(select.kevent(
                fd, filter=select.KQ_FILTER_READ, flags=flags))
        for kevent in kevents:
            self._kqueue.control([kevent], 0)

    def poll(self, timeout):
        kevents = self._kqueue.control(None, 1000, timeout)
        events = {}
        for kevent in kevents:
            fd = kevent.ident
            if kevent.filter == select.KQ_FILTER_READ:
                events[fd] = events.get(fd, 0) | IOLoop.READ
            if kevent.filter == select.KQ_FILTER_WRITE:
                if kevent.flags & select.KQ_EV_EOF:
                    events[fd] = IOLoop.ERROR
                else:
                    events[fd] = events.get(fd, 0) | IOLoop.WRITE
            if kevent.flags & select.KQ_EV_ERROR:
                events[fd] = events.get(fd, 0) | IOLoop.ERROR
        return events.items()

