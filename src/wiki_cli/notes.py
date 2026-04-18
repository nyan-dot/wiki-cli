from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import paths, sep
from .indexing import build_index
from .models import SepEntry
from .templates import (
    render_ingest_log_entry,
    render_person_log_entry,
    render_person_page,
    render_source_note,
)
from .utils import (
    relative_markdown_path,
    title_from_slug,
    write_text,
    yaml_list,
)


def import_sep(url: str, slug: str | None, force: bool) -> SepEntry:
    paths.ensure_workspace()

    page_html = sep.fetch_url(url)
    entry = sep.parse_sep_entry(url, page_html, slug)
    article_html = sep.extract_sep_article_html(page_html)
    source_markdown = sep.convert_sep_html_to_markdown(article_html, base_url=url)

    entry_dir = paths.RAW_ROOT / entry.slug
    if entry_dir.exists() and not force:
        raise FileExistsError(
            f"{entry_dir} already exists. Use --force to refresh the raw source files."
        )

    entry_dir.mkdir(parents=True, exist_ok=True)
    write_text(entry_dir / "source.html", page_html, force=True)
    write_text(entry_dir / "source.md", source_markdown, force=True)
    write_text(
        entry_dir / "meta.json",
        json.dumps(asdict(entry), indent=2, ensure_ascii=False) + "\n",
        force=True,
    )

    note_path = paths.SOURCE_NOTES_ROOT / f"{entry.slug}.md"
    if not note_path.exists():
        create_source_note(entry, force=False)
    update_index(entry)
    append_log_entry(entry)
    return entry


def load_entry(slug: str) -> SepEntry:
    meta_path = paths.RAW_ROOT / slug / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing raw metadata file: {meta_path}")

    data = json.loads(meta_path.read_text(encoding="utf-8"))
    return SepEntry(**data)


def create_source_note(entry: SepEntry, force: bool) -> Path:
    note_path = paths.SOURCE_NOTES_ROOT / f"{entry.slug}.md"
    source_md_path = relative_markdown_path(
        note_path, paths.RAW_ROOT / entry.slug / "source.md"
    )
    source_html_path = relative_markdown_path(
        note_path, paths.RAW_ROOT / entry.slug / "source.html"
    )

    authors_line = "; ".join(entry.authors) if entry.authors else "Unknown"
    published_line = entry.first_published or "Unknown"
    pubinfo_line = entry.pubinfo or "No publication info captured."
    concept_slug = sep.slugify(entry.title)
    content = render_source_note(
        entry,
        authors_line=authors_line,
        published_line=published_line,
        pubinfo_line=pubinfo_line,
        concept_slug=concept_slug,
        source_md_path=source_md_path,
        source_html_path=source_html_path,
        authors_yaml=yaml_list(entry.authors),
    )

    write_text(note_path, content, force=force)
    return note_path


def create_person_page(slug: str, title: str | None, force: bool) -> Path:
    person_path = paths.WIKI_ROOT / "people" / f"{slug}.md"
    person_title = title or title_from_slug(slug)
    content = render_person_page(person_title, slug)
    write_text(person_path, content, force=force)
    return person_path


def update_index(entry: SepEntry) -> None:
    del entry
    build_index()


def update_people_index(slug: str, title: str) -> None:
    del slug
    del title
    build_index()


def append_log_entry(entry: SepEntry) -> None:
    log_path = paths.WIKI_ROOT / "log.md"
    if not log_path.exists():
        raise FileNotFoundError(
            "wiki/log.md is missing. Run `wiki init` or restore the scaffold files."
        )

    timestamp = datetime.now().date().isoformat()
    source_md = (
        (paths.RAW_ROOT / entry.slug / "source.md").relative_to(paths.ROOT).as_posix()
    )
    note_md = (
        (paths.SOURCE_NOTES_ROOT / f"{entry.slug}.md")
        .relative_to(paths.ROOT)
        .as_posix()
    )
    entry_block = render_ingest_log_entry(
        entry,
        timestamp=timestamp,
        source_md=source_md,
        note_md=note_md,
    )
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(entry_block)


def append_person_log_entry(slug: str, title: str) -> None:
    log_path = paths.WIKI_ROOT / "log.md"
    if not log_path.exists():
        raise FileNotFoundError(
            "wiki/log.md is missing. Run `wiki init` or restore the scaffold files."
        )

    timestamp = datetime.now().date().isoformat()
    page_md = (
        (paths.WIKI_ROOT / "people" / f"{slug}.md").relative_to(paths.ROOT).as_posix()
    )
    entry_block = render_person_log_entry(
        slug=slug,
        title=title,
        timestamp=timestamp,
        page_md=page_md,
    )
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(entry_block)
