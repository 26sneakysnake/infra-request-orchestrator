from typing import Any

import pytest
from camunda_orchestration_sdk import JobError

from agents.qualification import Qualification
from workers import handlers
from workers.handlers import Deps


class FakeServiceNow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.changes: dict[str, dict[str, str]] = {}  # correlation_id -> change

    def query(self, table: str, query: str, fields: list[str], limit: int = 100) -> list:
        correlation = query.removeprefix("correlation_id=")
        return [self.changes[correlation]] if correlation in self.changes else []

    def add_comment(self, table: str, sys_id: str, text: str, internal: bool = False) -> None:
        self.calls.append(("comment", (sys_id, text, internal)))

    def set_state(self, table: str, sys_id: str, state: str) -> None:
        self.calls.append(("state", (sys_id, state)))

    def create_registered_change(self, fields: dict[str, str]) -> dict[str, str]:
        self.calls.append(("create_change", fields))
        change = {"sys_id": "chg-sys", "number": "CHG0030010"}
        self.changes[fields["correlation_id"]] = change
        return change

    def update_change(self, sys_id: str, fields: dict[str, str]) -> None:
        self.calls.append(("update_change", (sys_id, fields)))

    def close_change(self, sys_id: str, notes: str) -> None:
        self.calls.append(("close_change", sys_id))

    def record_url(self, table: str, sys_id: str) -> str:
        return f"https://sn.example/{table}.do?sys_id={sys_id}"


class FakeJira:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.labels: dict[str, str] = {}  # label -> issue key

    def create_issue(
        self, project: str, summary: str, description: str, labels: list[str] | None = None
    ) -> dict[str, str]:
        self.calls.append(("create", (project, summary)))
        for label in labels or []:
            self.labels[label] = "NETOPS-42"
        return {"key": "NETOPS-42"}

    def find_issues(self, jql: str) -> list[dict[str, str]]:
        return [{"key": key} for label, key in self.labels.items() if f'labels = "{label}"' in jql]

    def add_remote_link(self, key: str, url: str, title: str) -> None:
        self.calls.append(("link", (key, url)))

    def browse_url(self, key: str) -> str:
        return f"https://jira.example/browse/{key}"

    def add_comment(self, key: str, text: str) -> None:
        self.calls.append(("comment", key))

    def transition(self, key: str, category: str = "done") -> str:
        self.calls.append(("transition", (key, category)))
        return "Terminé"


class FakeCluster:
    def __init__(self, verification_ok: bool = True) -> None:
        self.verification_ok = verification_ok
        self.applied: list[dict[str, Any]] = []

    def apply(self, objects: list[dict[str, Any]]) -> list[str]:
        self.applied += objects
        return [f"{o['kind']}/{o['metadata']['name']}" for o in objects]

    def verify(
        self, namespace: str, service: str, port: int, allowed: list[str], all_zones: list[str]
    ):
        summary = "Règle réseau conforme" if self.verification_ok else "zone data : joignable"
        return {"ok": self.verification_ok, "checks": [], "summary": summary}


@pytest.fixture
def deps() -> Deps:
    return Deps(FakeServiceNow(), FakeJira(), "NETOPS", FakeCluster())  # type: ignore[arg-type]


VALIDATED = {
    "ritmSysId": "ritm-sys",
    "ritmNumber": "RITM0010042",
    "serviceName": "catalogue-api",
    "environment": "dev",
    "exposure": "interne",
    "namespace": "svc-catalogue-api-dev",
    "port": 8080,
    "zones": ["dev"],
    "changeClass": "standard",
}


def test_invalid_request_is_rejected_with_the_rules_and_closed_incomplete(deps: Deps) -> None:
    v = {"ritmSysId": "ritm-sys", "rejectionReasons": ["PORT-01 : le port 3389 (RDP) est interdit"]}
    assert handlers.reject_request(v, deps) == {"outcome": "rejected"}
    (_, (_, text, internal)), state = deps.servicenow.calls
    assert "PORT-01" in text and internal is False
    assert state == ("state", ("ritm-sys", "4"))


