"""Local-network HTTP endpoint for the Companion (one POST path, sealed envelopes only).

Bound to the LAN address the user chooses, never opened to the internet by Workbench (no UPnP, no relay).
Only ``POST /aiwb/v1`` exists; bodies are size-limited; every request is authenticated by service.handle().
"""
from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .service import CompanionService

PATH = "/aiwb/v1"
MAX_BODY = 512 * 1024
DEFAULT_PORT = 47821


def lan_address() -> str:
    """Best-effort LAN IPv4 (no packet is sent); falls back to loopback."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class CompanionServer:
    def __init__(self, service: CompanionService, host: str = "", port: int = DEFAULT_PORT) -> None:
        self.service = service
        self.host = host or lan_address()
        self.port = port
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.httpd is not None

    def start(self) -> int:
        if self.httpd:
            return self.port
        service = self.service

        class Handler(BaseHTTPRequestHandler):
            server_version = "AIWorkbenchCompanion/1"
            sys_version = ""

            def log_message(self, *_a: Any) -> None:  # no request logging (bodies/addresses stay private)
                pass

            def _send(self, code: int, obj: dict[str, Any]) -> None:
                data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                self._send(404, {"error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path != PATH:
                    return self._send(404, {"error": "not_found"})
                try:
                    n = int(self.headers.get("Content-Length") or "0")
                except ValueError:
                    n = -1
                if n <= 0 or n > MAX_BODY:
                    return self._send(413 if n > MAX_BODY else 400, {"error": "bad_size"})
                code, obj = service.handle(self.rfile.read(n))
                self._send(code, obj)

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="aiwb-companion", daemon=True)
        self.thread.start()
        return self.port

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
