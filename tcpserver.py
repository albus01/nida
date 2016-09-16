"""
author: shawnsha@tencent.com
date  : 2016.08.18

A nonblocking, single-thread TCP server.
"""
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os
import errno
import socket

from nida.iostream import IOStream
from nida.ioevent import IOLoop
from nida.util.netutil import _DEFAULT_BACKLOG, bind_listen
from nida.log import gen_log, app_log
from nida import process


class TCPServer(object):
    """
    a nonblocking, single-thread TCP Server.
    
    Not supported ssl and ipv6 now.
    """
    def __init__(self, backlog=_DEFAULT_BACKLOG, ioloop=None):
        self.ioloop           = ioloop or IOLoop.current()
        self._sockets         = {}
        self._pending_sockets = []
        self._backlog         = backlog
        self._start           = False

    def bind(self, port, address=None):
        sockets = bind_listen(port, address=address, family=socket.AF_INET,
                              socktype=socket.SOCK_STREAM,
                              backlog=self._backlog)
        if self._start:
            self.add_sockets(sockets)
        else:
            self._pending_sockets.append(sockets)

    def listen(self, port, address=""):
        socks = bind_listen(port, address=address, family=socket.AF_INET,
                    sock_type=socket.SOCK_STREAM, backlog=self._backlog)
        self.add_sockets(socks)


    def add_sockets(self, sockets):
        for sock in sockets:
            self._sockets[sock.fileno()] = sock
            self.accept_connection(sock, self._handle_conn)

    def _handle_conn(self, conn, addr):
        try:
            stream = IOStream(conn)
            self.handle_stream(stream, addr)
        except:
            app_log.error("error in handle connection", exc_info = True)

    def handle_stream(self, stream, addr):
        raise NotImplementedError()

    def accept_connection(self, sock, callback):
        def accept_handler(fd, events):
            while True:
                try:
                    conn, addr = sock.accept()
                except socket.error as e:
                    if e.args[0] in (errno.EWOULDBLOCK, errno.EAGAIN):
                        return
                    raise
                callback(conn, addr)

        self.ioloop.add_handler(sock, accept_handler,
                                self.ioloop.READ)

    def start(self, process_num = 1):
        assert not self._start
        self._start = True
        if process_num != 1:
            process.fork(process_num)
        self.add_sockets(self._pending_sockets)

    def stop(self):
        for fd, sock in self._sockets.items():
            self.ioloop.remove_handler(fd)
            sock.close()

