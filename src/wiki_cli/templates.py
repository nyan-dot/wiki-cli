from __future__ import annotations

from .models import SepEntry
from .utils import escape_quotes


def render_source_note(
    entry: SepEntry,
    *,
    authors_line: str,
    published_line: str,
    pubinfo_line: str,
    concept_slug: str,
    source_md_path: str,
    source_html_path: str,
    authors_yaml: str,
) -> str:
    return f"""---
title: "{escape_quotes(entry.title)}"
type: source
source_type: sep
slug: {entry.slug}
url: "{escape_quotes(entry.url)}"
authors:
{authors_yaml}
first_published: "{escape_quotes(published_line)}"
fetched_at: "{escape_quotes(entry.fetched_at)}"
status: seed
description: "SEP source note for {escape_quotes(entry.title)} and its role in the current cluster."
tags:
  - "sep"
  - "{concept_slug}"
---

# {entry.title}

## Source Snapshot
- Authors: {authors_line}
- Publication info: {pubinfo_line}
- Raw markdown: [{source_md_path}]({source_md_path})
- Raw HTML: [{source_html_path}]({source_html_path})

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
    entry: SepEntry,
    *,
    timestamp: str,
    source_md: str,
    note_md: str,
) -> str:
    return f"""
## [{timestamp}] ingest | {entry.title}

- Source type: SEP
- URL: {entry.url}
- Raw markdown: {source_md}
- Source note: {note_md}
"""


def render_person_log_entry(*, slug: str, title: str, timestamp: str, page_md: str) -> str:
    del slug
    return f"""
## [{timestamp}] seed | Person | {title}

- Page: {page_md}
"""
