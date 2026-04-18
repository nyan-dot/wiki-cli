from __future__ import annotations

from pathlib import Path

from . import paths
from .constants import SECTION_TYPES
from .models import PageRecord
from .utils import frontmatter_list, normalize_tag, parse_frontmatter, title_from_slug


def iter_content_pages() -> list[Path]:
    pages: list[Path] = []
    for section in SECTION_TYPES:
        section_root = paths.WIKI_ROOT / section
        if not section_root.exists():
            continue
        for path in sorted(section_root.glob("*.md")):
            if path.name == "README.md":
                continue
            pages.append(path)
    return pages


def read_page_record(path: Path) -> PageRecord:
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
    section = path.parent.name

    title = str(frontmatter.get("title") or title_from_slug(path.stem)).strip()
    page_type = str(frontmatter.get("type") or "").strip()
    status = str(frontmatter.get("status") or "").strip()
    description = str(frontmatter.get("description") or "").strip()
    tags = frontmatter_list(frontmatter, "tags")

    return PageRecord(
        section=section,
        slug=path.stem,
        title=title,
        page_type=page_type,
        status=status,
        description=description,
        tags=tags,
        path=path.relative_to(paths.ROOT).as_posix(),
    )


def load_page_records() -> list[PageRecord]:
    return [read_page_record(path) for path in iter_content_pages()]


def default_index_description(record: PageRecord) -> str:
    if record.section == "sources":
        return f"Source note for {record.title}."
    if record.section == "concepts":
        return f"Concept page for {record.title}."
    if record.section == "people":
        return f"Person page for {record.title}."
    return f"Question page for {record.title}."


def extract_wiki_links(text: str) -> list[str]:
    import re

    return re.findall(r"\[\[([^\]]+)\]\]", text)


def resolve_wiki_link(link: str) -> Path | None:
    cleaned = link.split("|", 1)[0].strip().strip("/")
    if not cleaned:
        return None

    candidate = paths.WIKI_ROOT / f"{cleaned}.md"
    return candidate


def filter_page_records(
    records: list[PageRecord],
    *,
    page_type: str | None,
    status: str | None,
    tags: list[str],
    contains: str | None,
) -> list[PageRecord]:
    filtered = records

    if page_type:
        filtered = [record for record in filtered if record.page_type == page_type]
    if status:
        filtered = [record for record in filtered if record.status == status]
    if tags:
        normalized_tags = [normalize_tag(tag) for tag in tags if normalize_tag(tag)]
        filtered = [
            record
            for record in filtered
            if all(
                normalized_tag in {normalize_tag(tag) for tag in record.tags}
                for normalized_tag in normalized_tags
            )
        ]
    if contains:
        needle = contains.casefold()
        filtered = [
            record
            for record in filtered
            if needle in record.title.casefold()
            or needle in record.description.casefold()
            or needle in record.slug.casefold()
            or any(needle in tag.casefold() for tag in record.tags)
        ]

    return sorted(
        filtered,
        key=lambda record: (
            record.section.casefold(),
            record.title.casefold(),
            record.slug.casefold(),
        ),
    )
