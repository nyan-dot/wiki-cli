from __future__ import annotations

from pathlib import Path

from wiki_cli import paths
from wiki_cli.models import SepEntry
from wiki_cli.notes import create_person_page, create_source_note


def test_create_source_note_includes_house_style_sections(
    isolated_workspace: Path,
) -> None:
    paths.ensure_workspace()

    entry = SepEntry(
        slug="sample-entry",
        title="Sample Entry",
        url="https://example.invalid/sample-entry",
        authors=["Example, Bea"],
        first_published="2026/04/17",
        pubinfo="First published Thu Apr 17, 2026",
        fetched_at="2026-04-17T00:00:00+00:00",
    )

    note_path = create_source_note(entry, force=False)
    note_text = note_path.read_text(encoding="utf-8")

    assert (
        'description: "SEP source note for Sample Entry and its role in the current cluster."'
        in note_text
    )
    assert "tags:" in note_text
    assert '  - "sep"' in note_text
    assert '  - "sample-entry"' in note_text
    assert "## Source Role" in note_text
    assert "## Important Passages" in note_text
    assert "## Tensions With Existing Pages" in note_text
    assert "[[concepts/sample-entry]]" in note_text


def test_create_person_page_defaults_title_from_slug(isolated_workspace: Path) -> None:
    paths.ensure_workspace()

    person_path = create_person_page("thomas-aquinas", title=None, force=False)
    person_text = person_path.read_text(encoding="utf-8")

    assert 'title: "Thomas Aquinas"' in person_text
    assert (
        'description: "Seed person page for Thomas Aquinas and their relevance to the current cluster."'
        in person_text
    )
    assert '  - "history"' in person_text
    assert '  - "thomas-aquinas"' in person_text
    assert "# Thomas Aquinas" in person_text
