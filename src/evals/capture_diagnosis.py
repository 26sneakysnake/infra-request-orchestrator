"""Capture the diagnosis evaluation cases on the kind cluster: python -m evals.capture_diagnosis

For each case: inject the fault into a clean exposure, let the symptom settle, run the same
verification as the process, take the canonical snapshot the agent will see, then delete the
namespace. The expected cause and action come from the injected fault, never from a hand edit.
Run once when the case set is created (needs `make kind-up`); --print shows snapshots only.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from k8s.cluster import Cluster
from k8s.faults import FAULTS, inject
from k8s.manifests import exposure_objects
from k8s.observe import collect
from netco.rules import load_rules

CASES = Path(__file__).resolve().parents[2] / "eval" / "cases" / "diagnosis" / "cases.yaml"
SPECS = [
    ("D01", "network_policy_zone", "inventaire-api", "dev", 8080, ["dev"]),
    ("D02", "network_policy_port", "budget-web", "recette", 443, ["finance"]),
    ("D03", "service_target_port", "stocks-api", "recette", 8443, ["finance"]),
    ("D04", "service_port", "monitoring-ui", "dev", 9090, ["bureautique"]),
    ("D05", "selector_typo", "catalogue-web", "dev", 8080, ["dev"]),
    ("D06", "selector_label", "ventes-db", "dev", 3306, ["data"]),
    ("D07", "image_tag", "reporting-api", "recette", 8443, ["data"]),
    ("D08", "image_registry", "portail-rh", "prod", 443, ["internet"]),
    ("D09", "quota_zero", "cache-sessions", "prod", 6379, ["dev"]),
    ("D10", "quota_full", "annuaire-db", "recette", 5432, ["bureautique"]),
]
READY_TIMEOUT_S = 45.0


def capture(cluster: Cluster, case_id: str, variant: str, service: str, environment: str,
            port: int, zones: list[str]) -> dict[str, Any]:  # fmt: skip
    namespace = load_rules()["naming"]["namespace_template"].format(
        service=service, environment=environment
    )
    request = {"service": service, "namespace": namespace, "port": port, "zones": zones}
    cluster.delete_namespace(namespace)
    objects = inject(
        exposure_objects(namespace, service, environment, port, zones), variant, request
    )
    cluster.apply(objects)
    all_zones = list(load_rules()["zones"])
    verification = cluster.verify(namespace, service, port, zones, all_zones, READY_TIMEOUT_S)
    if verification["ok"]:
        raise RuntimeError(f"{case_id}: fault {variant} did not break the verification")
    snapshot = collect(cluster, namespace, service, request, verification)
    cluster.delete_namespace(namespace)
    fault = FAULTS[variant]
    return {
        "id": case_id,
        "fault": variant,
        "request": {**request, "environment": environment},
        "expected": {"cause": fault.cause, "action": fault.action},
        "snapshot": snapshot,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated case ids, e.g. D01,D07")
    parser.add_argument("--print", action="store_true", help="print snapshots, write nothing")
    args = parser.parse_args(argv)
    wanted = set(args.only.split(",")) if args.only else None
    cluster = Cluster()
    cases = []
    for spec in SPECS:
        if wanted and spec[0] not in wanted:
            continue
        case = capture(cluster, *spec)
        cases.append(case)
        print(
            f"{case['id']} {case['fault']:<20} {case['snapshot']['verification'].splitlines()[1]}"
        )
        if args.print:
            print(yaml.safe_dump(case["snapshot"], allow_unicode=True, sort_keys=False))
    if not args.print:
        CASES.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# Diagnosis agent evaluation: 10 faults captured on the kind cluster by\n"
            "# `python -m evals.capture_diagnosis`. Expected cause and action come from the\n"
            "# injected fault. Frozen by cases.sha256; never edited by hand (CLAUDE.md).\n"
        )
        body = yaml.safe_dump(cases, allow_unicode=True, sort_keys=False, width=100)
        CASES.write_text(header + body, encoding="utf-8", newline="\n")
        print(f"Wrote {len(cases)} cases to {CASES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