def test_cab_refusal_quotes_the_approver_comment(deps: Deps) -> None:
    v = {"ritmSysId": "ritm-sys", "decision": "reject", "approvalComment": "Pas de fenêtre"}
    handlers.reject_request(v, deps)
    text = deps.servicenow.calls[0][1][1]
    assert "refusé lors de l'approbation" in text and "Pas de fenêtre" in text


def test_change_then_jira_issue_are_linked_both_ways(deps: Deps) -> None:
    change = handlers.create_sn_change(VALIDATED, deps)
    assert change == {"changeSysId": "chg-sys", "changeNumber": "CHG0030010"}
    created = deps.servicenow.calls[0][1]
    assert (
        "pré-approuvé" in created["description"] and "RITM0010042" in created["short_description"]
    )

    jira = handlers.create_jira_issue({**VALIDATED, **change}, deps)
    assert jira["jiraKey"] == "NETOPS-42"
    assert (
        "link",
        ("NETOPS-42", "https://sn.example/change_request.do?sys_id=chg-sys"),
    ) in deps.jira.calls
    update = [c for c in deps.servicenow.calls if c[0] == "update_change"][0]
    assert "NETOPS-42" in update[1][1]["work_notes"]


def test_provision_applies_the_four_objects(deps: Deps) -> None:
    result = handlers.provision_k8s(VALIDATED, deps)
    assert [r.split("/")[0] for r in result["provisionedResources"]] == [
        "Namespace",
        "Deployment",
        "Service",
        "NetworkPolicy",
    ]


def test_failed_verification_raises_the_bpmn_error_with_details(deps: Deps) -> None:
    deps.cluster.verification_ok = False
    with pytest.raises(JobError) as excinfo:
        handlers.verify_exposure({**VALIDATED, "verificationAttempts": 1}, deps)
    assert excinfo.value.error_code == "VERIFICATION_FAILED"
    assert excinfo.value.variables["verificationAttempts"] == 2


def test_close_marks_jira_done_closes_change_and_request(deps: Deps) -> None:
    v = {
        **VALIDATED,
        "jiraKey": "NETOPS-42",
        "changeSysId": "chg-sys",
        "changeNumber": "CHG0030010",
        "verification": {"summary": "Règle réseau conforme"},
    }
    assert handlers.close_tickets(v, deps) == {"outcome": "exposed"}
    assert ("transition", ("NETOPS-42", "done")) in deps.jira.calls
    assert ("close_change", "chg-sys") in deps.servicenow.calls
    assert deps.servicenow.calls[-1] == ("state", ("ritm-sys", "3"))


def test_retried_jobs_do_not_duplicate_the_change_or_the_issue(deps: Deps) -> None:
    # Zeebe delivers jobs at least once: the second attempt must reuse what the first created.
    first_change = handlers.create_sn_change(VALIDATED, deps)
    second_change = handlers.create_sn_change(VALIDATED, deps)
    assert first_change == second_change
    assert [c[0] for c in deps.servicenow.calls].count("create_change") == 1

    v = {**VALIDATED, **first_change}
    assert handlers.create_jira_issue(v, deps) == handlers.create_jira_issue(v, deps)
    assert [c[0] for c in deps.jira.calls].count("create") == 1
    assert [c[0] for c in deps.servicenow.calls].count("update_change") == 1


def test_qualify_request_appends_the_reply_and_merges_the_form(deps: Deps) -> None:
    seen = {}

    def fake_qualify(text: str, form: dict) -> Qualification:
        seen["text"], seen["form"] = text, form
        answer = {
            "out_of_scope": False,
            "service_name": "facturation-api",
            "environment": "recette",
            "exposure": "interne",
            "ports": ["8443/tcp"],
            "source_networks": ["10.40.12.0/24"],
            "vm_required": False,
            "vm_size": None,
            "urgent": False,
            "missing": [],
            "questions": [],
            "citations": [],
            "summary": "s",
        }
        return Qualification(answer, "claude-sonnet-5-5", 1, {})

    deps.qualify = fake_qualify
    v = {
        "requestText": "Ouvrir facturation-api",
        "reply": "C'est pour la recette.",
        "serviceName": "",
    }
    result = handlers.qualify_request(v, deps)
    assert seen["text"].endswith("Réponse du demandeur : C'est pour la recette.")
    assert result["environment"] == "recette" and result["reply"] is None
    assert result["requestText"] == seen["text"]


