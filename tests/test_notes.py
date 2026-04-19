from __future__ import annotations

from pathlib import Path

from wiki_cli import paths
from wiki_cli.models import SourceEntry
from wiki_cli.notes import append_log_entry, create_person_page, create_source_note

from .support import seed_index_and_log


def test_create_source_note_includes_house_style_sections(
    isolated_workspace: Path,
) -> None:
    paths.ensure_workspace()
    raw_dir = paths.raw_root("sep") / "sample-entry"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "source.md").write_text("# Sample Entry\n", encoding="utf-8")
    (raw_dir / "source.html").write_text("<html></html>\n", encoding="utf-8")
    (raw_dir / "notes.html").write_text("<html></html>\n", encoding="utf-8")

    entry = SourceEntry(
        source_type="sep",
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
    assert "Notes HTML:" in note_text


def test_create_arxiv_source_note_includes_archive_and_primary_source(
    isolated_workspace: Path,
) -> None:
    paths.ensure_workspace()
    raw_dir = paths.raw_root("arxiv") / "attention-is-all-you-need"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "source.md").write_text("# Manifest\n", encoding="utf-8")
    (raw_dir / "manifest.md").write_text("# Manifest\n", encoding="utf-8")
    (raw_dir / "abs.html").write_text("<html></html>\n", encoding="utf-8")
    (raw_dir / "source.tar.gz").write_bytes(b"test")
    extracted_dir = raw_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    (extracted_dir / "main.tex").write_text(
        "\\documentclass{article}\n", encoding="utf-8"
    )

    entry = SourceEntry(
        source_type="arxiv",
        slug="attention-is-all-you-need",
        title="Attention Is All You Need",
        url="https://arxiv.org/abs/1706.03762",
        authors=["Vaswani, Ashish"],
        first_published="2017/06/12",
        pubinfo="Submitted on 12 Jun 2017",
        fetched_at="2026-04-18T00:00:00+00:00",
        canonical_id="1706.03762",
        source_archive_name="source.tar.gz",
        primary_source_path="extracted/main.tex",
    )

    note_path = create_source_note(entry, force=False)
    note_text = note_path.read_text(encoding="utf-8")

    assert "source_type: arxiv" in note_text
    assert (
        'description: "arXiv source note for Attention Is All You Need and its role in the current cluster."'
        in note_text
    )
    assert '  - "arxiv"' in note_text
    assert "- arXiv ID: 1706.03762" in note_text
    assert "Source archive:" in note_text
    assert "Source manifest:" in note_text
    assert "Primary source candidate:" in note_text


def test_create_lesswrong_source_note_includes_post_id(
    isolated_workspace: Path,
) -> None:
    paths.ensure_workspace()
    raw_dir = paths.raw_root("lesswrong") / "logit-lens"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "source.md").write_text("# Post\n", encoding="utf-8")
    (raw_dir / "source.html").write_text("<html></html>\n", encoding="utf-8")

    entry = SourceEntry(
        source_type="lesswrong",
        slug="logit-lens",
        title="interpreting GPT: the logit lens",
        url="https://www.lesswrong.com/posts/AcKRB8wDpdaN6v6ru/interpreting-gpt-the-logit-lens",
        authors=["nostalgebraist"],
        first_published="2020-08-31",
        pubinfo="31st Aug 2020",
        fetched_at="2026-04-18T00:00:00+00:00",
        canonical_id="AcKRB8wDpdaN6v6ru",
    )

    note_path = create_source_note(entry, force=False)
    note_text = note_path.read_text(encoding="utf-8")

    assert "source_type: lesswrong" in note_text
    assert (
        'description: "LessWrong source note for interpreting GPT: the logit lens and its role in the current cluster."'
        in note_text
    )
    assert '  - "lesswrong"' in note_text
    assert "- LessWrong post ID: AcKRB8wDpdaN6v6ru" in note_text


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


def test_append_log_entry_skips_duplicate_ingest_for_same_source(
    isolated_workspace: Path,
) -> None:
    paths.ensure_workspace()
    seed_index_and_log(isolated_workspace)

    entry = SourceEntry(
        source_type="lesswrong",
        slug="simulators",
        title="Simulators",
        url="https://www.lesswrong.com/posts/vJFdjigzmcXMhNTsx/simulators",
        authors=["janus"],
        first_published="2022-09-02",
        pubinfo="2nd Sep 2022",
        fetched_at="2026-04-18T00:00:00+00:00",
        canonical_id="vJFdjigzmcXMhNTsx",
    )

    append_log_entry(entry)
    append_log_entry(entry)

    log_text = (paths.WIKI_ROOT / "log.md").read_text(encoding="utf-8")
    assert log_text.count("## [") == 1
    assert (
        log_text.count(
            "- URL: https://www.lesswrong.com/posts/vJFdjigzmcXMhNTsx/simulators"
        )
        == 1
    )


def test_append_log_entry_keeps_distinct_ingests_with_same_title(
    isolated_workspace: Path,
) -> None:
    paths.ensure_workspace()
    seed_index_and_log(isolated_workspace)

    first = SourceEntry(
        source_type="lesswrong",
        slug="simulators",
        title="Simulators",
        url="https://www.lesswrong.com/posts/vJFdjigzmcXMhNTsx/simulators",
        authors=["janus"],
        first_published="2022-09-02",
        pubinfo="2nd Sep 2022",
        fetched_at="2026-04-18T00:00:00+00:00",
        canonical_id="vJFdjigzmcXMhNTsx",
    )
    second = SourceEntry(
        source_type="lesswrong",
        slug="simulators-alt",
        title="Simulators",
        url="https://www.lesswrong.com/posts/another-post-id/simulators",
        authors=["someone-else"],
        first_published="2026-04-18",
        pubinfo="18th Apr 2026",
        fetched_at="2026-04-18T00:00:00+00:00",
        canonical_id="another-post-id",
    )

    append_log_entry(first)
    append_log_entry(second)

    log_text = (paths.WIKI_ROOT / "log.md").read_text(encoding="utf-8")
    assert log_text.count("## [") == 2
    assert log_text.count("- Source type: LessWrong") == 2
