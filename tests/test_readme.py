import json

import pytest

from report.readme import README, SOURCES, TEMPLATE, captures, fmt, render

PROPORTION = {"k": 5, "n": 20, "rate": 0.25, "wilson95": [0.1119, 0.4687]}


@pytest.mark.parametrize(
    ("value", "kind", "text"),
    [
        (PROPORTION, "kn", "5/20 (Wilson 95 % : 0,112 à 0,469)"),
        ({"k": 20, "n": 20, "wilson95": [0.8389, 1.0]}, "kn", "20/20 (Wilson 95 % : 0,839 à 1)"),
        (PROPORTION, "frac", "5/20"),
        (26.0, "s", "26,0 s"),
        (0.0255, "usd", "0,0255 $"),
        ([3, 12], "range", "3 à 12"),
        (185, None, "185"),
        ("5 exécutions", None, "5 exécutions"),
    ],
)
def test_values_are_written_in_french_notation(value, kind, text) -> None:
    assert fmt(value, kind) == text


def test_placeholders_are_replaced_and_unknown_formats_fail() -> None:
    results = {"m": {"a": {"b": 33.7}, "p": PROPORTION}}
    text = render("{{ m.a.b | s }} ; {{ m.p | kn }}", results, "")
    assert text.endswith("33,7 s ; 5/20 (Wilson 95 % : 0,112 à 0,469)")
    with pytest.raises(ValueError, match="unknown format"):
        render("{{ m.a.b | percent }}", results, "")
    with pytest.raises(KeyError):
        render("{{ m.a.missing }}", results, "")


def test_missing_captures_point_to_the_demo_script(tmp_path) -> None:
    assert "docs/DEMO.md" in captures(tmp_path)
    (tmp_path / "jira-issue.png").write_bytes(b"png")
    assert captures(tmp_path).startswith("![Jira")


def test_readme_is_generated_from_the_results() -> None:
    results = {k: json.loads(p.read_text(encoding="utf-8")) for k, p in SOURCES.items()}
    expected = render(TEMPLATE.read_text(encoding="utf-8"), results, captures())
    assert README.read_text(encoding="utf-8") == expected, "run `make readme`"
    # The fictional-company notice stays the first section.
    assert expected.splitlines()[3].startswith("> **Entreprise et données fictives.**")
