"""Diagnosis agent: explains why the network verification failed and proposes one allowed action.

It reads the canonical snapshot of the namespace (k8s.observe) through read-only tools, and the
runbooks. It cannot change anything: an operator validates the proposed action in Tasklist, then
the process applies it from a closed list (workers.remediation).
"""

import re
from pathlib import Path
from typing import Any

import anthropic

from agents.loop import AgentRun, run_tool_loop
from agents.referentiel import RUNBOOKS_DIR, format_results, search

MAX_TURNS = 8
CAUSES = ("network_policy", "service_port", "service_selector", "image", "quota", "other")
ACTIONS = (
    "reapply_network_policy",
    "reapply_service",
    "reapply_deployment",
    "raise_pod_quota",
    "escalate",
)
RUNBOOKS = tuple(f"RB-0{i}" for i in range(1, 7))
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "diagnosis.md").read_text(encoding="utf-8")

NO_INPUT = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
KINDS = ["Deployment", "Pod", "Service", "NetworkPolicy", "ResourceQuota"]
TOOLS = [
    {
        "name": "get_verification",
        "description": "Ce que la demande validée attendait, et le résultat de chaque sonde.",
        "strict": True,
        "input_schema": NO_INPUT,
    },
    {
        "name": "list_resources",
        "description": (
            "Résumé des objets du namespace : déploiement et image, pods et leur état, Service "
            "(ports, selector, endpoints prêts), NetworkPolicy (zones, ports), quotas."
        ),
        "strict": True,
        "input_schema": NO_INPUT,
    },
    {
        "name": "describe",
        "description": "Spécification d'un objet du namespace (nom donné par list_resources).",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": KINDS}, "name": {"type": "string"}},
            "required": ["kind", "name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_events",
        "description": "Événements Warning du namespace (tirage d'image, création refusée…).",
        "strict": True,
        "input_schema": NO_INPUT,
    },
    {
        "name": "get_logs",
        "description": "Dernières lignes du journal d'un pod (nom donné par list_resources).",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"pod": {"type": "string"}},
            "required": ["pod"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_runbooks",
        "description": "Cherche dans les runbooks NetCo (symptôme, cause, action autorisée).",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "cause": {"type": "string", "enum": list(CAUSES)},
        "action": {"type": "string", "enum": list(ACTIONS)},
        "runbook": {"type": "string", "enum": list(RUNBOOKS)},
        "explanation": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["cause", "action", "runbook", "explanation", "evidence", "confidence"],
    "additionalProperties": False,
}


def run_tool(snapshot: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    """Answer a tool call from the snapshot: the agent never reaches the cluster itself."""
    if name == "get_verification":
        return snapshot["verification"]
    if name == "list_resources":
        return snapshot["resources"]
    if name == "get_events":
        return snapshot["events"]
    if name == "describe":
        key = f"{args.get('kind')}/{args.get('name')}"
        return snapshot["objects"].get(
            key, f"Objet inconnu : {key}. Objets : {', '.join(sorted(snapshot['objects']))}"
        )
    if name == "get_logs":
        pod = str(args.get("pod"))
        return snapshot["logs"].get(
            pod, f"Pod inconnu : {pod}. Pods : {', '.join(sorted(snapshot['logs'])) or 'aucun'}"
        )
    if name == "search_runbooks":
        return format_results(search(str(args.get("query", "")), directory=RUNBOOKS_DIR))
    return f"Outil inconnu : {name}"


def diagnose(
    snapshot: dict[str, Any],
    service: str,
    client: anthropic.Anthropic | None = None,
    model: str | None = None,
) -> AgentRun:
    return run_tool_loop(
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        schema=OUTPUT_SCHEMA,
        first_message=(
            f"La vérification de l'exposition du service {service} (namespace "
            f"{snapshot['namespace']}) a échoué. Diagnostique la cause avec les outils, puis "
            "propose une seule action autorisée."
        ),
        execute=lambda name, args: run_tool(snapshot, name, args),
        max_turns=MAX_TURNS,
        client=client,
        model=model,
    )


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[`'\"*]", "", text.lower()).split()).strip(" .;:")


def grounded(evidence: str, snapshot: dict[str, Any]) -> bool:
    """True when a quoted piece of evidence really appears in what the tools returned."""
    corpus = [
        snapshot["verification"],
        snapshot["resources"],
        snapshot["events"],
        *snapshot["objects"].values(),
        *snapshot["logs"].values(),
    ]
    needle = _normalize(evidence)
    return bool(needle) and any(needle in _normalize(text) for text in corpus)
