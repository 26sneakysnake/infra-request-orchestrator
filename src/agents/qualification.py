"""Qualification agent: turns a free-text request into the structured form, citing the referentiel.

The agent proposes; the process decides. Its fields then go through the deterministic validation
(netco.rules) and the change classification table. It has one read-only tool and no side effect.
"""

import json
from pathlib import Path
from typing import Any

import anthropic

from agents.loop import AgentError, AgentRun, run_tool_loop
from agents.referentiel import format_results, search

MAX_TURNS = 6
REQUIRED = ("service_name", "environment", "exposure", "ports", "source_networks")
# Agent field -> process variable (same names as the ServiceNow form, see workers.poller).
PROCESS_NAMES = {
    "service_name": "serviceName",
    "environment": "environment",
    "exposure": "exposure",
    "ports": "ports",
    "source_networks": "sourceNetworks",
    "vm_required": "vmRequired",
    "vm_size": "vmSize",
    "urgent": "urgent",
}
DEFAULT_QUESTIONS = {
    "service_name": "Quel est le nom du service à exposer ?",
    "environment": "Pour quel environnement : dev, recette ou prod ?",
    "exposure": "L'exposition est-elle interne (réseaux NetCo) ou externe (Internet) ?",
    "ports": "Quel port (et protocole) faut-il ouvrir ?",
    "source_networks": "Depuis quels réseaux ou équipes le service doit-il être joignable ?",
}

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "qualification.md").read_text(encoding="utf-8")

SEARCH_TOOL = {
    "name": "search_referentiel",
    "description": (
        "Cherche dans le référentiel NetCo (nommage, environnements, ports, zones réseau, "
        "classes de changement) et renvoie les sections les plus proches, avec leur identifiant "
        "de règle. Sert à traduire une équipe en CIDR de zone, à vérifier un port ou un "
        "environnement."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Mots-clés, par exemple « zone développeurs » ou « port RDP ».",
            }
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


OUTPUT_PROPERTIES: dict[str, Any] = {
    "out_of_scope": {"type": "boolean"},
    "service_name": _nullable({"type": "string"}),
    "environment": _nullable({"type": "string", "enum": ["dev", "recette", "prod"]}),
    "exposure": _nullable({"type": "string", "enum": ["interne", "externe"]}),
    "ports": {"type": "array", "items": {"type": "string"}},
    "source_networks": {"type": "array", "items": {"type": "string"}},
    "vm_required": {"type": "boolean"},
    "vm_size": _nullable({"type": "string", "enum": ["S", "M", "L"]}),
    "urgent": {"type": "boolean"},
    "missing": {"type": "array", "items": {"type": "string", "enum": list(REQUIRED)}},
    "questions": {"type": "array", "items": {"type": "string"}},
    "citations": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"rule": {"type": "string"}, "passage": {"type": "string"}},
            "required": ["rule", "passage"],
            "additionalProperties": False,
        },
    },
    "summary": {"type": "string"},
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": OUTPUT_PROPERTIES,
    "required": list(OUTPUT_PROPERTIES),
    "additionalProperties": False,
}


# The names other modules use for the shared loop's result and error.
Qualification = AgentRun
QualificationError = AgentError


def _user_message(text: str, form: dict[str, Any] | None) -> str:
    filled = {k: v for k, v in (form or {}).items() if v not in (None, "", False, [])}
    parts = [f"Demande :\n{text.strip()}"]
    if filled:
        parts.append(
            "Formulaire déjà rempli par le demandeur :\n"
            + json.dumps(filled, ensure_ascii=False, sort_keys=True)
        )
    return "\n\n".join(parts)


def qualify(
    text: str,
    form: dict[str, Any] | None = None,
    client: anthropic.Anthropic | None = None,
    model: str | None = None,
    effort: str | None = None,
) -> Qualification:
    """Run the agent loop; form uses the agent field names (service_name, ports...)."""
    return run_tool_loop(
        system=SYSTEM_PROMPT,
        tools=[SEARCH_TOOL],
        schema=OUTPUT_SCHEMA,
        first_message=_user_message(text, form),
        execute=lambda name, args: format_results(search(str(args.get("query", "")))),
        max_turns=MAX_TURNS,
        client=client,
        model=model,
        effort=effort,
    )


def _empty(value: Any) -> bool:
    return value in (None, "", [])


def merge(form: dict[str, Any], qualification: Qualification) -> dict[str, Any]:
    """Process variables from the form (camelCase) and the agent: a filled form field wins.

    Deterministic: the list of missing fields is recomputed after the merge, so the agent cannot
    hide a gap, and a field the requester filled in is never asked again.
    """
    answer = qualification.answer
    variables: dict[str, Any] = {}
    for agent_name, name in PROCESS_NAMES.items():
        proposed = answer.get(agent_name)
        if agent_name in ("ports", "source_networks"):
            proposed = ", ".join(proposed or [])
        if agent_name in ("vm_required", "urgent"):
            variables[name] = bool(form.get(name)) or bool(proposed)
        else:
            variables[name] = form.get(name) if not _empty(form.get(name)) else proposed or ""

    missing = [
        f
        for f in REQUIRED
        if _empty(variables[PROCESS_NAMES[f]])
        or (f in answer.get("missing", []) and _empty(form.get(PROCESS_NAMES[f])))
    ]
    # The agent's questions, plus a default one for each gap it did not flag itself.
    questions = list(dict.fromkeys(answer.get("questions") or [])) if missing else []
    questions += [DEFAULT_QUESTIONS[f] for f in missing if f not in answer.get("missing", [])]

    out_of_scope = bool(answer.get("out_of_scope"))
    variables["qualification"] = {
        "outOfScope": out_of_scope,
        "missing": [] if out_of_scope else missing,
        "questions": [] if out_of_scope else questions,
        "citations": answer.get("citations") or [],
        "summary": answer.get("summary") or "",
        "model": qualification.model,
        "turns": qualification.turns,
        "costUsd": round(qualification.cost_usd, 6),
    }
    if out_of_scope:
        variables["rejectionReasons"] = [
            f"Hors périmètre de l'exposition de service : {answer.get('summary') or 'demande'}"
        ]
    return variables
