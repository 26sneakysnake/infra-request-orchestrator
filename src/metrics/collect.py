"""Measures of the process from the Camunda history: python -m metrics.collect

The sample is the e2e runs made with live LLM calls (out/e2e-runs/*.json, llm_mode "live"): in
replay an agent answers in a tenth of a second, which says nothing of its real latency. Each
instance is read back from the Camunda REST API: element instances with their start and end dates,
and the process variables (LLM cost, documentation check).

Human waits (approval, remediation validation, requester reply) are simulated by the e2e script, so
they are reported apart and subtracted from the processing time, never presented as measures. The
as-is scenario (hypotheses/as-is.yaml) is copied next to the measures and labelled as a hypothesis.
Writes results/metrics.json.
"""

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import camunda_orchestration_sdk as sdk
import yaml

from evals.stats import proportion
from scenario.camunda import camunda_client
from scenario.e2e import find_instance, instance_variables

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "out" / "e2e-runs"
AS_IS = ROOT / "hypotheses" / "as-is.yaml"
RESULT = ROOT / "results" / "metrics.json"

KINDS = ("standard", "normale_vm", "texte_libre", "panne")
AUTOMATED = {"SERVICE_TASK", "BUSINESS_RULE_TASK"}
# A human acts on a user task; the requester's reply ends the wait of the event-based gateway.
HUMAN_TASK, HUMAN_WAIT = "USER_TASK", {"USER_TASK", "EVENT_BASED_GATEWAY"}
REPLY_EVENT = "Event_RequesterReply"
AGENT_STEPS = ("Task_QualifyRequest", "Task_Diagnose", "Task_Document")

History = dict[str, Any]


def _seconds(start: float | None, end: float | None) -> float | None:
    return None if start is None or end is None else end - start


def instance_measures(history: History) -> dict[str, Any]:
    """Measures of one completed instance (dates in epoch seconds)."""
    elements = [e for e in history["elements"] if e["end"] is not None]
    human_wait = sum(e["end"] - e["start"] for e in elements if e["type"] in HUMAN_WAIT)
    total = history["end"] - history["start"]
    interventions = [e["id"] for e in elements if e["type"] == HUMAN_TASK or e["id"] == REPLY_EVENT]
    variables = history["variables"]
    return {
        "total_s": total,
        "human_wait_s": human_wait,
        "processing_s": total - human_wait,
        "automated": sum(e["type"] in AUTOMATED for e in elements),
        "human": len(interventions),
        "interventions": interventions,
        "steps": [
            (e["id"], e["name"], e["end"] - e["start"])
            for e in elements
            if e["type"] in AUTOMATED | {HUMAN_TASK}
        ],
        "llm_cost_usd": float(variables.get("llmCostUsd") or 0),
        "documentation": (variables.get("documentation") or {}).get("source"),
    }


def summary(values: list[float], digits: int = 1) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "median": round(statistics.median(values), digits),
        "min": round(min(values), digits),
        "max": round(max(values), digits),
    }


def _by_kind(rows: list[dict[str, Any]], field: str, digits: int = 1) -> dict[str, Any]:
    return {
        "all": summary([r[field] for r in rows], digits),
        **{k: summary([r[field] for r in rows if r["kind"] == k], digits) for k in KINDS},
    }


def aggregate(rows: list[dict[str, Any]], total_requests: int) -> dict[str, Any]:
    """rows: instance_measures() of the completed instances, each with its "kind"."""
    steps: dict[str, list[float]] = defaultdict(list)
    names: dict[str, str] = {}
    for row in rows:
        for element_id, name, seconds in row["steps"]:
            steps[element_id].append(seconds)
            names[element_id] = name
    interventions = {
        k: dict(
            sorted(Counter(i for r in rows if r["kind"] == k for i in r["interventions"]).items())
        )
        for k in KINDS
    }
    automated = sum(r["automated"] for r in rows)
    activities = automated + sum(r["human"] for r in rows)
    documented = [r for r in rows if r["documentation"]]
    return {
        "completed": proportion(len(rows), total_requests),
        "end_to_end_s": _by_kind(rows, "total_s"),
        "processing_s": _by_kind(rows, "processing_s"),
        "human_wait_s_simulated": _by_kind(rows, "human_wait_s"),
        "agent_steps_s": {
            s: {"name": names[s], **summary(steps[s])} for s in AGENT_STEPS if s in steps
        },
        "steps_s": {s: {"name": names[s], **summary(v)} for s, v in sorted(steps.items())},
        "automated_activities": {
            "k": automated,
            "n": activities,
            "rate": round(automated / activities, 4) if activities else None,
        },
        "requests_without_human": proportion(sum(r["human"] == 0 for r in rows), len(rows)),
        "human_interventions_by_kind": interventions,
        "llm_cost_usd": {
            **_by_kind(rows, "llm_cost_usd", digits=4),
            "total": round(sum(r["llm_cost_usd"] for r in rows), 4),
        },
        "documentation_by_agent": proportion(
            sum(r["documentation"] == "agent" for r in documented), len(documented)
        ),
    }


