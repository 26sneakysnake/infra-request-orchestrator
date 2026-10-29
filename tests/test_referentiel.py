"""netco.yaml is what the code reads; the Markdown is what people (and the P3 agent) read."""

import re
from pathlib import Path

from netco.rules import load_rules

REFERENTIEL = Path(__file__).resolve().parents[1] / "referentiel"
# Sub-folders included: infrastructure/ holds rules the qualification agent does not search.
MARKDOWN = "\n".join(p.read_text(encoding="utf-8") for p in REFERENTIEL.rglob("*.md"))


def test_every_port_and_zone_is_documented() -> None:
    rules = load_rules()
    ports = set(rules["ports"]["forbidden"]) | set(rules["ports"]["sensitive"])
    for allowed in rules["ports"]["allowed"].values():
        ports |= set(allowed)
    for port in ports:
        assert re.search(rf"\b{port}\b", MARKDOWN), f"port {port} missing from referentiel/*.md"
    for zone, cidr in rules["zones"].items():
        assert zone in MARKDOWN and cidr in MARKDOWN, f"zone {zone} missing from referentiel/*.md"


def test_every_rule_identifier_in_the_yaml_is_documented() -> None:
    yaml_text = (REFERENTIEL / "netco.yaml").read_text(encoding="utf-8")
    identifiers = set(re.findall(r"[A-Z]{3,4}-\d{2}", yaml_text))
    assert identifiers, "netco.yaml should reference its rule identifiers"
    for identifier in identifiers:
        assert f"## {identifier}" in MARKDOWN, f"{identifier} has no section in referentiel/*.md"
