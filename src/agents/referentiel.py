"""Search in the NetCo referentiel (referentiel/*.md): the agent's tool, and citation checks."""

import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

REFERENTIEL_DIR = Path(__file__).resolve().parents[2] / "referentiel"
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "et", "ou", "en", "au", "aux",
    "pour", "par", "sur", "dans", "avec", "est", "sont", "qui", "que", "ce", "cette", "se", "ne",
    "pas", "plus", "on", "il", "elle", "nous", "vous", "son", "sa", "ses", "leur",
}  # fmt: skip


@dataclass(frozen=True)
class Section:
    source: str
    title: str
    text: str


def _fold(text: str) -> str:
    """Lowercase without accents, so that "réseau" matches "reseau"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9./-]*", _fold(text))
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def _normalize(text: str) -> str:
    # Markdown markup and spacing must not decide whether a quoted passage is genuine.
    text = re.sub(r"[`*_>]", "", _fold(text)).replace("|", " ")
    text = re.sub(r"\s+([,.;:!?)])", r"\1", " ".join(text.split()))
    return text.strip(" .;:")


@cache
def sections() -> tuple[Section, ...]:
    found = []
    for path in sorted(REFERENTIEL_DIR.glob("*.md")):
        title, lines = None, []
        for line in [*path.read_text(encoding="utf-8").splitlines(), "## "]:
            if line.startswith("## "):
                if title:
                    found.append(Section(path.name, title, "\n".join(lines).strip()))
                title, lines = line[3:].strip(), []
            elif title is not None:
                lines.append(line)
    return tuple(found)


def search(query: str, k: int = 3) -> list[Section]:
    """The k sections sharing the most words with the query (title words count double)."""
    terms = _terms(query)
    scored = []
    for position, section in enumerate(sections()):
        score = len(terms & _terms(section.text)) + 2 * len(terms & _terms(section.title))
        if score:
            scored.append((-score, position, section))
    return [section for _, _, section in sorted(scored)[:k]]


def format_results(found: list[Section]) -> str:
    if not found:
        return "Aucune section du référentiel ne correspond. Reformulez avec d'autres mots-clés."
    return "\n\n".join(f"[{s.source}] ## {s.title}\n{s.text}" for s in found)


def passage_exists(passage: str) -> bool:
    """True when the quoted passage really appears in the referentiel (ignoring markup)."""
    needle = _normalize(passage)
    return bool(needle) and any(needle in _normalize(f"{s.title} {s.text}") for s in sections())
