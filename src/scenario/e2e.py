"""End-to-end scenario against the real stack and tools: python -m scenario.e2e

1. The engine evaluates the change_class decision on the reference cases.
2. Three requests are ordered in ServiceNow: a standard one, a normal one, and a free-text one
   without environment.
3. The workers start, restricted to these requests (NETCO_POLL_ONLY).
4. The normal change is approved in place of a CAB member (simulated approval, recorded as such),
   and the scenario answers the agent's question as the requester would, in a ServiceNow comment.
5. Every instance must complete; then Jira, the ServiceNow change and the request are checked.

Request texts are fixed so that the agent's prompts match the recorded cassettes (CI replays them).
Writes out/e2e-report.json. Exit code 0 only when every check passes.
"""

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import camunda_orchestration_sdk as sdk

from integrations.config import JiraSettings, ServiceNowSettings
from integrations.jira import JiraClient
from integrations.seed import ensure_catalog_item, order_request
from integrations.servicenow import (
    CHANGE_CLOSED,
    RITM_CLOSED_COMPLETE,
    RITM_PENDING,
    ServiceNowClient,
)
from k8s.faults import FAULTS
from scenario.camunda import camunda_client

OUT = Path(__file__).resolve().parents[2] / "out"

DMN_CASES = [
    (
        {"urgent": True, "environment": "dev", "exposure": "interne", "sensitivePort": False},
        "urgent",
    ),
    (
        {"urgent": False, "environment": "prod", "exposure": "interne", "sensitivePort": False},
        "normal",
    ),
    (
        {"urgent": False, "environment": "dev", "exposure": "externe", "sensitivePort": False},
        "normal",
    ),
    (
        {"urgent": False, "environment": "recette", "exposure": "interne", "sensitivePort": True},
        "normal",
    ),
    (
        {"urgent": False, "environment": "dev", "exposure": "interne", "sensitivePort": False},
        "standard",
    ),
]

# (expected change class, catalog variables, reply to the agent's question, injected fault)
FAULTY_SERVICE, FAULT = "inventaire-api", "network_policy_zone"
REQUESTS = [
    (
        "standard",
        {
            "service_name": "catalogue-api",
            "environment": "dev",
            "ports": "8080/tcp",
            "source_networks": "10.20.0.0/16",
            "exposure": "interne",
            "request_text": "Exposer l'API catalogue en dev, en interne, pour les développeurs.",
        },
        None,
        None,
    ),
    (
        "normal",
        {
            "service_name": "reporting-db",
            "environment": "recette",
            "ports": "5432/tcp",
            "source_networks": "10.30.0.0/16",
            "exposure": "interne",
            "request_text": "Ouvrir PostgreSQL en recette au réseau data uniquement.",
        },
        None,
        None,
    ),
    (
        "standard",
        {
            "request_text": "Il faudrait ouvrir le service facturation-api sur le 8443 pour "
            "l'équipe finance (10.40.12.0/24), en interne.",
        },
        "C'est pour la recette.",
        None,
    ),
    (
        "standard",
        {
            "service_name": FAULTY_SERVICE,
            "environment": "dev",
            "ports": "8080/tcp",
            "source_networks": "10.20.0.0/16",
            "exposure": "interne",
            "request_text": "Exposer inventaire-api en dev, en interne, pour les développeurs.",
        },
        None,
        FAULT,
    ),
]


def wait_for[T](probe: Callable[[], T | None], timeout: float, what: str, interval: float = 3) -> T:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(interval)
    raise TimeoutError(f"timed out after {timeout:.0f} s waiting for {what}")


def evaluate_dmn(client: sdk.CamundaClient) -> list[dict[str, Any]]:
    results = []
    for inputs, expected in DMN_CASES:
        evaluation = client.evaluate_decision(
            data=sdk.DecisionEvaluationByID(
                decision_definition_id="change_class",
                variables=sdk.DecisionEvaluationByIdVariables.from_dict(inputs),
            )
        )
        got = json.loads(evaluation.output)
        results.append({"inputs": inputs, "expected": expected, "got": got, "ok": got == expected})
    return results


