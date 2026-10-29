"""Generate README.md from docs/README.template.md and results/*.json: python -m report.readme

Every figure of the README comes from a results file produced by a script. The template names the
value, for instance {{ m.measured.end_to_end_s.all.median | s }}, and this script writes it in
French notation; a proportion is written k/n with its 95 % Wilson interval. CI regenerates the
README and fails on any difference, so a figure cannot drift away from its source.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "docs" / "README.template.md"
README = ROOT / "README.md"
SOURCES = {
    "q": ROOT / "results" / "qualification.json",
    "d": ROOT / "results" / "diagnosis.json",
    "m": ROOT / "results" / "metrics.json",
}
PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\.([\w.]+)\s*(?:\|\s*(\w+)\s*)?\}\}")
CAPTURES_DIR = ROOT / "docs" / "img" / "captures"
# Screenshots taken during the demo (docs/DEMO.md); a missing one is simply left out.
CAPTURES = [
    ("operate-instance.png", "Operate : une instance terminée, avec le chemin suivi"),
    ("tasklist-remediation.png", "Tasklist : la remédiation proposée par l'agent, à valider"),
    (
        "servicenow-change.png",
        "ServiceNow : le changement clos, avec la fiche et le compte rendu joints",
    ),
    ("jira-issue.png", "Jira : le ticket de travaux terminé, relié au changement"),
]
HEADER = (
    "<!-- Généré par `make readme` depuis docs/README.template.md et results/*.json. "
    "Ne pas modifier à la main. -->\n"
)


def number(value: float | int, digits: int | None = None) -> str:
    """French notation: decimal comma, no trailing zeros unless digits is given."""
    if digits is not None:
        text = f"{value:.{digits}f}"
    elif isinstance(value, float) and value.is_integer():
        text = str(int(value))
    else:
        text = str(value)
    return text.replace(".", ",")


def _bound(value: float) -> str:
    return number(round(value, 3)) if value not in (0, 1) else number(int(value))


def fmt(value: Any, kind: str | None) -> str:
    if kind == "kn":
        low, high = value["wilson95"]
        return f"{value['k']}/{value['n']} (Wilson 95 % : {_bound(low)} à {_bound(high)})"
    if kind == "frac":
        return f"{value['k']}/{value['n']}"
    if kind == "s":
        return f"{number(value, 1)} s"
    if kind == "usd":
        return f"{number(value)} $"
    if kind == "range":
        return f"{number(value[0])} à {number(value[1])}"
    if kind in (None, "num"):
        return number(value) if isinstance(value, int | float) else str(value)
    raise ValueError(f"unknown format {kind!r}")


def lookup(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split("."):
        value = value[key]
    return value


def captures(directory: Path = CAPTURES_DIR) -> str:
    shown = [(f, c) for f, c in CAPTURES if (directory / f).exists()]
    if not shown:
        return "Captures d'écran à prendre pendant la démo : voir [docs/DEMO.md](docs/DEMO.md)."
    return "\n\n".join(f"![{c}](docs/img/captures/{f})\n*{c}*" for f, c in shown)


def render(template: str, results: dict[str, dict[str, Any]], captures_block: str) -> str:
    def replace(match: re.Match) -> str:
        source, path, kind = match.groups()
        return fmt(lookup(results[source], path), kind)

    body = template.replace("{{ captures }}", captures_block)
    return HEADER + PLACEHOLDER.sub(replace, body)


def main() -> int:
    results = {k: json.loads(p.read_text(encoding="utf-8")) for k, p in SOURCES.items()}
    text = render(TEMPLATE.read_text(encoding="utf-8"), results, captures())
    leftover = re.findall(r"\{\{[^}]*\}\}", text)
    if leftover:
        print(f"Unresolved placeholders: {leftover}")
        return 1
    README.write_text(text, encoding="utf-8", newline="\n")
    print(f"{README.relative_to(ROOT)} written from {TEMPLATE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
