"""Record real HTTP exchanges once, then replay them in tests without network or secrets.

A cassette stores, per exchange: method, URL, request body, status, content type and response
body. Headers are never stored, so credentials cannot reach a cassette; real hostnames and
identifiers are replaced by placeholders before writing.
"""

import json
from pathlib import Path
from typing import Any

import httpx


class CassetteMismatch(AssertionError):
    """The code under test sent a request that the cassette does not expect."""


class RecordingTransport(httpx.BaseTransport):
    def __init__(
        self,
        path: Path,
        replacements: dict[str, str],
        inner: httpx.BaseTransport | None = None,
    ) -> None:
        self.path = path
        # Longest first, so a host is replaced before any shorter string it contains.
        self.replacements = sorted(replacements.items(), key=lambda item: -len(item[0]))
        self.inner = inner or httpx.HTTPTransport()
        self.interactions: list[dict[str, Any]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self.inner.handle_request(request)
        response.read()
        self.interactions.append(
            {
                "method": request.method,
                "url": self._scrub(str(request.url)),
                "request_body": self._request_body(request),
                "status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "response_body": self._scrub(response.text),
            }
        )
        return response

    def close(self) -> None:
        self.inner.close()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.interactions, indent=2, ensure_ascii=False)
        self.path.write_text(text + "\n", encoding="utf-8", newline="\n")

    def _request_body(self, request: httpx.Request) -> str:
        if request.headers.get("content-type", "").startswith("multipart/"):
            return "<multipart body not recorded>"
        try:
            return self._scrub(request.content.decode("utf-8"))
        except UnicodeDecodeError:
            return f"<{len(request.content)} binary bytes>"

    def _scrub(self, text: str) -> str:
        for real, placeholder in self.replacements:
            text = text.replace(real, placeholder)
        return text


class ReplayTransport(httpx.BaseTransport):
    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"missing cassette {path}; record it with `make record`")
        self.interactions = json.loads(path.read_text(encoding="utf-8"))
        self.position = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self.position >= len(self.interactions):
            raise CassetteMismatch(f"no recorded response left for {request.method} {request.url}")
        recorded = self.interactions[self.position]
        self.position += 1
        expected = f"{recorded['method']} {recorded['url']}"
        if f"{request.method} {request.url}" != expected:
            raise CassetteMismatch(f"expected {expected}, got {request.method} {request.url}")
        return httpx.Response(
            recorded["status"],
            headers={"content-type": recorded["content_type"]},
            content=recorded["response_body"].encode("utf-8"),
            request=request,
        )
