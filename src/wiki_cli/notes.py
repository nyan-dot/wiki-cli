from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import arxiv, lesswrong, paths, sep
from .indexing import build_index
from .models import SourceEntry
from .templates import (
    render_arxiv_source_manifest,
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


def import_sep(url: str, slug: str | None, force: bool) -> SourceEntry:
    paths.ensure_workspace()

    page_html = sep.fetch_url(url)
    entry = sep.parse_sep_entry(url, page_html, slug)
    article_html = sep.extract_sep_article_html(page_html)
    source_markdown = sep.convert_sep_html_to_markdown(article_html, base_url=url)

    entry_dir = paths.raw_root(entry.source_type) / entry.slug
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


def import_lesswrong(url: str, slug: str | None, force: bool) -> SourceEntry:
    paths.ensure_workspace()

    normalized_url, _, _ = lesswrong.normalize_lesswrong_url(url)
    page_html = lesswrong.fetch_url(normalized_url)
    entry = lesswrong.parse_lesswrong_entry(normalized_url, page_html, slug)
    article_html = lesswrong.extract_lesswrong_post_html(page_html)
    source_markdown = lesswrong.convert_lesswrong_html_to_markdown(
        article_html,
        base_url=entry.url,
    )

    entry_dir = paths.raw_root(entry.source_type) / entry.slug
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


def import_arxiv_source(
    identifier_or_url: str,
    slug: str | None,
    force: bool,
) -> SourceEntry:
    paths.ensure_workspace()

    identifier = arxiv.normalize_arxiv_identifier(identifier_or_url)
    abs_url = arxiv.build_abs_url(identifier)
    page_html = arxiv.fetch_text(abs_url)
    entry = arxiv.parse_arxiv_entry(identifier, page_html, slug=slug)
    archive_bytes, headers = arxiv.fetch_binary(arxiv.build_src_url(identifier))

    archive_name = f"source{arxiv.archive_suffix(arxiv.filename_from_headers(headers))}"
    entry.source_archive_name = archive_name

    entry_dir = paths.raw_root(entry.source_type) / entry.slug
    if entry_dir.exists() and not force:
        raise FileExistsError(
            f"{entry_dir} already exists. Use --force to refresh the raw source files."
        )

    entry_dir.mkdir(parents=True, exist_ok=True)
    archive_path = entry_dir / archive_name
    archive_path.write_bytes(archive_bytes)
    (entry_dir / "abs.html").write_text(page_html, encoding="utf-8", newline="\n")

    extracted_dir = entry_dir / "extracted"
    extracted_files = arxiv.extract_archive(archive_path, extracted_dir)
    entry.primary_source_path = arxiv.choose_primary_source(entry_dir, extracted_files)

    reading_markdown = arxiv.build_reading_markdown(entry, entry_dir)
    manifest = render_arxiv_source_manifest(
        entry,
        source_markdown_name="source.md",
        abstract_page_name="abs.html",
        source_archive_name=archive_name,
        extracted_files=extracted_files,
        primary_source_path=entry.primary_source_path,
    )
    write_text(entry_dir / "source.md", reading_markdown, force=True)
    write_text(entry_dir / "manifest.md", manifest, force=True)
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


def load_entry(slug: str, *, source_type: str | None = None) -> SourceEntry:
    search_types = [source_type] if source_type else list(paths.RAW_SOURCE_ROOTS)
    meta_candidates: list[Path] = []
    for current_type in search_types:
        meta_path = paths.raw_root(current_type) / slug / "meta.json"
        if meta_path.exists():
            meta_candidates.append(meta_path)

    if not meta_candidates:
        search_roots = ", ".join(
            f"raw/{current_type}/{slug}/meta.json" for current_type in search_types
        )
        raise FileNotFoundError(
            f"Missing raw metadata file. Looked for: {search_roots}"
        )

    if len(meta_candidates) > 1:
        raise ValueError(
            f"Multiple raw imports match slug `{slug}`. Re-run with `--source-type`."
        )

    data = json.loads(meta_candidates[0].read_text(encoding="utf-8"))
    return SourceEntry(**data)


def create_source_note(entry: SourceEntry, force: bool) -> Path:
    note_path = paths.SOURCE_NOTES_ROOT / f"{entry.slug}.md"
    raw_root = paths.raw_root(entry.source_type)
    source_page_name = "abs.html" if entry.source_type == "arxiv" else "source.html"
    source_md_path = relative_markdown_path(
        note_path, raw_root / entry.slug / "source.md"
    )
    source_html_path = relative_markdown_path(
        note_path,
        raw_root / entry.slug / source_page_name,
    )
    source_archive_path = (
        relative_markdown_path(
            note_path, raw_root / entry.slug / entry.source_archive_name
        )
        if entry.source_archive_name
        else None
    )
    source_manifest_path = (
        relative_markdown_path(note_path, raw_root / entry.slug / "manifest.md")
        if entry.source_type == "arxiv"
        and (raw_root / entry.slug / "manifest.md").exists()
        else None
    )
    primary_source_path = (
        relative_markdown_path(
            note_path, raw_root / entry.slug / entry.primary_source_path
        )
        if entry.primary_source_path
        else None
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
        source_archive_path=source_archive_path,
        source_manifest_path=source_manifest_path,
        primary_source_path=primary_source_path,
    )

    write_text(note_path, content, force=force)
    return note_path


def create_person_page(slug: str, title: str | None, force: bool) -> Path:
    person_path = paths.WIKI_ROOT / "people" / f"{slug}.md"
    person_title = title or title_from_slug(slug)
    content = render_person_page(person_title, slug)
    write_text(person_path, content, force=force)
    return person_path


def update_index(entry: SourceEntry) -> None:
    del entry
    build_index()


def update_people_index(slug: str, title: str) -> None:
    del slug
    del title
    build_index()


def append_log_entry(entry: SourceEntry) -> None:
    log_path = paths.WIKI_ROOT / "log.md"
    if not log_path.exists():
        raise FileNotFoundError(
            "wiki/log.md is missing. Run `wiki init` or restore the scaffold files."
        )

    if ingest_log_entry_exists(log_path, entry):
        return

    timestamp = datetime.now().date().isoformat()
    source_md = (
        (paths.raw_root(entry.source_type) / entry.slug / "source.md")
        .relative_to(paths.ROOT)
        .as_posix()
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
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(entry_block)


def ingest_log_entry_exists(log_path: Path, entry: SourceEntry) -> bool:
    log_text = log_path.read_text(encoding="utf-8")
    source_type_label = ingest_source_type_label(entry)
    pattern = re.compile(
        r"^## \[[^\]]+\] ingest \| .*$\n(?P<body>(?:^(?!## ).*$\n?)*)",
        re.MULTILINE,
    )

    for match in pattern.finditer(log_text):
        body = match.group("body")
        if (
            f"- Source type: {source_type_label}" in body
            and f"- URL: {entry.url}" in body
        ):
            return True

    return False


def ingest_source_type_label(entry: SourceEntry) -> str:
    return {
        "sep": "SEP",
        "arxiv": "arXiv",
        "lesswrong": "LessWrong",
    }.get(entry.source_type, entry.source_type)


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
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(entry_block)
