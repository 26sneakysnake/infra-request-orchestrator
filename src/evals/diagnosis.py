"""Evaluate the diagnosis agent on the frozen fault cases: python -m evals.diagnosis [--live]

The cases (eval/cases/diagnosis/cases.yaml) are canonical snapshots of injected faults, captured
once on kind by evals.capture_diagnosis. By default the agent's answers are replayed from
cassettes/llm/ (no key, no cost); --live records the missing ones. --freeze writes the fingerprint.
Writes results/diagnosis.json, deterministic for given cassettes.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from agents.diagnosis import diagnose, grounded
from agents.llm import anthropic_client, cost_usd
from evals.stats import proportion

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "eval" / "cases" / "diagnosis" / "cases.yaml"
FINGERPRINT = CASES.with_name("cases.sha256")
RESULTS = ROOT / "results" / "diagnosis.json"


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


def score_case(case: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    evidence = answer.get("evidence") or []
    return {
        "id": case["id"],
        "fault": case["fault"],
        "cause_expected": expected["cause"],
        "cause_got": answer["cause"],
        "action_expected": expected["action"],
        "action_got": answer["action"],
        "cause_ok": answer["cause"] == expected["cause"],
        "action_ok": answer["action"] == expected["action"],
        "runbook": answer.get("runbook"),
        "confidence": answer.get("confidence"),
        "evidence": len(evidence),
        "evidence_grounded": sum(grounded(e, case["snapshot"]) for e in evidence),
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
        run = diagnose(case["snapshot"], case["request"]["service"], client=client)
        model = run.model
        usage.update(run.usage)
        scored.append(score_case(case, run.answer))
        s = scored[-1]
        print(
            f"{case['id']} {case['fault']:<20} cause {s['cause_got']:<16} action {s['action_got']}"
        )

    n = len(scored)
    report = {
        "cases": n,
        "cases_sha256": cases_hash,
        "metrics": {
            "cause": proportion(sum(s["cause_ok"] for s in scored), n),
            "action": proportion(sum(s["action_ok"] for s in scored), n),
            "cause_and_action": proportion(
                sum(s["cause_ok"] and s["action_ok"] for s in scored), n
            ),
            "evidence_grounded": proportion(
                sum(s["evidence_grounded"] for s in scored), sum(s["evidence"] for s in scored)
            ),
            "cost": {
                "model": model,
                "total_usd": round(cost_usd(model, usage), 4),
                "per_case_usd": round(cost_usd(model, usage) / n, 5),
                **{k: usage[k] for k in sorted(usage)},
            },
        },
        "per_case": scored,
    }
    RESULTS.parent.mkdir(exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    RESULTS.write_text(text, encoding="utf-8", newline="\n")  # same bytes on Windows and Linux
    m = report["metrics"]
    print(
        f"cause {m['cause']['k']}/{n}, action {m['action']['k']}/{n}, evidence grounded "
        f"{m['evidence_grounded']['k']}/{m['evidence_grounded']['n']}, cost "
        f"{m['cost']['total_usd']} $ -> {RESULTS.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
