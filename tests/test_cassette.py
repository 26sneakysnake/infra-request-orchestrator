import json
from pathlib import Path

import httpx
import pytest

from integrations.cassette import CassetteMismatch, RecordingTransport, ReplayTransport


def _upstream(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"link": "https://real.example.org/x", "owner": "me@real.org"})


def test_records_without_secrets_then_replays(tmp_path: Path) -> None:
    path = tmp_path / "cassette.json"
    recorder = RecordingTransport(
        path,
        {"real.example.org": "example.test", "me@real.org": "user@example.com"},
        inner=httpx.MockTransport(_upstream),
    )
    with httpx.Client(transport=recorder, auth=("me@real.org", "s3cret")) as client:
        client.post("https://real.example.org/api", json={"owner": "me@real.org"})

    text = path.read_text(encoding="utf-8")
    for leaked in ("real.example.org", "me@real.org", "s3cret", "Authorization", "authorization"):
        assert leaked not in text

    with httpx.Client(transport=ReplayTransport(path)) as client:
        response = client.post("https://example.test/api", json={})
    assert response.json() == {"link": "https://example.test/x", "owner": "user@example.com"}


def _cassette(tmp_path: Path) -> Path:
    path = tmp_path / "cassette.json"
    exchange = {
        "method": "GET",
        "url": "https://example.test/a",
        "request_body": "",
        "status": 200,
        "content_type": "application/json",
        "response_body": "{}",
    }
    path.write_text(json.dumps([exchange]), encoding="utf-8")
    return path


def test_replay_rejects_an_unexpected_request(tmp_path: Path) -> None:
    with httpx.Client(transport=ReplayTransport(_cassette(tmp_path))) as client:
        with pytest.raises(CassetteMismatch, match="expected GET https://example.test/a"):
            client.get("https://example.test/b")


def test_replay_rejects_a_request_beyond_the_cassette(tmp_path: Path) -> None:
    with httpx.Client(transport=ReplayTransport(_cassette(tmp_path))) as client:
        client.get("https://example.test/a")
        with pytest.raises(CassetteMismatch, match="no recorded response left"):
            client.get("https://example.test/a")
