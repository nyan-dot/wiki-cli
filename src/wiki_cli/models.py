from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class LintFinding:
    level: str
    path: Path
    message: str


@dataclass
class SourceEntry:
    source_type: str
    slug: str
    title: str
    url: str
    authors: list[str]
    first_published: str | None
    pubinfo: str | None
    fetched_at: str
    abstract: str | None = None
    canonical_id: str | None = None
    source_archive_name: str | None = None
    primary_source_path: str | None = None


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
