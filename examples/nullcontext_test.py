from __future__ import absolute_import, division
import env
import time

from nida.ioevent import IOLoop
#from tornado.ioloop import IOLoop
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


def f2(name):
    with StackContext(partial(context, 'c')) as s4:
    #with NullStackContext():
        print "f2:%s" % name
        #raise Exception("f2 Exception")
        _loop.add_callback(f3)
        #s4()

def callbackfunc():
    print context_manager._stack.contexts
    print 'in callback'
    raise Exception("callback Exception")

def run_callback(callback, *args):
    def wrapper():
        try:
            callback()
        except Exception as e:
            print 'catch!!!!'
            print e
    with StackContext(partial(context, 'a')):
        #with NullStackContext():
            _loop.add_callback(wrapper)

def context2():
    with StackContext(partial(context,'b')):
        _loop.add_callback(callbackfunc)


def exception_handler(type, value, traceback):
    print 'in exception_handler ~~'
    print context_manager._stack.contexts
    return False

if __name__ == "__main__":
    define_logging_options(options)
    parse_command()
    
    _loop.add_callback(partial(run_callback, context2))
    _loop.start()


