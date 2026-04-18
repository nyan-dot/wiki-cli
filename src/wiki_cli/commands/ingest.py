from __future__ import annotations

import argparse

from .. import paths
from ..activity import log_activity
from ..notes import (
    append_person_log_entry,
    create_person_page,
    create_source_note,
    import_sep,
    load_entry,
    update_index,
    update_people_index,
)
from ..utils import title_from_slug


def import_sep_command(args: argparse.Namespace) -> None:
    entry = import_sep(args.url, slug=args.slug, force=args.force)
    log_activity(
        "sep_imported",
        command_name="import-sep",
        slug=entry.slug,
        title=entry.title,
        url=entry.url,
        author_count=len(entry.authors),
    )
    print(f"Imported SEP entry: {entry.title} -> raw/sep/{entry.slug}")
    print(f"Seed note: wiki/sources/{entry.slug}.md")


def seed_note_command(args: argparse.Namespace) -> None:
    paths.ensure_workspace()
    entry = load_entry(args.slug)
    path = create_source_note(entry, force=args.force)
    update_index(entry)
    log_activity(
        "source_note_seeded",
        command_name="seed-note",
        slug=args.slug,
        force=args.force,
        path=path.relative_to(paths.ROOT),
    )
    print(f"Seeded source note: {path.relative_to(paths.ROOT).as_posix()}")


def seed_person_command(args: argparse.Namespace) -> None:
    paths.ensure_workspace()
    title = args.title or title_from_slug(args.slug)
    path = create_person_page(args.slug, title=title, force=args.force)
    update_people_index(args.slug, title)
    append_person_log_entry(args.slug, title)
    log_activity(
        "person_page_seeded",
        command_name="seed-person",
        slug=args.slug,
        title=title,
        force=args.force,
        path=path.relative_to(paths.ROOT),
    )
    print(f"Seeded person page: {path.relative_to(paths.ROOT).as_posix()}")


def register_import_sep_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import_parser = subparsers.add_parser(
        "import-sep",
        help="Fetch an SEP entry, convert it to Markdown, and seed a source note.",
    )
    import_parser.add_argument(
        "url",
        help="SEP entry URL, such as https://plato.stanford.edu/entries/freewill/",
    )
    import_parser.add_argument(
        "--slug",
        help="Optional slug override for the local entry directory.",
    )
    import_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing raw source files for the same slug.",
    )
    import_parser.set_defaults(func=import_sep_command)


def register_seed_note_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    seed_parser = subparsers.add_parser(
        "seed-note",
        help="Create or refresh a wiki source note from an existing raw SEP import.",
    )
    seed_parser.add_argument("slug", help="Slug under raw/sep/<slug>.")
    seed_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing wiki source note.",
    )
    seed_parser.set_defaults(func=seed_note_command)


def register_seed_person_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    person_parser = subparsers.add_parser(
        "seed-person",
        help="Create or refresh a wiki person page stub.",
    )
    person_parser.add_argument("slug", help="Slug under wiki/people/<slug>.md.")
    person_parser.add_argument(
        "--title",
        help="Optional display title. Defaults to a title-cased version of the slug.",
    )
    person_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing wiki person page.",
    )
    person_parser.set_defaults(func=seed_person_command)
