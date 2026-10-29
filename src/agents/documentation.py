"""Documentation agent: writes the service sheet and the change report from the process facts.

The agent only rewrites the facts it receives. A deterministic check then extracts every concrete
value of its Markdown (backticks, addresses, ports, identifiers, sizes) and refuses the text if one
of them is not in the facts; a refused text is replaced by a template, so a closed change always
has its documents. Ticket numbers and the date change at every run: the agent sees them as markers
that the worker fills in afterwards, so the prompt is the same on every run (replayable) and the
agent cannot get a number wrong.
"""

import json
import re
from pathlib import Path
from typing import Any

import anthropic

from agents.loop import AgentRun, run_tool_loop
from k8s.manifests import WORKLOAD_IMAGE
from netco.rules import load_rules

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "documentation.md").read_text(encoding="utf-8")
MARKERS = ("ritmNumber", "changeNumber", "jiraKey", "date")
PLATFORM = "Kubernetes sur kind (cluster local du laboratoire)"
# The lab is neither of these, and nothing runs in production: a document must not suggest it.
FORBIDDEN = ("openshift", "vcenter", "en production")

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"fiche_service": {"type": "string"}, "compte_rendu": {"type": "string"}},
    "required": ["fiche_service", "compte_rendu"],
    "additionalProperties": False,
}

# Concrete values that must come from the facts.
BACKTICKS = re.compile(r"`([^`\n]+)`")
ADDRESS = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b")
PORT = re.compile(r"\b\d+/(?:tcp|udp)\b", re.IGNORECASE)
IDENTIFIER = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b")
NAMESPACE = re.compile(r"\bsvc-[a-z0-9]+(?:-[a-z0-9]+)*")
SIZE = re.compile(r"\b(\d[\d   ]*)\s*(?:Mo|Go|Mio|Gio|MB|GB|vCPU)\b")
# Numbers of ServiceNow records: always markers, never written by the agent.
RECORD_NUMBER = re.compile(r"\b(?:RITM|REQ|CHG|INC|PRB)\d+\b")
MARKER = re.compile(r"\{\{(\w*)\}\}")


def facts(v: dict[str, Any]) -> dict[str, Any]:
    """The facts of an exposure, from the process variables; the agent's only source."""
    zones = load_rules()["zones"]
    if v["changeClass"] == "standard":
        approval = "pré-approuvé (changement standard, CHG-01)"
    else:
        approval = "approuvé dans Camunda Tasklist (CHG-02)"
    verification = v["verification"]
    dossier: dict[str, Any] = {
        "demande": {
            "numero": "{{ritmNumber}}",
            "service": v["serviceName"],
            "environnement": v["environment"],
            "exposition": v["exposure"],
            "port": f"{v['port']}/tcp",
            "port_sensible": bool(v.get("sensitivePort")),
            "reseaux_sources": [n.strip() for n in str(v["sourceNetworks"]).split(",")],
        },
        "changement": {
            "numero": "{{changeNumber}}",
            "classe": v["changeClass"],
            "approbation": approval,
            "commentaire_approbation": v.get("approvalComment") or None,
        },
        "ticket_jira": "{{jiraKey}}",
        "date": "{{date}}",
        "kubernetes": {
            "plateforme": PLATFORM,
            "namespace": v["namespace"],
            "objets": v.get("provisionedResources") or [],
            "image": WORKLOAD_IMAGE,
            "adresse_interne": f"{v['serviceName']}.{v['namespace']}.svc.cluster.local:{v['port']}",
            "zones_autorisees": {zone: zones[zone] for zone in v["zones"]},
        },
        "verification": {
            "resultat": verification["summary"],
            "tentatives": v.get("verificationAttempts") or 1,
            "sondes": [
                {
                    "zone": check["zone"],
                    "attendu": "joignable" if check["expected"] else "bloquée",
                    "constat": "joignable" if check["reachable"] else "bloquée",
                }
                for check in verification.get("checks") or []
            ],
        },
    }
    if v.get("vm"):
        vm = v["vm"]
        dossier["vm"] = {
            "plateforme": vm["platform"],
            "nom": vm["name"],
            "dossier": vm["folder"],
            "taille": str(v.get("vmSize") or "").upper(),
            "vcpu": vm["cpu"],
            "memoire_mo": vm["memoryMb"],
            "reseau": vm["network"],
            "etat": vm["powerState"],
        }
    if v.get("diagnosis"):
        diagnosis = v["diagnosis"]
        manual = v.get("remediationDecision") == "manual"
        dossier["incident"] = {
            "constat": "première vérification réseau en échec",
            "cause_diagnostiquee": diagnosis["cause"],
            "runbook": diagnosis.get("runbook"),
            "explication_agent": diagnosis.get("explanation", ""),
            "action_proposee": diagnosis["action"],
            "validation": (
                "l'opérateur a corrigé lui-même puis relancé la vérification"
                if manual
                else "action validée par un opérateur dans Camunda Tasklist, puis appliquée"
            ),
            "commentaire_validation": v.get("remediationComment") or None,
            "actions_appliquees": v.get("remediationsApplied") or [],
        }
    return dossier


