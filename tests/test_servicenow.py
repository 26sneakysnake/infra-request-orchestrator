import json

import httpx
import pytest

from integrations.seed import ensure_catalog_item, order_request
from integrations.servicenow import ServiceNowClient, ServiceNowError


def _client(handler) -> ServiceNowClient:
    return ServiceNowClient(
        "https://example.service-now.com", "u", "p", httpx.MockTransport(handler)
    )


def test_servicenow_error_message_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"error": {"message": "User is not authenticated"}, "status": "failure"}
        return httpx.Response(401, json=body)

    with pytest.raises(ServiceNowError, match="401: User is not authenticated") as excinfo:
        _client(handler).query("sc_req_item")
    assert excinfo.value.status == 401


def test_html_answer_suggests_a_hibernating_instance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<html>Your instance is hibernating</html>")

    with pytest.raises(ServiceNowError, match="hibernating"):
        _client(handler).get("sc_req_item", "abc")


def test_internal_comment_goes_to_work_notes() -> None:
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"result": {}})

    _client(handler).add_comment("sc_req_item", "abc", "Note interne", internal=True)
    assert sent == {"work_notes": "Note interne"}


@pytest.mark.recorded
def test_request_lifecycle(servicenow: ServiceNowClient) -> None:
    item = ensure_catalog_item(servicenow)
    created = order_request(
        servicenow,
        item,
        {
            "request_text": "[test] Demande créée par les tests enregistrés du dépôt.",
            "service_name": "test-api",
            "environment": "dev",
            "ports": "8080/tcp",
            "source_networks": "10.20.0.0/16",
            "exposure": "interne",
            "vm_required": False,
        },
    )
    assert created["ritm"].startswith("RITM")
    ritm = created["ritm_sys_id"]

    servicenow.add_comment("sc_req_item", ritm, "[test] Il manque l'environnement cible.")
    attachment = servicenow.attach("sc_req_item", ritm, "fiche-test.md", b"# Fiche de test\n")
    assert attachment["file_name"] == "fiche-test.md"

    updated = servicenow.set_state("sc_req_item", ritm, 2)  # 2 = Work in Progress
    assert updated["state"] == "2"
    assert servicenow.get("sc_req_item", ritm)["number"] == created["ritm"]
