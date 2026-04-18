from __future__ import annotations

from . import paths
from .constants import INDEX_MARKER_END, INDEX_MARKER_START, SECTION_TYPES
from .content import default_index_description, load_page_records
from .models import PageRecord


def render_index_section(section: str, records: list[PageRecord]) -> list[str]:
    title = section.capitalize()
    lines = [f"## {title}"]

    sorted_records = sorted(
        (record for record in records if record.section == section),
        key=lambda record: (record.title.casefold(), record.slug.casefold()),
    )

    if section == "sources":
        lines.append(INDEX_MARKER_START)

    if sorted_records:
        for record in sorted_records:
            description = record.description or default_index_description(record)
            lines.append(
                f"- [[{section}/{record.slug}|{record.title}]] - {description}"
            )
    else:
        lines.append("- No pages yet.")

    if section == "sources":
        lines.append(INDEX_MARKER_END)

    return lines


def build_index_text(records: list[PageRecord] | None = None) -> str:
    if records is None:
        records = load_page_records()
    lines = [
        "# Wiki Index",
        "",
        "This file is generated from page frontmatter.",
        "Run `wiki build-index` after structural edits if it falls out of date.",
        "",
    ]

    for index, section in enumerate(SECTION_TYPES):
        if index:
            lines.append("")
        lines.extend(render_index_section(section, records))

    return "\n".join(lines).rstrip() + "\n"


def build_index() -> None:
    paths.ensure_workspace()
    index_path = paths.WIKI_ROOT / "index.md"
    index_path.write_text(build_index_text(), encoding="utf-8")
