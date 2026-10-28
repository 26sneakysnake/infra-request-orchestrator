"""Create the NetCo catalog item if needed, then order the synthetic requests.

Usage: python -m integrations.seed. Each run orders new requests, on purpose: fresh demo data.
"""

import sys
from pathlib import Path
from typing import Any

import yaml

from integrations.config import ServiceNowSettings
from integrations.servicenow import ServiceNowClient, ServiceNowError

CATALOG = "Service Catalog"
CATEGORY = "NetCo"
CATALOG_ITEM = "Exposition de service (NetCo)"
REQUESTS_FILE = Path(__file__).resolve().parents[2] / "seed" / "requests.yaml"

# Variable types, as listed in the choices of question.type on the instance.
MULTI_LINE_TEXT, SINGLE_LINE_TEXT, CHECKBOX = "2", "6", "7"
VARIABLES = [
    ("request_text", "Décrivez votre besoin", MULTI_LINE_TEXT),
    ("service_name", "Nom du service", SINGLE_LINE_TEXT),
    ("environment", "Environnement (dev, recette, prod)", SINGLE_LINE_TEXT),
    ("ports", "Ports et protocoles (ex. 443/tcp)", SINGLE_LINE_TEXT),
    ("source_networks", "Réseaux sources autorisés (CIDR)", SINGLE_LINE_TEXT),
    ("exposure", "Exposition (interne ou externe)", SINGLE_LINE_TEXT),
    ("vm_required", "Une VM est-elle nécessaire ?", CHECKBOX),
    ("vm_size", "Taille de la VM (S, M ou L)", SINGLE_LINE_TEXT),
    ("urgent", "Changement urgent (incident en cours)", CHECKBOX),
]


def _find_or_create(
    client: ServiceNowClient, table: str, query: str, fields: dict[str, str]
) -> str:
    found = client.query(table, query, fields=["sys_id"], limit=1)
    return found[0]["sys_id"] if found else client.create(table, fields)["sys_id"]


def ensure_catalog_item(client: ServiceNowClient) -> str:
    """Return the sys_id of the catalog item, creating it and any missing variable."""
    catalogs = client.query("sc_catalog", f"title={CATALOG}", fields=["sys_id"], limit=1)
    if not catalogs:
        raise ServiceNowError(404, f"catalog {CATALOG!r} not found")
    catalog = catalogs[0]["sys_id"]
    category = _find_or_create(
        client,
        "sc_category",
        f"title={CATEGORY}^sc_catalog={catalog}",
        {"title": CATEGORY, "sc_catalog": catalog},
    )
    item = _find_or_create(
        client,
        "sc_cat_item",
        f"name={CATALOG_ITEM}",
        {
            "name": CATALOG_ITEM,
            "short_description": "Demande d'exposition d'un service sur le réseau NetCo (fictive)",
            "sc_catalogs": catalog,
            "category": category,
        },
    )
    existing = {v["name"] for v in client.query("item_option_new", f"cat_item={item}", ["name"])}
    for order, (name, question, kind) in enumerate(VARIABLES, start=1):
        if name not in existing:
            client.create(
                "item_option_new",
                {
                    "cat_item": item,
                    "name": name,
                    "question_text": question,
                    "type": kind,
                    "order": str(order * 100),
                },
            )
    return item


def as_variable(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def order_request(client: ServiceNowClient, item: str, variables: dict[str, Any]) -> dict[str, str]:
    """Order one request; return the numbers and sys_ids of the REQ and of its RITM."""
    order = client.order_catalog_item(item, {k: as_variable(v) for k, v in variables.items()})
    request_id = order.get("request_id") or order["sys_id"]
    ritms = client.query("sc_req_item", f"request={request_id}", ["sys_id", "number"], limit=1)
    if not ritms:
        raise ServiceNowError(404, f"no RITM found for {order.get('number', request_id)}")
    return {
        "request": order.get("request_number") or order["number"],
        "ritm": ritms[0]["number"],
        "ritm_sys_id": ritms[0]["sys_id"],
    }


def load_requests(path: Path = REQUESTS_FILE) -> list[dict[str, Any]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> int:
    s = ServiceNowSettings.from_env()
    with ServiceNowClient(s.instance_url, s.username, s.password) as client:
        item = ensure_catalog_item(client)
        requests = load_requests()
        for request in requests:
            created = order_request(client, item, request["variables"])
            print(f"{created['request']}  {created['ritm']}  {request['title']}")
    print(f"{len(requests)} requests ordered from catalog item {CATALOG_ITEM!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
