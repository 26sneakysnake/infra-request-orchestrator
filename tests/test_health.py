import socket
import threading
from collections import Counter
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from stack.health import Endpoint, probe, wait_for


class _Handler(BaseHTTPRequestHandler):
    """/ok answers 200, /warmup answers 503 twice then 200, anything else answers 503."""

    def do_GET(self) -> None:
        calls = self.server.calls
        calls[self.path] += 1
        if self.path == "/ok" or (self.path == "/warmup" and calls[self.path] > 2):
            self.send_response(200)
        else:
            self.send_response(503)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass  # keep test output quiet


@pytest.fixture
def server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.calls = Counter()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_probe_accepts_success(server: str) -> None:
    assert probe(Endpoint(f"{server}/ok"))


def test_probe_rejects_server_error(server: str) -> None:
    assert not probe(Endpoint(f"{server}/down"))


def test_probe_rejects_closed_port() -> None:
    assert not probe(Endpoint(f"http://127.0.0.1:{_closed_port()}/"), timeout=1)


def test_wait_for_retries_until_ready(server: str) -> None:
    status = wait_for({"warmup": Endpoint(f"{server}/warmup")}, timeout=5, interval=0.01)
    assert status == {"warmup": True}


def test_wait_for_reports_endpoints_still_down_at_timeout(server: str) -> None:
    endpoints = {"ok": Endpoint(f"{server}/ok"), "down": Endpoint(f"{server}/down")}
    status = wait_for(endpoints, timeout=0.2, interval=0.05)
    assert status == {"ok": True, "down": False}