def as_is(path: Path = AS_IS) -> dict[str, Any]:
    """The declared hypotheses, with their totals for the request types of the scenario."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    variants = {"standard": {"all"}, "normale_vm": {"all", "normal", "vm"}}
    totals = {}
    for variant, applies in variants.items():
        steps = [s for s in data["steps"] if s["applies"] in applies]
        totals[variant] = {
            "steps": len(steps),
            "effort_min": sum(s["effort_min"] for s in steps),
            "delay_days": [
                sum(s["delay_days"][0] for s in steps),
                sum(s["delay_days"][1] for s in steps),
            ],
            "human_steps": len(steps),
        }
    return {"nature": data["nature"], "source": "hypotheses/as-is.yaml", "steps": data["steps"],
            "totals": totals}  # fmt: skip


# --- Camunda history -------------------------------------------------------------------------


def _epoch(value: Any) -> float | None:
    return value.timestamp() if value is not None and hasattr(value, "timestamp") else None


def fetch_history(client: sdk.CamundaClient, business_id: str) -> History | None:
    instance = find_instance(client, business_id)
    if instance is None or not str(instance.state).endswith("COMPLETED"):
        return None
    key = instance.process_instance_key
    query = sdk.ElementInstanceSearchQuery(
        filter_=sdk.ElementInstanceFilter(process_instance_key=key)
    )
    result = client.search_element_instances(data=query)
    if result.page.has_more_total_items or result.page.total_items > len(result.items or []):
        raise RuntimeError(f"{business_id}: element instances span several pages")
    elements = [
        {
            "id": e.element_id,
            "name": e.element_name,
            "type": str(e.type_.value if hasattr(e.type_, "value") else e.type_),
            "start": _epoch(e.start_date),
            "end": _epoch(e.end_date),
        }
        for e in result.items or []
    ]
    return {
        "start": _epoch(instance.start_date),
        "end": _epoch(instance.end_date),
        "elements": elements,
        "variables": instance_variables(client, str(key)),
    }


def load_runs(directory: Path = RUNS, mode: str = "live") -> list[dict[str, Any]]:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]
    return [r for r in runs if r.get("llm_mode") == mode]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", default="live", help="LLM mode of the e2e runs to measure")
    args = parser.parse_args(argv)
    runs = load_runs(mode=args.mode)
    if not runs:
        print(f"No e2e run in {args.mode} mode in {RUNS}: run NETCO_LLM_MODE=live make e2e first.")
        return 1
    client = camunda_client()
    requests = [(run["run"], r) for run in runs for r in run["requests"]]
    rows = []
    for _, request in requests:
        history = fetch_history(client, request["ritm"])
        if history is not None:
            rows.append({**instance_measures(history), "kind": request["kind"]})
    result = {
        "sample": {
            "description": f"{len(runs)} exécutions de l'e2e, appels LLM en mode {args.mode}",
            "llm_mode": args.mode,
            "runs": [run["run"] for run in runs],
            "requests": [
                {"run": run_id, "ritm": r["ritm"], "kind": r["kind"]} for run_id, r in requests
            ],
            "by_kind": dict(Counter(r["kind"] for _, r in requests)),
            "human_steps": "simulées par le script e2e : leurs durées ne sont pas des mesures",
        },
        "measured": aggregate(rows, len(requests)),
        "as_is_hypotheses": as_is(),
    }
    RESULT.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    m = result["measured"]
    print(
        f"{len(rows)}/{len(requests)} completed; end to end median "
        f"{m['end_to_end_s']['all'].get('median')} s; automated "
        f"{m['automated_activities']['k']}/{m['automated_activities']['n']}; LLM cost median "
        f"{m['llm_cost_usd']['all'].get('median')} $ -> {RESULT.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