def test_ask_requester_posts_the_questions_and_waits(deps: Deps) -> None:
    v = {"ritmSysId": "ritm-sys", "qualification": {"questions": ["Pour quel environnement ?"]}}
    assert handlers.ask_requester(v, deps) == {"questionsAsked": 1}
    (_, (_, text, internal)), state = deps.servicenow.calls
    assert text.startswith(handlers.REQUESTER_MARKER) and "Pour quel environnement ?" in text
    assert internal is False  # visible to the requester
    assert state == ("state", ("ritm-sys", "-5"))


class RemediationCluster(FakeCluster):
    def __init__(self) -> None:
        super().__init__()
        self.quotas_raised: list[str] = []

    def snapshot(self, namespace: str, service: str, request: dict, verification: dict) -> dict:
        return {
            "namespace": namespace,
            "resources": "NetworkPolicy x: ingress from zones ['bureautique']",
            "objects": {},
            "events": "",
            "logs": {},
            "verification": "zone dev : observée bloquée",
        }

    def raise_pod_quota(self, namespace: str) -> list[str]:
        self.quotas_raised.append(namespace)
        return ["ResourceQuota/pods-quota pods 0 -> 2"]


def test_diagnosis_is_stored_with_its_grounded_evidence(deps: Deps) -> None:
    from agents.loop import AgentRun

    deps.cluster = RemediationCluster()
    answer = {
        "cause": "network_policy",
        "action": "reapply_network_policy",
        "runbook": "RB-01",
        "confidence": "high",
        "explanation": "La politique n'autorise pas la zone dev.",
        "evidence": ["ingress from zones ['bureautique']", "pas dans l'instantané"],
    }
    deps.diagnose = lambda snapshot, service: AgentRun(answer, "claude-sonnet-5-5", 3, {})
    result = handlers.diagnose_failure({**VALIDATED, "verification": {"ok": False}}, deps)
    assert result["diagnosis"]["action"] == "reapply_network_policy"
    assert result["diagnosis"]["evidenceGrounded"] == "1/2"


@pytest.mark.parametrize(
    ("action", "kind"),
    [
        ("reapply_network_policy", "NetworkPolicy"),
        ("reapply_service", "Service"),
        ("reapply_deployment", "Deployment"),
    ],
)
def test_remediation_reapplies_only_the_approved_object(deps: Deps, action: str, kind: str) -> None:
    deps.cluster = RemediationCluster()
    v = {
        **VALIDATED,
        "changeSysId": "chg-sys",
        "jiraKey": "NETOPS-42",
        "diagnosis": {"action": action, "cause": "c", "explanation": "e"},
    }
    assert handlers.apply_remediation(v, deps) == {"remediationsApplied": [action]}
    assert [o["kind"] for o in deps.cluster.applied] == [kind]
    assert ("comment", "NETOPS-42") in deps.jira.calls


def test_quota_remediation_and_escalation(deps: Deps) -> None:
    deps.cluster = RemediationCluster()
    v = {**VALIDATED, "changeSysId": "c", "jiraKey": "NETOPS-42"}
    handlers.apply_remediation(
        {**v, "diagnosis": {"action": "raise_pod_quota", "cause": "quota"}}, deps
    )
    assert deps.cluster.quotas_raised == ["svc-catalogue-api-dev"]
    with pytest.raises(ValueError, match="not in the allowed list"):
        handlers.apply_remediation(
            {**v, "diagnosis": {"action": "escalate", "cause": "other"}}, deps
        )
