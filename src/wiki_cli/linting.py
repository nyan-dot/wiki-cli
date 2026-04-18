from __future__ import annotations

import re
from pathlib import Path

from . import paths
from .constants import ALLOWED_STATUSES, SECTION_TYPES
from .content import extract_wiki_links, iter_content_pages, resolve_wiki_link
from .indexing import build_index_text
from .models import LintFinding
from .utils import frontmatter_list, normalize_tag, parse_frontmatter


def add_finding(
    findings: list[LintFinding], level: str, path: Path, message: str
) -> None:
    findings.append(LintFinding(level=level, path=path, message=message))


def page_has_heading(text: str, heading: str) -> bool:
    normalized = heading.strip()
    pattern = rf"(?m)^##\s+{re.escape(normalized)}\s*$"
    return re.search(pattern, text) is not None


def lint_wiki() -> list[LintFinding]:
    findings: list[LintFinding] = []

    index_path = paths.WIKI_ROOT / "index.md"
    log_path = paths.WIKI_ROOT / "log.md"

    if not index_path.exists():
        raise FileNotFoundError("wiki/index.md is missing.")
    if not log_path.exists():
        raise FileNotFoundError("wiki/log.md is missing.")

    index_text = index_path.read_text(encoding="utf-8")
    log_text = log_path.read_text(encoding="utf-8")
    raw_slugs_by_type = {
        source_type: (
            {path.name for path in raw_root.iterdir() if path.is_dir()}
            if raw_root.exists()
            else set()
        )
        for source_type, raw_root in paths.RAW_SOURCE_ROOTS.items()
    }
    parse_failed = False

    for path in iter_content_pages():
        relative_path = path.relative_to(paths.ROOT)
        text = path.read_text(encoding="utf-8")

        try:
            frontmatter = parse_frontmatter(text)
        except ValueError as exc:
            add_finding(findings, "error", relative_path, str(exc))
            parse_failed = True
            continue

        section = path.parent.name
        slug = path.stem
        expected_type = SECTION_TYPES[section]

        title = frontmatter.get("title")
        page_type = frontmatter.get("type")
        status = frontmatter.get("status")
        description = str(frontmatter.get("description") or "").strip()
        tags = frontmatter_list(frontmatter, "tags")
        source_notes = frontmatter_list(frontmatter, "source_notes")
        related_questions = frontmatter_list(frontmatter, "related_questions")
        sources = frontmatter_list(frontmatter, "sources")

        if not title:
            add_finding(
                findings, "error", relative_path, "Missing `title` in frontmatter."
            )
        if page_type != expected_type:
            add_finding(
                findings,
                "error",
                relative_path,
                f"Expected `type: {expected_type}`, found `{page_type}`.",
            )
        if status not in ALLOWED_STATUSES:
            add_finding(
                findings,
                "error",
                relative_path,
                f"`status` should be one of: {', '.join(sorted(ALLOWED_STATUSES))}.",
            )
        if not description:
            add_finding(
                findings,
                "warning",
                relative_path,
                "Missing `description` in frontmatter.",
            )
        for tag in tags:
            normalized_tag = normalize_tag(tag)
            if not normalized_tag:
                add_finding(
                    findings,
                    "warning",
                    relative_path,
                    "Frontmatter `tags` contains an empty or invalid value.",
                )
                continue
            if tag != normalized_tag:
                add_finding(
                    findings,
                    "warning",
                    relative_path,
                    f"Frontmatter tag `{tag}` should be normalized as `{normalized_tag}`.",
                )

        if section == "sources":
            for key in ["source_type", "slug", "url"]:
                if not frontmatter.get(key):
                    add_finding(
                        findings,
                        "error",
                        relative_path,
                        f"Missing `{key}` in source note frontmatter.",
                    )

            note_slug = frontmatter.get("slug")
            source_type = str(frontmatter.get("source_type") or "").strip()
            if note_slug and note_slug != slug:
                add_finding(
                    findings,
                    "warning",
                    relative_path,
                    f"Frontmatter slug `{note_slug}` does not match filename `{slug}`.",
                )

            if source_type not in paths.RAW_SOURCE_ROOTS:
                add_finding(
                    findings,
                    "error",
                    relative_path,
                    f"Unsupported source type `{source_type}`.",
                )
            elif slug not in raw_slugs_by_type[source_type]:
                add_finding(
                    findings,
                    "error",
                    relative_path,
                    f"Missing matching raw import under `raw/{source_type}/{slug}/`.",
                )

            if f"wiki/sources/{slug}.md" not in log_text:
                add_finding(
                    findings,
                    "warning",
                    relative_path,
                    "Source note does not appear in `wiki/log.md`.",
                )

            if not page_has_heading(text, "Source Role"):
                add_finding(
                    findings,
                    "warning",
                    relative_path,
                    "Source note is missing the `## Source Role` section.",
                )

            if not page_has_heading(text, "Important Passages"):
                add_finding(
                    findings,
                    "warning",
                    relative_path,
                    "Source note is missing the `## Important Passages` section.",
                )

            if not page_has_heading(text, "Tensions With Existing Pages"):
                add_finding(
                    findings,
                    "warning",
                    relative_path,
                    "Source note is missing the `## Tensions With Existing Pages` section.",
                )
        elif section == "concepts":
            if not source_notes:
                add_finding(
                    findings,
                    "warning",
                    relative_path,
                    "Concept pages should usually declare at least one `source_notes` entry.",
                )

            if not related_questions:
                add_finding(
                    findings,
                    "warning",
                    relative_path,
                    "Concept pages should usually declare at least one `related_questions` entry.",
                )
        elif section == "questions":
            if len(sources) < 2:
                add_finding(
                    findings,
                    "warning",
                    relative_path,
                    "Question pages should usually cite at least two `sources` entries.",
                )

        for link in extract_wiki_links(text):
            target = resolve_wiki_link(link)
            if target is None:
                continue
            if not target.exists():
                add_finding(
                    findings,
                    "warning",
                    relative_path,
                    f"Broken wiki link: [[{link}]]",
                )

    for source_type, raw_slugs in raw_slugs_by_type.items():
        for raw_slug in sorted(raw_slugs):
            note_path = paths.SOURCE_NOTES_ROOT / f"{raw_slug}.md"
            if not note_path.exists():
                add_finding(
                    findings,
                    "warning",
                    note_path.relative_to(paths.ROOT),
                    f"Raw import under `raw/{source_type}/` exists without a source note for `{raw_slug}`.",
                )

    if not parse_failed:
        expected_index = build_index_text()
        if index_text != expected_index:
            add_finding(
                findings,
                "warning",
                index_path.relative_to(paths.ROOT),
                "wiki/index.md is out of date. Run `python main.py build-index`.",
            )

    return findings
