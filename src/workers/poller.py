"""Bridge from ServiceNow to the process, by polling the Table API.

ServiceNow cannot call the local Camunda stack (no public address), so the orchestrator polls:
- open requests of the NetCo catalog item start one expose_service instance each;
- pending requests (the process asked the requester for missing information) are checked for a
  reply comment, which is correlated to the waiting instance as the requester-reply message.
"""

import logging
import threading
from collections.abc import Callable
from typing import Any

from integrations.seed import CATALOG_ITEM
from integrations.servicenow import (
    RITM_OPEN,
    RITM_PENDING,
    RITM_WORK_IN_PROGRESS,
    ServiceNowClient,
    ServiceNowError,
)
from workers.handlers import REQUESTER_MARKER

log = logging.getLogger(__name__)

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
CorrelateReply = Callable[[str, str], None]  # (request number, reply text)


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


def _requests(client: ServiceNowClient, item_id: str, state: str, only, fields) -> list[dict]:
    query = f"cat_item={item_id}^state={state}"
    if only:
        query += "^numberIN" + ",".join(only)
    return client.query("sc_req_item", query, fields, limit=20)


def poll_once(
    client: ServiceNowClient, start: StartInstance, item_id: str, only: list[str] | None = None
) -> list[str]:
    fields = ["sys_id", "number"] + [f"variables.{name}" for name in FORM_FIELDS]
    started = []
    for ritm in _requests(client, item_id, RITM_OPEN, only, fields):
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


def reply_since_question(comments: list[dict[str, Any]]) -> str:
    """Requester comments posted after the last question of the process (comments newest first)."""
    replies = []
    for comment in comments:
        if comment["value"].startswith(REQUESTER_MARKER):
            break
        replies.append(comment["value"].strip())
    return "\n".join(reversed(replies))


def poll_replies(
    client: ServiceNowClient,
    correlate: CorrelateReply,
    item_id: str,
    only: list[str] | None = None,
) -> list[str]:
    answered = []
    for ritm in _requests(client, item_id, RITM_PENDING, only, ["sys_id", "number"]):
        comments = client.query(
            "sys_journal_field",
            f"element_id={ritm['sys_id']}^element=comments^ORDERBYDESCsys_created_on",
            ["value", "sys_created_on"],
            limit=10,
        )
        reply = reply_since_question(comments)
        if not reply:
            continue
        # Correlation fails while the instance is not yet waiting: the request stays pending and the
        # next poll tries again.
        correlate(ritm["number"], reply)
        client.set_state("sc_req_item", ritm["sys_id"], RITM_WORK_IN_PROGRESS)
        answered.append(ritm["number"])
    return answered


def poll_forever(
    client: ServiceNowClient,
    start: StartInstance,
    correlate: CorrelateReply,
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
            for number in poll_replies(client, correlate, item_id, only):
                log.info("Correlated the requester's reply for %s", number)
        except Exception:
            # Keep polling: a developer instance can be briefly unavailable (hibernation), and a
            # reply may arrive before its instance waits for it.
            log.exception("ServiceNow poll failed")
        stop.wait(interval)