def _leaves(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [s for item in value.items() for v in item for s in _leaves(v)]
    if isinstance(value, list):
        return [s for item in value for s in _leaves(item)]
    return [] if value is None else [str(value)]


def check_values(text: str, dossier: dict[str, Any]) -> list[str]:
    """Problems of a draft, before markers are filled in; an empty list means it can be used."""
    leaves = _leaves(dossier)
    corpus = "\n".join(leaves)
    problems: list[str] = []

    def unknown(value: str) -> None:
        if value not in corpus and f"valeur absente des faits : {value}" not in problems:
            problems.append(f"valeur absente des faits : {value}")

    for value in BACKTICKS.findall(text):
        unknown(value.strip())
    for pattern in (ADDRESS, PORT, IDENTIFIER, NAMESPACE):
        for value in pattern.findall(text):
            unknown(value)
    for number in SIZE.findall(text):
        digits = re.sub(r"\D", "", number)
        if digits not in leaves:
            problems.append(f"taille absente des faits : {number.strip()}")
    for number in RECORD_NUMBER.findall(text):
        problems.append(f"numéro écrit en dur au lieu d'un marqueur : {number}")
    for name in MARKER.findall(text):
        if name not in MARKERS:
            problems.append(f"marqueur inconnu : {{{{{name}}}}}")
    lowered = text.lower()
    problems += [f"terme interdit : {term}" for term in FORBIDDEN if term in lowered]
    return problems


def fill(text: str, values: dict[str, str]) -> str:
    """Replace the markers by the values of this run (ticket numbers, date)."""
    return MARKER.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def draft(
    dossier: dict[str, Any],
    client: anthropic.Anthropic | None = None,
    model: str | None = None,
) -> AgentRun:
    """One request, no tool: the facts go in, the two Markdown documents come out."""
    return run_tool_loop(
        system=SYSTEM_PROMPT,
        tools=[],
        schema=OUTPUT_SCHEMA,
        first_message=(
            "Dossier de faits :\n```json\n"
            + json.dumps(dossier, ensure_ascii=False, indent=2)
            + "\n```\n\nRédige la fiche de service et le compte rendu du changement."
        ),
        execute=lambda name, args: f"Outil inconnu : {name}",
        max_turns=1,
        client=client,
        model=model,
        effort="low",
    )


def _ticks(value: Any) -> str:
    return f"`{value}`"


def template(dossier: dict[str, Any]) -> dict[str, str]:
    """The deterministic documents used when a draft fails the check."""
    d, c, k, ver = (dossier[s] for s in ("demande", "changement", "kubernetes", "verification"))
    zones = ", ".join(f"{_ticks(z)} ({_ticks(cidr)})" for z, cidr in k["zones_autorisees"].items())
    probes = [
        f"- zone {_ticks(p['zone'])} : attendu {p['attendu']}, constaté {p['constat']}"
        for p in ver["sondes"]
    ]
    vm = dossier.get("vm")
    vm_lines = (
        [
            "",
            "## Machine virtuelle",
            f"- VM {_ticks(vm['nom'])} dans le dossier {_ticks(vm['dossier'])} "
            f"({vm['plateforme']})",
            f"- Taille {_ticks(vm['taille'])} : {_ticks(vm['vcpu'])} vCPU, "
            f"{_ticks(vm['memoire_mo'])} Mo, réseau {_ticks(vm['reseau'])}, "
            f"état {_ticks(vm['etat'])}",
        ]
        if vm
        else []
    )
    fiche = "\n".join(
        [
            f"# Fiche de service : {_ticks(d['service'])} ({_ticks(d['environnement'])})",
            "",
            "## Identité",
            f"- Service {_ticks(d['service'])}, environnement {_ticks(d['environnement'])}, "
            f"exposition {_ticks(d['exposition'])}",
            f"- Plateforme : {k['plateforme']}",
            "",
            "## Accès",
            f"- Namespace {_ticks(k['namespace'])}, port {_ticks(d['port'])}",
            f"- Adresse interne : {_ticks(k['adresse_interne'])}",
            f"- Zones autorisées : {zones}",
            "",
            "## Objets Kubernetes",
            *[f"- {_ticks(o)}" for o in k["objets"]],
            *vm_lines,
            "",
            "## Vérification",
            f"- Résultat : {ver['resultat']} ({ver['tentatives']} vérification(s))",
            *probes,
            "",
            "## Références",
            "- Demande {{ritmNumber}}, changement {{changeNumber}}, ticket Jira {{jiraKey}}",
            "- Fiche générée par gabarit le {{date}}",
        ]
    )
    incident = dossier.get("incident")
    incident_lines = (
        [
            "",
            "## Incident et remédiation",
            f"- Constat : {incident['constat']}",
            f"- Cause diagnostiquée par l'agent : {_ticks(incident['cause_diagnostiquee'])} "
            f"(runbook {_ticks(incident['runbook'])})",
            f"- Action proposée : {_ticks(incident['action_proposee'])} ; {incident['validation']}",
        ]
        if incident
        else []
    )
    vm_step = [f"- Création de la VM {_ticks(vm['nom'])} ({vm['plateforme']})"] if vm else []
    compte_rendu = "\n".join(
        [
            "# Compte rendu du changement {{changeNumber}}",
            "",
            "## Contexte",
            f"Demande {{{{ritmNumber}}}} : exposition {_ticks(d['exposition'])} du service "
            f"{_ticks(d['service'])} en {_ticks(d['environnement'])} sur le port "
            f"{_ticks(d['port'])}.",
            "",
            "## Classe et approbation",
            f"Classe {_ticks(c['classe'])}, {c['approbation']}.",
            "",
            "## Opérations",
            f"- Provisionnement du namespace {_ticks(k['namespace'])} ({k['plateforme']})",
            *vm_step,
            f"- Vérification réseau : {ver['resultat']}",
            *incident_lines,
            "",
            "## Conclusion",
            "Changement réalisé et vérifié le {{date}} ; ticket Jira {{jiraKey}}.",
        ]
    )
    return {"fiche_service": fiche, "compte_rendu": compte_rendu}
