from __future__ import annotations

from pathlib import Path

from .models import SourceEntry
from .utils import escape_quotes


SOURCE_TYPE_LABELS = {
    "sep": "SEP",
    "arxiv": "arXiv",
    "lesswrong": "LessWrong",
}


def render_source_note(
    entry: SourceEntry,
    *,
    authors_line: str,
    published_line: str,
    pubinfo_line: str,
    concept_slug: str,
    source_md_path: str,
    source_html_path: str,
    authors_yaml: str,
    source_archive_path: str | None = None,
    primary_source_path: str | None = None,
    source_manifest_path: str | None = None,
) -> str:
    source_type_label = SOURCE_TYPE_LABELS.get(entry.source_type, entry.source_type)
    source_page_label = (
        "Abstract page HTML" if entry.source_type == "arxiv" else "Raw HTML"
    )
    extra_snapshot_lines: list[str] = []
    if entry.canonical_id:
        canonical_id_label = {
            "sep": "SEP slug",
            "arxiv": "arXiv ID",
            "lesswrong": "LessWrong post ID",
        }.get(entry.source_type, "Canonical ID")
        extra_snapshot_lines.append(f"- {canonical_id_label}: {entry.canonical_id}")
    if source_archive_path:
        extra_snapshot_lines.append(
            f"- Source archive: [{source_archive_path}]({source_archive_path})"
        )
    if source_manifest_path:
        extra_snapshot_lines.append(
            f"- Source manifest: [{source_manifest_path}]({source_manifest_path})"
        )
    if primary_source_path:
        extra_snapshot_lines.append(
            f"- Primary source candidate: [{primary_source_path}]({primary_source_path})"
        )

    return f"""---
title: "{escape_quotes(entry.title)}"
type: source
source_type: {entry.source_type}
slug: {entry.slug}
url: "{escape_quotes(entry.url)}"
authors:
{authors_yaml}
first_published: "{escape_quotes(published_line)}"
fetched_at: "{escape_quotes(entry.fetched_at)}"
status: seed
description: "{source_type_label} source note for {escape_quotes(entry.title)} and its role in the current cluster."
tags:
  - "{entry.source_type}"
  - "{concept_slug}"
---

# {entry.title}

## Source Snapshot
- Authors: {authors_line}
- Publication info: {pubinfo_line}
- Raw markdown: [{source_md_path}]({source_md_path})
- {source_page_label}: [{source_html_path}]({source_html_path})
{"\n".join(extra_snapshot_lines)}

## Summary
- Fill this in after reading the source or discussing it with the LLM.

## Source Role
- Decide whether this source functions mainly as an overview, a bridge, a case study, or a person-centered entry for your current cluster.
- Note why it matters for the questions you are actually pursuing in the wiki.

## Core Claims
- Add the main theses of the entry.

## Important Passages
- Capture 2-3 sections, arguments, or examples you expect to cite again later.

## Key Terms And Positions
- List important concepts, distinctions, and schools of thought.

## Candidate Wiki Links
- [[concepts/{concept_slug}]]
- Add question pages once you know what you want to compare.

## Tensions With Existing Pages
- Note where this source sharpens, complicates, or disagrees with pages already in the wiki.

## Open Questions
- What do you want to compare or follow up on next?
"""


def render_person_page(person_title: str, slug: str) -> str:
    return f"""---
title: "{escape_quotes(person_title)}"
type: person
status: seed
description: "Seed person page for {escape_quotes(person_title)} and their relevance to the current cluster."
tags:
  - "history"
  - "{slug}"
---

# {person_title}

## Why This Person Matters
- Note which debates or concept pages make this person worth tracking.

## Main Connections
- Add concept, question, and source links as they become relevant.

## Key Works Or Roles
- Add primary texts, signature arguments, or recurring positions.

## Open Questions
- Which existing wiki pages most need this person page to be filled in next?
"""


def render_ingest_log_entry(
    entry: SourceEntry,
    *,
    timestamp: str,
    source_md: str,
    note_md: str,
) -> str:
    source_type_label = SOURCE_TYPE_LABELS.get(entry.source_type, entry.source_type)
    return f"""
## [{timestamp}] ingest | {entry.title}

- Source type: {source_type_label}
- URL: {entry.url}
- Raw markdown: {source_md}
- Source note: {note_md}
"""


def render_arxiv_source_manifest(
    entry: SourceEntry,
    *,
    source_markdown_name: str,
    abstract_page_name: str,
    source_archive_name: str,
    extracted_files: list[Path],
    primary_source_path: str | None,
) -> str:
    extracted_lines = [
        f"- [{path.as_posix()}]({path.as_posix()})" for path in extracted_files
    ]
    primary_line = (
        f"- Primary source candidate: [{primary_source_path}]({primary_source_path})"
        if primary_source_path
        else "- Primary source candidate: Could not determine one automatically."
    )
    abstract_block = entry.abstract or "No abstract metadata captured."

    return f"""# {entry.title}

## Source Snapshot
- arXiv ID: {entry.canonical_id or "Unknown"}
- Generated reading markdown: [{source_markdown_name}]({source_markdown_name})
- Abstract page HTML: [{abstract_page_name}]({abstract_page_name})
- Source archive: [{source_archive_name}]({source_archive_name})
{primary_line}
- Extracted file count: {len(extracted_files)}

## Abstract
{abstract_block}

## Extracted File Inventory
{"\n".join(extracted_lines) if extracted_lines else "- No extracted files were found."}
"""


def render_person_log_entry(
    *, slug: str, title: str, timestamp: str, page_md: str
) -> str:
    del slug
    return f"""
## [{timestamp}] seed | Person | {title}

- Page: {page_md}
"""
