"""Read-only check of the ServiceNow and Jira access: python -m integrations.verify

Nothing is created or changed on either side. Exit code 0 only when both answer.
"""

import sys
from collections.abc import Callable

import httpx

from integrations.config import ConfigError, JiraSettings, ServiceNowSettings
from integrations.jira import JiraClient, JiraError
from integrations.servicenow import ServiceNowClient, ServiceNowError

SERVICENOW_TABLES = ("sc_cat_item", "sc_req_item", "change_request")


def check_servicenow(client: ServiceNowClient) -> str:
    for table in SERVICENOW_TABLES:
        client.query(table, fields=["sys_id"], limit=1)
    catalogs = client.list_catalogs()
    tables = ", ".join(SERVICENOW_TABLES)
    return f"tables {tables} readable, Service Catalog API answers ({len(catalogs)} catalogs)"


def check_jira(client: JiraClient, project_key: str) -> str:
    me = client.myself()
    project = client.get_project(project_key)
    client.issue_type_id(project["key"], "Task")
    return f"signed in as {me.get('displayName', '?')}, project {project['key']} has a Task type"


def run_check(name: str, check: Callable[[], str]) -> bool:
    try:
        detail = check()
    except ConfigError as exc:
        print(f"{name} KO  {exc}")
        return False
    except (ServiceNowError, JiraError) as exc:
        hint = {401: " (credentials rejected: check .env)", 404: " (not found: check .env)"}
        print(f"{name} KO  {exc}{hint.get(exc.status, '')}")
        return False
    except httpx.HTTPError as exc:
        print(f"{name} KO  network error: {exc}")
        return False
    print(f"{name} OK  {detail}")
    return True


def _servicenow() -> str:
    s = ServiceNowSettings.from_env()
    with ServiceNowClient(s.instance_url, s.username, s.password) as client:
        return f"{s.instance_url} as {s.username}: {check_servicenow(client)}"


def _jira() -> str:
    s = JiraSettings.from_env()
    with JiraClient(s.base_url, s.email, s.api_token) as client:
        return f"{s.base_url}: {check_jira(client, s.project_key)}"


def main() -> int:
    results = [run_check("ServiceNow", _servicenow), run_check("Jira", _jira)]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
