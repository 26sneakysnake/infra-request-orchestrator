"""The consulting deliverables (docs/0*.md): short enough to read, and never claim what is not."""

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
DELIVERABLES = sorted(DOCS.glob("0*.md"))
# About two printed pages, tables included.
MAX_WORDS = 1100
# The lab is neither of these, nothing runs in production, and no real client is named.
FORBIDDEN = re.compile(r"openshift|vcenter|en production", re.IGNORECASE)


def test_the_six_deliverables_exist() -> None:
    assert [p.name[:2] for p in DELIVERABLES] == ["01", "02", "03", "04", "05", "06"]


@pytest.mark.parametrize("path", DELIVERABLES, ids=lambda p: p.name)
def test_deliverable_is_short_and_claims_nothing_forbidden(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert len(text.split()) <= MAX_WORDS, f"{path.name}: {len(text.split())} words"
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text)
    # Every relative link points to a file of the repository.
    for target in re.findall(r"\]\((?!https?://)([^)#]+)", text):
        assert (path.parent / target).exists(), f"{path.name}: broken link {target}"
