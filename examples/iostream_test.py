"""
author: shawnsha@tencent.com
date : 2016.08.18

To ensure the iostream avaiable.
"""
import env
from nida.iostream import IOStream
from nida.ioevent import IOLoop
from nida.options import parse_command
import time

import socket

def send_request():
    print "send request"
    #after stream.write, the socket become writable and readable when epoll, and
    #handle_events handle the read first,it return error EGAIN, and then hanle
    #writable, put the GET request to socket. After this two handles,
    #handle_event will remove POLLOUT event cause the write_buf has no data,
    #and POLLIN still there. In the next handle_read, we can get the data.
    stream.write(b"GET / HTTP/1.1\r\nHost:localhost\r\n\r\n")
    time.sleep(3)
    stream.read_until(b"\r\n\r\n", on_headers)

def on_headers(data):
    headers = {}
    for line in data.split(b"\r\n"):
        parts = line.split(b":")
        if len(parts)==2:
            headers[parts[0].strip()] = parts[1].strip()
    print headers
    stream.read_bytes(int(headers[b"Content-Length"]), on_body)

def on_body(data):
    print data
    stream.close()
    IOLoop.instance().stop()
    #IOLoop.global_instance().stop()


parse_command()
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
stream = IOStream(s)
stream.connect(("localhost", 80), send_request)
IOLoop.instance().start()
#IOLoop.global_instance().start()
