"""Start one expose_service instance per new NetCo request in ServiceNow.

ServiceNow cannot call the local Camunda stack (no public address), so the orchestrator polls the
Table API for open requests of the NetCo catalog item.
"""

import logging
import threading
from collections.abc import Callable
from typing import Any

from integrations.seed import CATALOG_ITEM
from integrations.servicenow import RITM_WORK_IN_PROGRESS, ServiceNowClient, ServiceNowError

log = logging.getLogger(__name__)

RITM_OPEN = "1"
# ServiceNow catalog variable -> process variable
FORM_FIELDS = {
    "request_text": "requestText",
    "service_name": "serviceName",
    "environment": "environment",
    "ports": "ports",
    "source_networks": "sourceNetworks",
    "exposure": "exposure",
    "vm_required": "vmRequired",
    "vm_size": "vmSize",
    "urgent": "urgent",
}
BOOLEAN_FIELDS = {"vmRequired", "urgent"}

StartInstance = Callable[[dict[str, Any], str], str]


def ritm_variables(ritm: dict[str, Any]) -> dict[str, Any]:
    variables: dict[str, Any] = {"ritmSysId": ritm["sys_id"], "ritmNumber": ritm["number"]}
    for sn_name, name in FORM_FIELDS.items():
        value = ritm.get(f"variables.{sn_name}") or ""
        variables[name] = value == "true" if name in BOOLEAN_FIELDS else value
    return variables


def catalog_item_id(client: ServiceNowClient) -> str:
    items = client.query("sc_cat_item", f"name={CATALOG_ITEM}", ["sys_id"], limit=1)
    if not items:
        raise ServiceNowError(404, f"catalog item {CATALOG_ITEM!r} not found: run `make seed`")
    return items[0]["sys_id"]


def poll_once(
    client: ServiceNowClient, start: StartInstance, item_id: str, only: list[str] | None = None
) -> list[str]:
    query = f"cat_item={item_id}^state={RITM_OPEN}"
    if only:
        query += "^numberIN" + ",".join(only)
    fields = ["sys_id", "number"] + [f"variables.{name}" for name in FORM_FIELDS]
    started = []
    for ritm in client.query("sc_req_item", query, fields, limit=20):
        # Claim the request first, so that a second poll does not start it twice.
        client.set_state("sc_req_item", ritm["sys_id"], RITM_WORK_IN_PROGRESS)
        try:
            key = start(ritm_variables(ritm), ritm["number"])
        except Exception:
            client.set_state("sc_req_item", ritm["sys_id"], RITM_OPEN)
            raise
        client.add_comment(
            "sc_req_item",
            ritm["sys_id"],
            f"Demande prise en charge par l'orchestrateur (instance Camunda {key}).",
            internal=True,
        )
        started.append(ritm["number"])
    return started


def poll_forever(
    client: ServiceNowClient,
    start: StartInstance,
    stop: threading.Event,
    only: list[str] | None = None,
    interval: float = 10.0,
) -> None:
    item_id = catalog_item_id(client)
    log.info("Polling ServiceNow every %.0f s for %s requests", interval, CATALOG_ITEM)
    while not stop.is_set():
        try:
            for number in poll_once(client, start, item_id, only):
                log.info("Started expose_service for %s", number)
        except Exception:
            # Keep polling: a developer instance can be briefly unavailable (hibernation).
            log.exception("ServiceNow poll failed")
        stop.wait(interval)
