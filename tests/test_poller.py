from typing import Any

import pytest

from workers.poller import poll_once, ritm_variables

RITM = {
    "sys_id": "ritm-sys",
    "number": "RITM0010042",
    "variables.service_name": "catalogue-api",
    "variables.environment": "dev",
    "variables.ports": "8080/tcp",
    "variables.source_networks": "10.20.0.0/16",
    "variables.exposure": "interne",
    "variables.vm_required": "false",
    "variables.urgent": "true",
    "variables.request_text": "Bonjour",
}


class FakeServiceNow:
    def __init__(self, ritms: list[dict[str, Any]]) -> None:
        self.ritms = ritms
        self.queries: list[str] = []
        self.states: list[str] = []
        self.comments: list[str] = []

    def query(self, table: str, query: str, fields: list[str], limit: int) -> list[dict[str, Any]]:
        self.queries.append(query)
        return self.ritms

    def set_state(self, table: str, sys_id: str, state: str) -> None:
        self.states.append(state)

    def add_comment(self, table: str, sys_id: str, text: str, internal: bool = False) -> None:
        self.comments.append(text)


def test_ritm_variables_become_process_variables() -> None:
    variables = ritm_variables(RITM)
    assert variables["ritmNumber"] == "RITM0010042"
    assert variables["serviceName"] == "catalogue-api"
    assert variables["sourceNetworks"] == "10.20.0.0/16"
    assert variables["urgent"] is True and variables["vmRequired"] is False
    assert variables["vmSize"] == ""


def test_poll_claims_the_request_before_starting_the_instance() -> None:
    sn = FakeServiceNow([RITM])
    started = []

    def start(variables: dict[str, Any], business_id: str) -> str:
        assert sn.states == ["2"], "the request must be claimed first"
        started.append(business_id)
        return "2251799813685249"

    assert poll_once(sn, start, "item-sys", only=["RITM0010042"]) == ["RITM0010042"]  # type: ignore[arg-type]
    assert started == ["RITM0010042"]
    assert sn.queries == ["cat_item=item-sys^state=1^numberINRITM0010042"]
    assert "2251799813685249" in sn.comments[0]


def test_failed_start_releases_the_request() -> None:
    sn = FakeServiceNow([RITM])

    def start(variables: dict[str, Any], business_id: str) -> str:
        raise ConnectionError("engine down")

    with pytest.raises(ConnectionError):
        poll_once(sn, start, "item-sys")  # type: ignore[arg-type]
    assert sn.states == ["2", "1"]
