from types import SimpleNamespace

import pytest

from agents.diagnosis import CAUSES, grounded, run_tool
from evals.diagnosis import score_case
from k8s.faults import FAULTS, inject, requested_fault
from k8s.manifests import exposure_objects
from k8s.observe import _clean, _waiting_reason
from workers.handlers import REMEDIATIONS

REQUEST = {"service": "inventaire-api", "namespace": "svc-inventaire-api-dev", "port": 8080}
REQUEST["zones"] = ["dev"]
OBJECTS = exposure_objects("svc-inventaire-api-dev", "inventaire-api", "dev", 8080, ["dev"])


def _kind(objects: list[dict], kind: str) -> dict:
    return next(o for o in objects if o["kind"] == kind)


def test_every_fault_changes_the_clean_exposure_and_maps_to_an_allowed_action() -> None:
    for variant, fault in FAULTS.items():
        broken = inject(OBJECTS, variant, REQUEST)
        assert broken != OBJECTS, variant
        # Every injected fault has an automatic fix the process knows how to apply.
        assert fault.action in REMEDIATIONS and fault.cause in CAUSES, variant
    # inject() works on a copy: the clean exposure is left untouched.
    assert OBJECTS == exposure_objects(
        "svc-inventaire-api-dev", "inventaire-api", "dev", 8080, ["dev"]
    )


def test_network_policy_fault_opens_another_zone() -> None:
    policy = _kind(inject(OBJECTS, "network_policy_zone", REQUEST), "NetworkPolicy")
    zones = policy["spec"]["ingress"][0]["from"][0]["namespaceSelector"]["matchExpressions"][0]
    assert zones["values"] == ["bureautique"]


def test_quota_fault_comes_before_the_deployment() -> None:
    kinds = [o["kind"] for o in inject(OBJECTS, "quota_full", REQUEST)]
    assert kinds[:3] == ["Namespace", "Pod", "ResourceQuota"]
    assert kinds.index("ResourceQuota") < kinds.index("Deployment")


def test_fault_is_injected_only_for_the_named_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NETCO_INJECT_FAULT", "image_tag:inventaire-api")
    assert requested_fault("inventaire-api") == "image_tag"
    assert requested_fault("catalogue-api") is None
    monkeypatch.setenv("NETCO_INJECT_FAULT", "nope:inventaire-api")
    with pytest.raises(ValueError, match="unknown fault"):
        requested_fault("inventaire-api")


def test_snapshot_text_is_canonical() -> None:
    names = {"inventaire-api-79f87cc85f-x2k9p": "inventaire-api-pod-1"}
    text = (
        "2026/10/28 15:28:33 Pod inventaire-api-79f87cc85f-x2k9p pulled in 1.234s from "
        "10.96.0.10:53, replicaset inventaire-api-79f87cc85f, pod inventaire-api-6d4b9c8f7d-abcde"
    )
    assert _clean(text, names, ["inventaire-api"]) == (
        "Pod inventaire-api-pod-1 pulled in <durée> from <ip>, replicaset "
        "inventaire-api-replicaset, pod inventaire-api-pod"
    )


def test_image_pull_reasons_are_merged() -> None:
    def pod(reason: str) -> SimpleNamespace:
        waiting = SimpleNamespace(reason=reason)
        status = SimpleNamespace(state=SimpleNamespace(waiting=waiting))
        return SimpleNamespace(status=SimpleNamespace(container_statuses=[status]))

    assert _waiting_reason(pod("ErrImagePull")) == "ImagePullBackOff"
    assert _waiting_reason(pod("ContainerCreating")) == "ContainerCreating"


SNAPSHOT = {
    "namespace": "svc-inventaire-api-dev",
    "resources": "Service inventaire-api: ports 8080 -> targetPort 8081, ready endpoints 1",
    "objects": {"Service/inventaire-api": "ports:\n- port: 8080\n  targetPort: 8081"},
    "events": "(aucun événement Warning)",
    "logs": {"inventaire-api-pod-1": "Starting up on port 8080"},
    "verification": "zone dev : attendue joignable, observée bloquée (ÉCHEC)",
}


def test_tools_only_read_the_snapshot_and_the_runbooks() -> None:
    assert "targetPort: 8081" in run_tool(
        SNAPSHOT, "describe", {"kind": "Service", "name": "inventaire-api"}
    )
    assert "Objet inconnu" in run_tool(SNAPSHOT, "describe", {"kind": "Pod", "name": "x"})
    assert (
        run_tool(SNAPSHOT, "get_logs", {"pod": "inventaire-api-pod-1"})
        == "Starting up on port 8080"
    )
    assert "RB-04" in run_tool(SNAPSHOT, "search_runbooks", {"query": "image ImagePullBackOff"})


def test_evidence_must_come_from_the_snapshot() -> None:
    assert grounded("targetPort 8081", SNAPSHOT)
    assert grounded("observée bloquée", SNAPSHOT)
    assert not grounded("la NetworkPolicy n'autorise que la zone bureautique", SNAPSHOT)


def test_diagnosis_scoring() -> None:
    case = {
        "id": "D03",
        "fault": "service_target_port",
        "expected": {"cause": "service_port", "action": "reapply_service"},
        "snapshot": SNAPSHOT,
    }
    answer = {
        "cause": "service_port",
        "action": "escalate",
        "runbook": "RB-02",
        "confidence": "high",
        "evidence": ["targetPort 8081", "invented"],
    }
    scored = score_case(case, answer)
    assert scored["cause_ok"] and not scored["action_ok"]
    assert (scored["evidence"], scored["evidence_grounded"]) == (2, 1)
