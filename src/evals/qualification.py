"""Evaluate the qualification agent on the frozen cases: python -m evals.qualification [--live]

By default the agent's answers are replayed from cassettes/llm/ (no key, no cost), so the published
figures can be reproduced exactly. --live calls the API for the answers not recorded yet (costs
money, bounded by the spend guard). --freeze writes the cases fingerprint (once, at creation).
Writes results/qualification.json; the file has no timestamp, so the same cassettes give the same
bytes.
"""

import argparse
import hashlib
import ipaddress
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from agents.llm import anthropic_client, cost_usd
from agents.qualification import PROCESS_NAMES, merge, qualify
from agents.referentiel import passage_exists
from evals.stats import proportion
from netco.rules import validate

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "eval" / "cases" / "qualification" / "cases.yaml"
FINGERPRINT = CASES.with_name("cases.sha256")
RESULTS = ROOT / "results" / "qualification.json"
SCORED_FIELDS = tuple(PROCESS_NAMES)  # service_name ... urgent


def fingerprint() -> str:
    return hashlib.sha256(CASES.read_bytes()).hexdigest()


def check_frozen() -> str:
    actual = fingerprint()
    expected = FINGERPRINT.read_text(encoding="utf-8").split()[0]
    if actual != expected:
        raise SystemExit(
            f"{CASES.name} changed since it was frozen ({expected[:12]} != {actual[:12]})"
        )
    return actual


def _normalize_item(field: str, value: str) -> str:
    value = str(value).strip().lower()
    if field == "ports" and value and "/" not in value:
        return f"{value}/tcp"
    if field == "source_networks":
        try:
            return str(ipaddress.ip_network(value, strict=False))
        except ValueError:
            return value
    return value


def field_ok(field: str, expected: Any, got: Any) -> bool:
    if field in ("ports", "source_networks"):
        return {_normalize_item(field, v) for v in expected or []} == {
            _normalize_item(field, v) for v in got or []
        }
    if expected is None:
        return got in (None, "")
    if isinstance(expected, str):
        return isinstance(got, str) and got.strip().lower() == expected.lower()
    return got == expected


def decision(variables: dict[str, Any]) -> tuple[str, list[str]]:
    """What the process does with the merged form: out_of_scope, missing, valid or rejected."""
    qualification = variables["qualification"]
    if qualification["outOfScope"]:
        return "out_of_scope", []
    if qualification["missing"]:
        return "missing", []
    result = validate(variables)
    return (
        ("valid", []) if result.valid else ("rejected", [r.split(" ")[0] for r in result.reasons])
    )


def score_case(case: dict[str, Any], answer: dict[str, Any], variables: dict[str, Any]) -> dict:
    expected = case["expected"]
    out_of_scope = bool(expected.get("out_of_scope"))
    fields = (
        {}
        if out_of_scope
        else {f: field_ok(f, expected.get(f), answer.get(f)) for f in SCORED_FIELDS}
    )
    got_decision, rules = decision(variables)
    wanted = expected["verdict"]
    decision_ok = got_decision == wanted or (got_decision == "rejected" and wanted in rules)
    citations = answer.get("citations") or []
    return {
        "id": case["id"],
        "category": case["category"],
        "fields": fields,
        "missing_expected": expected.get("missing", []),
        "missing_got": variables["qualification"]["missing"],
        "out_of_scope_expected": out_of_scope,
        "out_of_scope_got": variables["qualification"]["outOfScope"],
        "decision_expected": wanted,
        "decision_got": got_decision if got_decision != "rejected" else ",".join(rules),
        "decision_ok": decision_ok,
        "citations": len(citations),
        "citations_valid": sum(passage_exists(c["passage"]) for c in citations),
    }


def aggregate(scored: list[dict[str, Any]], usage: Counter, model: str) -> dict[str, Any]:
    in_scope = [s for s in scored if not s["out_of_scope_expected"]]
    with_gaps = [s for s in in_scope if s["missing_expected"]]
    complete = [s for s in in_scope if not s["missing_expected"]]
    out_scope = [s for s in scored if s["out_of_scope_expected"]]
    return {
        "fields": {
            f: proportion(sum(s["fields"][f] for s in in_scope), len(in_scope))
            for f in SCORED_FIELDS
        },
        "exact_requests": proportion(
            sum(all(s["fields"].values()) for s in in_scope), len(in_scope)
        ),
        "missing_detected": proportion(
            sum(set(s["missing_expected"]) <= set(s["missing_got"]) for s in with_gaps),
            len(with_gaps),
        ),
        "missing_false_alarms": proportion(
            sum(bool(s["missing_got"]) for s in complete), len(complete)
        ),
        "out_of_scope_detected": proportion(
            sum(s["out_of_scope_got"] for s in out_scope), len(out_scope)
        ),
        "out_of_scope_false_alarms": proportion(
            sum(s["out_of_scope_got"] for s in in_scope), len(in_scope)
        ),
        "citations_found_in_referentiel": proportion(
            sum(s["citations_valid"] for s in scored), sum(s["citations"] for s in scored)
        ),
        "final_decision": proportion(sum(s["decision_ok"] for s in scored), len(scored)),
        "cost": {
            "model": model,
            "total_usd": round(cost_usd(model, usage), 4),
            "per_request_usd": round(cost_usd(model, usage) / len(scored), 5),
            **{k: usage[k] for k in sorted(usage)},
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="record missing answers (costs money)")
    parser.add_argument("--freeze", action="store_true", help="write the cases fingerprint")
    args = parser.parse_args(argv)
    if args.freeze:
        FINGERPRINT.write_text(f"{fingerprint()}  {CASES.name}\n", encoding="utf-8", newline="\n")
        print(f"Frozen {CASES.name}: {fingerprint()}")
        return 0

    cases_hash = check_frozen()
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    client = anthropic_client("record" if args.live else "replay")
    usage: Counter[str] = Counter()
    scored, model = [], ""
    for case in cases:
        qualification = qualify(case["text"], case.get("form"), client=client)
        model = qualification.model
        usage.update(qualification.usage)
        form = {PROCESS_NAMES[k]: v for k, v in (case.get("form") or {}).items()}
        scored.append(score_case(case, qualification.answer, merge(form, qualification)))
        print(f"{case['id']} {case['category']:<22} decision {scored[-1]['decision_got']}")

    report = {
        "cases": len(cases),
        "cases_sha256": cases_hash,
        "metrics": aggregate(scored, usage, model),
        "per_case": scored,
    }
    RESULTS.parent.mkdir(exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    RESULTS.write_text(text, encoding="utf-8", newline="\n")  # same bytes on Windows and Linux
    m = report["metrics"]
    print(
        f"exact requests {m['exact_requests']['k']}/{m['exact_requests']['n']}, "
        f"missing detected {m['missing_detected']['k']}/{m['missing_detected']['n']}, "
        f"final decision {m['final_decision']['k']}/{m['final_decision']['n']}, "
        f"cost {m['cost']['total_usd']} $ -> {RESULTS.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
