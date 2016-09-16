from __future__ import absolute_import
import env
import nida.ioevent
import nida.httpserver
from nida.options import parse_command

def handle_request(request):
    message = "You requested %s\n" % request.uri
    request.write("HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (
                  len(message), message))
    request.finish()

parse_command()
http_server = nida.httpserver.HTTPServer(handle_request)
http_server.listen(8080)
nida.ioevent.IOLoop.instance().start()


