import json

import pytest

from agents.documentation import MARKERS, check_values, facts, fill, template

VARIABLES = {
    "ritmNumber": "RITM0010042",
    "changeNumber": "CHG0030010",
    "jiraKey": "NETOPS-42",
    "serviceName": "reporting-db",
    "environment": "recette",
    "exposure": "interne",
    "sourceNetworks": "10.30.0.0/16",
    "namespace": "svc-reporting-db-recette",
    "port": 5432,
    "zones": ["data"],
    "sensitivePort": True,
    "changeClass": "normal",
    "approvalComment": "OK pour la recette.",
    "provisionedResources": ["Namespace/svc-reporting-db-recette", "Service/reporting-db"],
    "verification": {
        "ok": True,
        "summary": "Règle réseau conforme",
        "checks": [
            {"zone": "data", "expected": True, "reachable": True, "ok": True},
            {"zone": "dev", "expected": False, "reachable": False, "ok": True},
        ],
    },
    "verificationAttempts": 1,
    "vmSize": "m",
    "vm": {
        "name": "reporting-db-recette-vm",
        "folder": "netco/recette",
        "cpu": 2,
        "memoryMb": 4096,
        "network": "VM Network",
        "powerState": "poweredOn",
        "uuid": "98c179c3-003b-5b4a-928d-7686ed2a1e7a",
        "platform": "vcsim (simulateur de l'API vSphere)",
    },
}
INCIDENT = {
    "diagnosis": {
        "cause": "network_policy",
        "action": "reapply_network_policy",
        "runbook": "RB-01",
        "explanation": "La NetworkPolicy autorise bureautique au lieu de data.",
    },
    "remediationDecision": "apply",
    "remediationComment": "OK",
    "remediationsApplied": ["reapply_network_policy"],
    "verificationAttempts": 2,
}


def test_facts_hold_no_value_that_changes_between_runs() -> None:
    text = json.dumps(facts(VARIABLES), ensure_ascii=False)
    # Same prompt on every run: ticket numbers and the date are markers, the VM uuid is left out.
    for value in ("RITM0010042", "CHG0030010", "NETOPS-42", VARIABLES["vm"]["uuid"]):
        assert value not in text
    for marker in MARKERS:
        assert f"{{{{{marker}}}}}" in text


@pytest.mark.parametrize(
    "variables",
    [
        {k: v for k, v in VARIABLES.items() if k not in ("vm", "vmSize")},
        VARIABLES,
        {**VARIABLES, **INCIDENT},
    ],
)
def test_template_passes_the_check_and_fills_every_marker(variables: dict) -> None:
    dossier = facts(variables)
    for text in template(dossier).values():
        assert check_values(text, dossier) == []
        filled = fill(text, {m: f"<{m}>" for m in MARKERS})
        assert "{{" not in filled and "}}" not in filled


def test_template_mentions_the_vm_and_the_incident_only_when_present() -> None:
    plain = template(facts({k: v for k, v in VARIABLES.items() if k not in ("vm", "vmSize")}))
    assert "VM" not in plain["fiche_service"]
    full = template(facts({**VARIABLES, **INCIDENT}))
    assert "`reporting-db-recette-vm`" in full["fiche_service"]
    assert "`4096` Mo" in full["fiche_service"]
    assert "`reapply_network_policy`" in full["compte_rendu"]


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("Accès depuis `10.30.0.0/16`.", None),
        ("Accès depuis 10.99.0.0/16.", "valeur absente des faits : 10.99.0.0/16"),
        ("Port 8443/tcp ouvert.", "valeur absente des faits : 8443/tcp"),
        ("Namespace `svc-reporting-db-prod`.", "valeur absente des faits : svc-reporting-db-prod"),
        ("Voir `kubectl get pods`.", "valeur absente des faits : kubectl get pods"),
        ("VM de 4 Go.", "taille absente des faits : 4"),
        ("VM de 4 096 Mo et 2 vCPU.", None),
        ("Demande RITM0010042.", "numéro écrit en dur au lieu d'un marqueur : RITM0010042"),
        ("Ticket NETOPS-42.", "valeur absente des faits : NETOPS-42"),
        ("Runbook RB-01, règle CHG-02.", None),
        ("Responsable {{owner}}.", "marqueur inconnu : {{owner}}"),
        ("Déployé sur OpenShift.", "terme interdit : openshift"),
        ("Service disponible en production.", "terme interdit : en production"),
    ],
)
def test_check_values_flags_any_value_absent_from_the_facts(text: str, problem: str | None) -> None:
    problems = check_values(text, facts({**VARIABLES, **INCIDENT}))
    assert problems == ([problem] if problem else [])
