import env
from nida.tcpserver import TCPServer
from nida.ioevent import IOLoop
from nida.options import parse_command

if __name__ == "__main__":
    parse_command()
    s = TCPServer()
    s.listen(8000)
    IOLoop.instance().start()
    #IOLoop.current().start()


