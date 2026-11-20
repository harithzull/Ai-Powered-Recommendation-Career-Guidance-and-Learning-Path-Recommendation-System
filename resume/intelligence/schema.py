"""Contracts for an extractor that operates on private, local text."""
from dataclasses import dataclass, field
from typing import Protocol


EXTRACTOR_VERSION = 'deterministic-1'
MAX_CATALOG_ROWS = 30_000
MAX_SUGGESTIONS = 100
MAX_SKILLS = 60
MAX_OCCURRENCES = 6
MAX_STRUCTURED_PER_SECTION = 12
MAX_REVISIONS = 20
MAX_LINE_CHARS = 2_000
MAX_SECTIONS = 120
MAX_VALUE_CHARS = 240


@dataclass(frozen=True)
class Evidence:
    start: int
    end: int
    excerpt: str
    section: str
    context: str = ''
    match_method: str = ''
    alias_id: int | None = None


@dataclass(frozen=True)
class Section:
    kind: str
    label: str
    start: int
    end: int


@dataclass
class Suggestion:
    category: str
    value: str
    normalized: str
    evidence: list[Evidence]
    method: str
    support: str = 'explicit'
    fields: dict = field(default_factory=dict)
    canonical: dict = field(default_factory=dict)
    alternatives: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Extraction:
    sections: list[Section]
    suggestions: list[Suggestion]
    notices: tuple[str, ...]


class Extractor(Protocol):
    """Return local suggestions whose evidence offsets index the exact input text."""

    def extract(self, text: str) -> Extraction: ...
