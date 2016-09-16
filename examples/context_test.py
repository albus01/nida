from __future__ import absolute_import, division
import env
import time

from nida.ioevent import IOLoop
from nida import context_manager
from nida.context_manager import *
from nida.log import app_log,access_log, gen_log, define_logging_options
from nida.options import parse_command, options


from functools import partial
from contextlib import contextmanager

class Loop(object):
    def __init__(self):
        self.callbacks = []

    def start(self):
        while True:
            #time.sleep(5)
            callbacks = self.callbacks
            self.callbacks = []
            for callback in callbacks:
                try:
                    callback()
                except:
                    print "Loop catch the Exception"

    def add_callback(self, callback, *args, **kwargs):
        self.callbacks.append(context_manager.wrap(partial(callback, *args,
                                                           **kwargs)))
#_loop = Loop()
_loop = IOLoop()

@contextmanager
def context(name):
    try:
        print 'enter %s' % name
        yield
    except Exception as e:
        print "%s catch the exception: %s" % (name, e)
    finally:
        print 'exit %s' % name

def f1(name):
    global _loop
    with ExceptionStackContext(lambda t, v, trace : exception_handler(t, v,
                                                                      trace)) as s1:
        with StackContext(partial(context,'a')) as s2:
            with StackContext(partial(context,'b')) as s3:
                print "f1:%s" % name
                _loop.add_callback(f2, name)
                #s3()
            #s2()


def f2(name):
    with StackContext(partial(context, 'c')) as s4:
    #with NullStackContext():
        print "f2:%s" % name
        #raise Exception("f2 Exception")
        _loop.add_callback(f3)
        #s4()

def f3():
    def wrapper():
        print "f3"
        raise Exception("f3 Exception")
    with NullStackContext():
        _loop.add_callback(wrapper)

def exception_handler(type, value, traceback):
    print 'in exception_handler ~~'
    print context_manager._stack.contexts
    return True

if __name__ == "__main__":
    define_logging_options(options)
    parse_command()

    _loop.add_callback(f1, 'shawnsha')
    _loop.start()


