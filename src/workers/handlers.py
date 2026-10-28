"""One function per job type of the expose_service process.

Each function takes the process variables and the clients, and returns the variables to set. The
business logic lives here and is tested with fake clients, without the engine.

Zeebe delivers a job at least once (a worker can die after its side effects but before completing
the job), so the handlers that create records look for the record of a previous attempt first.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from camunda_orchestration_sdk import JobError

from agents.diagnosis import diagnose, grounded
from agents.loop import AgentRun
from agents.qualification import PROCESS_NAMES, Qualification, merge, qualify
from integrations.jira import JiraClient
from integrations.servicenow import (
    RITM_CLOSED_COMPLETE,
    RITM_CLOSED_INCOMPLETE,
    RITM_PENDING,
    ServiceNowClient,
)
from k8s.faults import inject, requested_fault
from k8s.manifests import exposure_objects
from netco.rules import load_rules, validate

Variables = dict[str, Any]
# Comments the process posts to the requester start with this marker; the poller treats any later
# comment without it as the requester's reply.
REQUESTER_MARKER = "[NetCo]"


class ClusterOps(Protocol):
    def apply(self, objects: list[dict[str, Any]]) -> list[str]: ...

    def verify(
        self,
        namespace: str,
        service: str,
        port: int,
        allowed_zones: list[str],
        all_zones: list[str],
    ) -> dict[str, Any]: ...

    def snapshot(
        self, namespace: str, service: str, request: dict[str, Any], verification: dict[str, Any]
    ) -> dict[str, Any]: ...

    def raise_pod_quota(self, namespace: str) -> list[str]: ...


@dataclass
class Deps:
    servicenow: ServiceNowClient
    jira: JiraClient
    jira_project: str
    cluster: ClusterOps
    qualify: Callable[[str, dict[str, Any]], Qualification] = qualify
    diagnose: Callable[[dict[str, Any], str], AgentRun] = diagnose


def _exposure(v: Variables) -> str:
    zones = ", ".join(v["zones"])
    return f"{v['serviceName']} ({v['environment']}), port {v['port']}/tcp, zones {zones}"


def qualify_request(v: Variables, deps: Deps) -> Variables:
    """The agent fills the form from the free text; a reply to a question joins the text."""
    text = str(v.get("requestText") or "")
    if v.get("reply"):
        text = f"{text}\n\nRéponse du demandeur : {v['reply']}"
    form = {name: v.get(name) for name in PROCESS_NAMES.values()}
    agent_form = {field: form[name] for field, name in PROCESS_NAMES.items()}
    variables = merge(form, deps.qualify(text, agent_form))
    return {**variables, "requestText": text, "reply": None}


def ask_requester(v: Variables, deps: Deps) -> Variables:
    questions = v["qualification"]["questions"]
    text = "\n".join(
        [f"{REQUESTER_MARKER} Il manque des informations pour traiter votre demande :"]
        + [f"- {question}" for question in questions]
        + ["Répondez simplement par un commentaire sur cette demande."]
    )
    deps.servicenow.add_comment("sc_req_item", v["ritmSysId"], text)
    deps.servicenow.set_state("sc_req_item", v["ritmSysId"], RITM_PENDING)
    return {"questionsAsked": int(v.get("questionsAsked") or 0) + 1}


def validate_request(v: Variables, deps: Deps) -> Variables:
    return validate(v).as_variables()


def reject_request(v: Variables, deps: Deps) -> Variables:
    if v.get("decision") == "reject":
        comment = str(v.get("approvalComment") or "").strip()
        lines = ["Changement refusé lors de l'approbation (CAB)."]
        lines += [f"Motif : {comment}"] if comment else []
    else:
        lines = ["Demande refusée par le processus d'exposition de service NetCo :"]
        lines += [f"- {reason}" for reason in v.get("rejectionReasons") or []]
    deps.servicenow.add_comment("sc_req_item", v["ritmSysId"], "\n".join(lines))
    deps.servicenow.set_state("sc_req_item", v["ritmSysId"], RITM_CLOSED_INCOMPLETE)
    return {"outcome": "rejected"}


def create_sn_change(v: Variables, deps: Deps) -> Variables:
    # The request number is the correlation id: a retried job finds the change it already created.
    existing = deps.servicenow.query(
        "change_request", f"correlation_id={v['ritmNumber']}", ["sys_id", "number"], limit=1
    )
    if existing:
        return {"changeSysId": existing[0]["sys_id"], "changeNumber": existing[0]["number"]}
    if v["changeClass"] == "standard":
        approval = "Changement standard, pré-approuvé (CHG-01)."
    else:
        comment = str(v.get("approvalComment") or "").strip()
        approval = f"Changement {v['changeClass']}, approuvé dans Camunda Tasklist (CHG-02)."
        approval += f" Commentaire : {comment}" if comment else ""
    description = "\n".join(
        [
            f"Demande {v['ritmNumber']} : exposition {v['exposure']} de {_exposure(v)}.",
            f"Namespace Kubernetes : {v['namespace']}.",
            approval,
            "Exécution automatisée par l'orchestrateur Camunda (processus expose_service).",
        ]
    )
    change = deps.servicenow.create_registered_change(
        {
            "short_description": f"Exposition de {v['serviceName']} ({v['environment']}) - "
            f"{v['ritmNumber']}",
            "description": description,
            "correlation_id": v["ritmNumber"],
            "correlation_display": "Demande ServiceNow",
        }
    )
    deps.servicenow.add_comment(
        "sc_req_item", v["ritmSysId"], f"Changement {change['number']} enregistré.", internal=True
    )
    return {"changeSysId": change["sys_id"], "changeNumber": change["number"]}


def create_jira_issue(v: Variables, deps: Deps) -> Variables:
    change_url = deps.servicenow.record_url("change_request", v["changeSysId"])
    # The request number is a label: a retried job finds the issue it already created.
    label = v["ritmNumber"]
    existing = deps.jira.find_issues(f'project = "{deps.jira_project}" AND labels = "{label}"')
    if existing:
        key = existing[0]["key"]
    else:
        key = deps.jira.create_issue(
            deps.jira_project,
            f"Exposer {v['serviceName']} ({v['environment']}) - {v['ritmNumber']}",
            f"Mise en œuvre de l'exposition de {_exposure(v)}.\n\n"
            f"Demande ServiceNow {v['ritmNumber']}, changement {v['changeNumber']} "
            f"(classe {v['changeClass']}).\n\nTicket créé et suivi par l'orchestrateur Camunda.",
            labels=["netco", label],
        )["key"]
        deps.servicenow.update_change(
            v["changeSysId"],
            {"work_notes": f"Ticket Jira de mise en œuvre : {key} ({deps.jira.browse_url(key)})"},
        )
    deps.jira.add_remote_link(key, change_url, f"{v['changeNumber']} (changement ServiceNow)")
    return {"jiraKey": key, "jiraUrl": deps.jira.browse_url(key)}


def _objects(v: Variables) -> list[dict[str, Any]]:
    """The exposure computed from the validated request: what provisioning and remediation apply."""
    return exposure_objects(
        v["namespace"], v["serviceName"], v["environment"], v["port"], v["zones"]
    )


def provision_k8s(v: Variables, deps: Deps) -> Variables:
    objects = _objects(v)
    fault = requested_fault(v["serviceName"])  # demos and the e2e scenario only
    if fault:
        target = {k: v[n] for k, n in (("service", "serviceName"), ("namespace", "namespace"))}
        objects = inject(objects, fault, {**target, "port": v["port"], "zones": v["zones"]})
    result: Variables = {"provisionedResources": deps.cluster.apply(objects)}
    if fault:
        result["injectedFault"] = fault
    return result


def diagnose_failure(v: Variables, deps: Deps) -> Variables:
    """The agent reads a read-only snapshot of the namespace and proposes one allowed action."""
    request = {"service": v["serviceName"], "port": v["port"], "zones": v["zones"]}
    snapshot = deps.cluster.snapshot(
        v["namespace"], v["serviceName"], request, v.get("verification") or {}
    )
    run = deps.diagnose(snapshot, v["serviceName"])
    answer = run.answer
    evidence = list(answer.get("evidence") or [])
    found = sum(grounded(e, snapshot) for e in evidence)
    return {
        "diagnosis": {
            "cause": answer["cause"],
            "action": answer["action"],
            "runbook": answer.get("runbook"),
            "confidence": answer.get("confidence"),
            "explanation": answer.get("explanation", ""),
            "evidence": evidence,
            "evidenceGrounded": f"{found}/{len(evidence)}",
            "model": run.model,
            "turns": run.turns,
            "costUsd": round(run.cost_usd, 6),
        }
    }


# The only changes the process may make after a diagnosis, each validated by a human first.
REMEDIATIONS: dict[str, Callable[[Variables, Deps], list[str]]] = {
    "reapply_network_policy": lambda v, deps: deps.cluster.apply([_objects(v)[3]]),
    "reapply_service": lambda v, deps: deps.cluster.apply([_objects(v)[2]]),
    "reapply_deployment": lambda v, deps: deps.cluster.apply([_objects(v)[1]]),
    "raise_pod_quota": lambda v, deps: deps.cluster.raise_pod_quota(v["namespace"]),
}


def apply_remediation(v: Variables, deps: Deps) -> Variables:
    diagnosis = v["diagnosis"]
    action = diagnosis["action"]
    if action not in REMEDIATIONS:
        raise ValueError(f"action {action!r} is not in the allowed list")
    done = REMEDIATIONS[action](v, deps)
    explanation = diagnosis.get("explanation", "")
    note = (
        f"Remédiation appliquée après validation humaine : {action} ({', '.join(done)}). "
        f"Cause diagnostiquée par l'agent : {diagnosis['cause']}. {explanation}"
    )
    deps.servicenow.update_change(v["changeSysId"], {"work_notes": note})
    deps.jira.add_comment(v["jiraKey"], note)
    return {"remediationsApplied": [*(v.get("remediationsApplied") or []), action]}


def verify_exposure(v: Variables, deps: Deps) -> Variables:
    attempts = int(v.get("verificationAttempts") or 0) + 1
    result = deps.cluster.verify(
        v["namespace"], v["serviceName"], v["port"], v["zones"], list(load_rules()["zones"])
    )
    variables = {"verification": result, "verificationAttempts": attempts}
    if not result["ok"]:
        # Business failure, modelled in BPMN: a human looks at it (an agent proposes a fix in P4).
        raise JobError("VERIFICATION_FAILED", message=result["summary"], variables=variables)
    return variables


def close_tickets(v: Variables, deps: Deps) -> Variables:
    summary = f"Service exposé : {_exposure(v)}. Vérification : {v['verification']['summary']}."
    deps.jira.add_comment(v["jiraKey"], summary)
    deps.jira.transition(v["jiraKey"], "done")
    deps.servicenow.close_change(v["changeSysId"], summary)
    deps.servicenow.add_comment(
        "sc_req_item",
        v["ritmSysId"],
        f"{summary}\nChangement {v['changeNumber']}, ticket Jira {v['jiraKey']}.",
    )
    deps.servicenow.set_state("sc_req_item", v["ritmSysId"], RITM_CLOSED_COMPLETE)
    return {"outcome": "exposed"}


HANDLERS: dict[str, Callable[[Variables, Deps], Variables]] = {
    "qualify-request": qualify_request,
    "ask-requester": ask_requester,
    "validate-request": validate_request,
    "reject-request": reject_request,
    "create-sn-change": create_sn_change,
    "create-jira-issue": create_jira_issue,
    "provision-k8s": provision_k8s,
    "verify-exposure": verify_exposure,
    "diagnose-failure": diagnose_failure,
    "apply-remediation": apply_remediation,
    "close-tickets": close_tickets,
}
