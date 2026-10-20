"""Controlled Host listener for the occupied-default-port KVM acceptance."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return
        body=f'piwork-microvm controlled port-{self.server.server_port} listener\n'.encode()
        self.send_response(200)
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self,*args):
        pass


parser=argparse.ArgumentParser()
parser.add_argument('--port',type=int,default=7171)
HTTPServer(('127.0.0.1',parser.parse_args().port),Handler).serve_forever()
