import env
import time,threading
from nida.ioevent import IOLoop
from nida.log import app_log,access_log, gen_log, define_logging_options
from nida.options import parse_command, options

def callback():
    print 'in callback'

def callback_sleep():
    time.sleep(3)

def startTornado():
    ioloop = IOLoop()
    ioloop.make_current()
    time.sleep(3)
    for i in range(10):
        print i
        ioloop.add_callback(callback)
        time.sleep(1)
    ioloop.add_callback(callback_sleep)
    ioloop.add_callback(ioloop.stop)
    ioloop.start()
    #tornado.ioloop.IOLoop.instance().start()

def startTornadoMain():
    IOLoop.instance().start()

def stopTornado():
    IOLoop.instance().stop()

if __name__ == "__main__":
    define_logging_options(options)
    parse_command()
    thread1 = threading.Thread(target=startTornado)
    thread1.start()
    thread2 = threading.Thread(target=startTornadoMain)
    thread2.start()
    print "Your web server will self destruct in 2 minutes"
    time.sleep(3)
    IOLoop.instance().add_callback(callback)
    #time.sleep(10)
    IOLoop.instance().add_callback(callback)
    stopTornado()
    