def find_instance(client: sdk.CamundaClient, business_id: str) -> Any:
    query = sdk.ProcessInstanceSearchQuery(
        filter_=sdk.ProcessInstanceFilter(business_id=business_id)
    )
    items = client.search_process_instances(data=query).items or []
    return items[0] if items else None


def instance_variables(client: sdk.CamundaClient, instance_key: str) -> dict[str, Any]:
    query = sdk.VariableSearchQuery(filter_=sdk.VariableFilter(process_instance_key=instance_key))
    return {v.name: json.loads(v.value) for v in client.search_variables(data=query).items or []}


def approve(client: sdk.CamundaClient, instance_key: str) -> None:
    def open_task() -> Any:
        query = sdk.UserTaskSearchQuery(
            filter_=sdk.UserTaskFilter(
                process_instance_key=instance_key, element_id="Task_ApproveChange"
            )
        )
        tasks = [
            t
            for t in client.search_user_tasks(data=query).items or []
            if str(t.state).endswith("CREATED")
        ]
        return tasks[0] if tasks else None

    task = wait_for(open_task, 120, "the approval task")
    decision = {
        "decision": "approve",
        "approvalComment": "Approbation simulée par le scénario e2e (aucun humain impliqué).",
    }
    client.complete_user_task(
        task.user_task_key,
        data=sdk.UserTaskCompletionRequest(
            variables=sdk.UserTaskCompletionRequestVariables.from_dict(decision)
        ),
    )


def answer_question(sn: ServiceNowClient, request: dict[str, Any]) -> None:
    """Wait for the agent's question (request pending), then reply as the requester would."""

    def pending() -> bool:
        ritm = sn.query("sc_req_item", f"number={request['ritm']}", ["state"])[0]
        return ritm["state"] == RITM_PENDING

    wait_for(pending, 120, f"the question on {request['ritm']}")
    sn.add_comment("sc_req_item", request["ritm_sys_id"], request["reply"])


def validate_remediation(client: sdk.CamundaClient, instance_key: str) -> dict[str, Any]:
    """Approve the agent's proposed action in place of an operator; return the diagnosis."""

    def open_task() -> Any:
        query = sdk.UserTaskSearchQuery(
            filter_=sdk.UserTaskFilter(
                process_instance_key=instance_key, element_id="Task_ValidateRemediation"
            )
        )
        tasks = [
            t
            for t in client.search_user_tasks(data=query).items or []
            if str(t.state).endswith("CREATED")
        ]
        return tasks[0] if tasks else None

    task = wait_for(open_task, 300, "the remediation validation task")
    diagnosis = instance_variables(client, instance_key)["diagnosis"]
    decision = {
        "remediationDecision": "apply",
        "remediationComment": "Validation simulée par le scénario e2e (aucun humain impliqué).",
    }
    client.complete_user_task(
        task.user_task_key,
        data=sdk.UserTaskCompletionRequest(
            variables=sdk.UserTaskCompletionRequestVariables.from_dict(decision)
        ),
    )
    return diagnosis


def finished(client: sdk.CamundaClient, business_id: str) -> Any:
    instance = find_instance(client, business_id)
    if instance is not None and instance.has_incident:
        raise RuntimeError(
            f"incident on the instance of {business_id}: see Operate and the worker log"
        )
    if instance is not None and str(instance.state).endswith("COMPLETED"):
        return instance
    return None


