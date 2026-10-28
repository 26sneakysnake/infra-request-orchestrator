"""Fixtures for tests that replay cassettes of real ServiceNow and Jira calls.

By default the clients replay tests/cassettes/<test name>.json with placeholder settings: no
network, no secrets. With CASSETTE_RECORD=1 (`make record`) they call the real instances from .env
and rewrite the cassettes, which creates test records there.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from integrations.cassette import RecordingTransport, ReplayTransport
from integrations.config import JiraSettings, ServiceNowSettings
from integrations.jira import JiraClient
from integrations.servicenow import ServiceNowClient

CASSETTES = Path(__file__).parent / "cassettes"
RECORDING = os.environ.get("CASSETTE_RECORD") == "1"

# Values written into cassettes in place of the real hosts and e-mail.
SERVICENOW_PLACEHOLDER = ServiceNowSettings("https://example.service-now.com", "user", "password")
JIRA_PLACEHOLDER = JiraSettings(
    "https://example.atlassian.net", "user@example.com", "token", "NETOPS"
)


def _host(url: str) -> str:
    return urlsplit(url).netloc


def _transport(name: str, replacements: dict[str, str]) -> httpx.BaseTransport:
    path = CASSETTES / f"{name}.json"
    return RecordingTransport(path, replacements) if RECORDING else ReplayTransport(path)


@pytest.fixture
def servicenow(request: pytest.FixtureRequest) -> Iterator[ServiceNowClient]:
    s = ServiceNowSettings.from_env() if RECORDING else SERVICENOW_PLACEHOLDER
    replacements = {_host(s.instance_url): _host(SERVICENOW_PLACEHOLDER.instance_url)}
    transport = _transport(request.node.name, replacements)
    with ServiceNowClient(s.instance_url, s.username, s.password, transport=transport) as client:
        yield client


@pytest.fixture
def jira(request: pytest.FixtureRequest) -> Iterator[JiraClient]:
    s = JiraSettings.from_env() if RECORDING else JIRA_PLACEHOLDER
    replacements = {
        _host(s.base_url): _host(JIRA_PLACEHOLDER.base_url),
        s.email: JIRA_PLACEHOLDER.email,
    }
    if RECORDING:
        # Not secrets, but personal identifiers: keep them out of the public cassettes too.
        with JiraClient(s.base_url, s.email, s.api_token) as unrecorded:
            me = unrecorded.myself()
        replacements[me["accountId"]] = "000000:00000000-0000-0000-0000-000000000000"
        replacements[me["displayName"]] = "NetCo Test"
    transport = _transport(request.node.name, replacements)
    with JiraClient(s.base_url, s.email, s.api_token, transport=transport) as client:
        yield client
