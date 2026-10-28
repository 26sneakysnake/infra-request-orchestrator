"""Qualification agent: turns a free-text request into the structured form, citing the referentiel.

The agent proposes; the process decides. Its fields then go through the deterministic validation
(netco.rules) and the change classification table. It has one read-only tool and no side effect.
"""

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from agents.llm import anthropic_client, cost_usd, llm_model
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
# Server-side fallback on refusal exists for these models (not for Haiku 5.5).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}

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


class QualificationError(RuntimeError):
    """The agent could not produce a qualification (refusal, truncated or endless loop)."""


@dataclass
class Qualification:
    answer: dict[str, Any]
    model: str
    turns: int
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def cost_usd(self) -> float:
        return cost_usd(self.model, self.usage)


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
    client = client or anthropic_client()
    model = model or llm_model()
    effort = effort or os.environ.get("NETCO_LLM_EFFORT", "medium")
    extra: dict[str, Any] = {}
    if model in FALLBACK_MODELS:
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    messages: list[dict[str, Any]] = [{"role": "user", "content": _user_message(text, form)}]
    usage: Counter[str] = Counter()
    for turn in range(1, MAX_TURNS + 1):
        response = client.beta.messages.create(
            model=model,
            max_tokens=8000,
            # Explicit breakpoint: tools + system prompt are cached once and shared by all requests;
            # the automatic one below caches the growing conversation within a request.
            system=[
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
            ],
            tools=[SEARCH_TOOL],
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            cache_control={"type": "ephemeral"},
            messages=messages,
            **extra,
        )
        for name in ("input_tokens", "output_tokens"):
            usage[name] += getattr(response.usage, name) or 0
        for name in ("cache_creation_input_tokens", "cache_read_input_tokens"):
            usage[name] += getattr(response.usage, name, None) or 0

        if response.stop_reason == "refusal":
            raise QualificationError(f"the model declined the request: {response.stop_details}")
        if response.stop_reason == "max_tokens":
            raise QualificationError("answer truncated (max_tokens)")
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": format_results(search(str(block.input.get("query", "")))),
                }
                for block in response.content
                if block.type == "tool_use"
            ]
            messages.append({"role": "user", "content": results})
            continue
        answer_text = next(b.text for b in response.content if b.type == "text")
        return Qualification(json.loads(answer_text), model, turn, dict(usage))
    raise QualificationError(f"no answer after {MAX_TURNS} turns")


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
