"""Offline loopback HTTP fixture. Run as root; agents run as uid 1000."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def serve(mode, state_path):
    state = {"requests": [], "executions": 0, "value_attempts": 0}

    def persist():
        Path(state_path).write_text(json.dumps(state))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state["requests"].append("GET " + self.path)
            code, body = 200, {}
            if self.path == "/items":
                body = {
                    "items": [{"id": "A", "amount": 10}, {"id": "B", "amount": 20}],
                    "next": "/items?page=2",
                }
            elif self.path == "/items?page=2":
                body = {"items": [{"id": "C", "amount": 30}], "next": None}
            elif self.path == "/value":
                state["value_attempts"] += 1
                code, body = (
                    (503, {"error": "temporary"})
                    if state["value_attempts"] < 3
                    else (200, {"value": 42})
                )
            elif self.path == "/request":
                body = {"id": "request-1", "action": "execute"}
            elif self.path == "/approval":
                body = {"granted": False}
            else:
                code, body = 404, {"error": "not found"}
            persist()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def do_POST(self):
            state["requests"].append("POST " + self.path)
            if self.path == "/execute":
                state["executions"] += 1
            persist()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"executed"}')

    persist()
    HTTPServer(("127.0.0.1", 8080), Handler).serve_forever()


if __name__ == "__main__":
    import sys

    serve(sys.argv[1], sys.argv[2])
