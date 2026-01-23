from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

HEALTH_BODY = '{ "status": "ok" }'


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"not found")
            return

        # Validate that the body is valid JSON while keeping the exact string stable.
        _parsed: Any = json.loads(HEALTH_BODY)

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(HEALTH_BODY.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(HEALTH_BODY.encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # Keep tests quiet.
        return


@dataclass(frozen=True)
class RunningServer:
    server: HTTPServer
    thread: threading.Thread
    host: str
    port: int


def start_server(host: str = "127.0.0.1", port: int = 0) -> RunningServer:
    server = HTTPServer((host, port), HealthHandler)
    actual_host, actual_port = server.server_address[0], int(server.server_address[1])

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    return RunningServer(server=server, thread=thread, host=actual_host, port=actual_port)


def stop_server(running: RunningServer) -> None:
    running.server.shutdown()
    running.server.server_close()
    running.thread.join(timeout=2)
