from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class LintFinding:
    level: str
    path: Path
    message: str


@dataclass
class SepEntry:
    slug: str
    title: str
    url: str
    authors: list[str]
    first_published: str | None
    pubinfo: str | None
    fetched_at: str


@dataclass
class PageRecord:
    section: str
    slug: str
    title: str
    page_type: str
    status: str
    description: str
    tags: list[str]
    path: str
