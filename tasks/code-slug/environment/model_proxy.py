"""CONNECT-only model gateway on a Docker internal network; no credentials logged."""

import select
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED = {"chatgpt.com", "auth.openai.com", "api.openai.com"}


class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_CONNECT(self):
        host, sep, port = self.path.rpartition(":")
        if not sep or host.lower() not in ALLOWED or port != "443":
            self.send_error(403, "Destination is not a model endpoint")
            return
        try:
            remote = socket.create_connection((host, 443), timeout=15)
        except OSError:
            self.send_error(502)
            return
        self.send_response(200, "Connection established")
        self.end_headers()
        try:
            with remote:
                peers = [self.connection, remote]
                while True:
                    ready, _, _ = select.select(peers, [], [], 120)
                    if not ready:
                        return
                    for src in ready:
                        buf = src.recv(65536)
                        if not buf:
                            return
                        (remote if src is self.connection else self.connection).sendall(buf)
        except OSError:
            pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 3128), Proxy).serve_forever()
