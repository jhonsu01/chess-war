"""Viewer server: serves docs/ (the same viewer that gets published) and /live.json.

In live mode (`/?live`) the viewer polls /live.json; in replay mode it reads docs/data/.
One interface to watch the match and to publish it.
"""
from __future__ import annotations

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class LiveState:
    def __init__(self):
        self._lock = threading.Lock()
        self._blob = b'{"status":"waiting"}'

    def set(self, data: dict) -> None:
        blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
        with self._lock:
            self._blob = blob

    def blob(self) -> bytes:
        with self._lock:
            return self._blob


class _Handler(SimpleHTTPRequestHandler):
    live: LiveState

    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] == "/live.json":
            body = self.live.blob()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):  # quiet: the arena prints its own progress
        pass


def serve(docs: Path, live: LiveState, host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    handler = type("LiveHandler", (_Handler,), {"live": live})
    httpd = ThreadingHTTPServer((host, port), partial(handler, directory=str(docs)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