def main() -> int:
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    OUT.mkdir(exist_ok=True)
    report: dict[str, Any] = {"run": run_id, "started_at": datetime.now(UTC).isoformat()}
    camunda = camunda_client()

    report["dmn"] = evaluate_dmn(camunda)
    print(f"DMN: {sum(c['ok'] for c in report['dmn'])}/{len(report['dmn'])} cases as expected")

    sn_settings, jira_settings = ServiceNowSettings.from_env(), JiraSettings.from_env()
    sn = ServiceNowClient(sn_settings.instance_url, sn_settings.username, sn_settings.password)
    jira = JiraClient(jira_settings.base_url, jira_settings.email, jira_settings.api_token)
    item = ensure_catalog_item(sn)
    ordered = []
    for expected_class, variables, reply, fault in REQUESTS:
        created = order_request(sn, item, {**variables, "urgent": False})
        ordered.append(
            {
                "expected_class": expected_class,
                "reply": reply,
                "fault": fault,
                "ritm": created["ritm"],
                "ritm_sys_id": created["ritm_sys_id"],
                "t0": time.monotonic(),
            }
        )
        detail = ", free text" if reply else f", injected fault {fault}" if fault else ""
        print(f"Ordered {created['ritm']} ({expected_class}{detail})")

    log = (OUT / "e2e-workers.log").open("w", encoding="utf-8")
    env = {
        **os.environ,
        "NETCO_POLL_ONLY": ",".join(r["ritm"] for r in ordered),
        "NETCO_INJECT_FAULT": f"{FAULT}:{FAULTY_SERVICE}",
    }
    workers = subprocess.Popen([sys.executable, "-m", "workers"], env=env, stdout=log, stderr=log)
    results = []
    try:
        for request in ordered:
            ritm_number = request["ritm"]
            instance = wait_for(
                lambda n=ritm_number: find_instance(camunda, n), 90, f"{ritm_number} instance"
            )
            request["instance"] = str(instance.process_instance_key)
            if request["reply"]:
                answer_question(sn, request)
                print(f"Answered the agent's question on {ritm_number}: {request['reply']!r}")
            if request["expected_class"] != "standard":
                approve(camunda, request["instance"])
                print(f"Approved {request['ritm']} (simulated CAB approval)")
            if request["fault"]:
                request["diagnosis"] = validate_remediation(camunda, request["instance"])
                d = request["diagnosis"]
                print(f"Remediation approved on {ritm_number}: {d['cause']} -> {d['action']}")
        for request in ordered:
            ritm_number = request["ritm"]
            wait_for(lambda n=ritm_number: finished(camunda, n), 300, f"{ritm_number} to complete")
            variables = instance_variables(camunda, request["instance"])
            change = sn.query("change_request", f"number={variables['changeNumber']}", ["state"])[0]
            ritm = sn.query("sc_req_item", f"number={request['ritm']}", ["state"])[0]
            issue = jira.get_issue(variables["jiraKey"], fields=["status"])
            checks = {
                "change_class": variables["changeClass"] == request["expected_class"],
                "verification": variables["verification"]["ok"],
                "servicenow_change_closed": change["state"] == CHANGE_CLOSED,
                "servicenow_request_closed": ritm["state"] == RITM_CLOSED_COMPLETE,
                "jira_done": issue["fields"]["status"]["statusCategory"]["key"] == "done",
            }
            if request["reply"]:
                checks["agent_asked_the_requester"] = variables.get("questionsAsked", 0) >= 1
            if request["fault"]:
                expected = FAULTS[request["fault"]]
                checks["diagnosis_cause"] = request["diagnosis"]["cause"] == expected.cause
                checks["diagnosis_action"] = request["diagnosis"]["action"] == expected.action
                checks["remediation_applied"] = variables.get("remediationsApplied") == [
                    expected.action
                ]
                checks["verified_after_remediation"] = variables.get("verificationAttempts") == 2
            results.append(
                {
                    "ritm": request["ritm"],
                    "instance": request["instance"],
                    "change": variables["changeNumber"],
                    "jira": variables["jiraKey"],
                    "change_class": variables["changeClass"],
                    "seconds_to_complete": round(time.monotonic() - request["t0"], 1),
                    "checks": checks,
                    "ok": all(checks.values()),
                }
            )
            print(f"{request['ritm']}: {'OK' if results[-1]['ok'] else 'KO'} {checks}")
    finally:
        workers.terminate()
        workers.wait(timeout=30)
        log.close()
        sn.close()
        jira.close()

    report["requests"] = results
    report["ok"] = all(c["ok"] for c in report["dmn"]) and all(r["ok"] for r in results)
    (OUT / "e2e-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"e2e {'OK' if report['ok'] else 'KO'}: report in out/e2e-report.json")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
