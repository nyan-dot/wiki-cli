from __future__ import annotations

import argparse
import json

from .. import paths
from ..activity import log_activity
from ..constants import ALLOWED_STATUSES, SECTION_TYPES
from ..content import default_index_description, filter_page_records, load_page_records
from ..indexing import build_index
from ..linting import lint_wiki


def lint_wiki_command(_args: argparse.Namespace) -> None:
    findings = lint_wiki()
    errors = [finding for finding in findings if finding.level == "error"]
    warnings = [finding for finding in findings if finding.level == "warning"]

    for finding in findings:
        print(f"{finding.level.upper()}: {finding.path.as_posix()} - {finding.message}")

    print(f"Lint finished with {len(errors)} error(s) and {len(warnings)} warning(s).")

    log_activity(
        "lint_completed",
        command_name="lint-wiki",
        errors=len(errors),
        warnings=len(warnings),
        findings=[
            {
                "level": finding.level,
                "path": finding.path.as_posix(),
                "message": finding.message,
            }
            for finding in findings
        ],
    )

    if errors:
        raise ValueError("Lint failed.")


def list_pages_command(args: argparse.Namespace) -> None:
    records = filter_page_records(
        load_page_records(),
        page_type=args.type,
        status=args.status,
        tags=args.tag,
        contains=args.contains,
    )

    log_activity(
        "pages_listed",
        command_name="list-pages",
        page_type=args.type,
        status=args.status,
        tags=args.tag,
        contains=args.contains,
        format=args.format,
        result_count=len(records),
    )

    if args.format == "json":
        print(
            json.dumps(
                [
                    {
                        "section": record.section,
                        "slug": record.slug,
                        "title": record.title,
                        "type": record.page_type,
                        "status": record.status,
                        "description": record.description,
                        "tags": record.tags,
                        "path": record.path,
                    }
                    for record in records
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    for record in records:
        description = record.description or default_index_description(record)
        tag_suffix = f" | tags={', '.join(record.tags)}" if record.tags else ""
        print(
            f"{record.page_type} | {record.status} | {record.title} | "
            f"{record.path} | {description}{tag_suffix}"
        )


def build_index_command(_args: argparse.Namespace) -> None:
    page_count = len(load_page_records())
    build_index()
    log_activity(
        "index_rebuilt",
        command_name="build-index",
        page_count=page_count,
        path=(paths.WIKI_ROOT / "index.md").relative_to(paths.ROOT),
    )
    print("Rebuilt wiki/index.md from page frontmatter.")


def register_list_pages_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    list_parser = subparsers.add_parser(
        "list-pages",
        help="List wiki pages from frontmatter metadata.",
    )
    list_parser.add_argument(
        "--type",
        choices=sorted(set(SECTION_TYPES.values())),
        help="Optional page type filter.",
    )
    list_parser.add_argument(
        "--status",
        choices=sorted(ALLOWED_STATUSES),
        help="Optional status filter.",
    )
    list_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Optional tag filter. Repeat to require multiple tags.",
    )
    list_parser.add_argument(
        "--contains",
        help="Optional substring filter across title, slug, description, and tags.",
    )
    list_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format.",
    )
    list_parser.set_defaults(func=list_pages_command)


def register_build_index_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    build_index_parser = subparsers.add_parser(
        "build-index",
        help="Regenerate wiki/index.md from page frontmatter.",
    )
    build_index_parser.set_defaults(func=build_index_command)


def register_lint_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    lint_parser = subparsers.add_parser(
        "lint-wiki",
        help="Check wiki frontmatter, links, and index/log consistency.",
    )
    lint_parser.set_defaults(func=lint_wiki_command)
