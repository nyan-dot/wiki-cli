from __future__ import annotations

import json
import textwrap
from pathlib import Path

from wiki_cli import paths
from wiki_cli.indexing import build_index
from wiki_cli.models import SourceEntry
from wiki_cli.notes import append_log_entry, create_source_note


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def read_machine_log(root: Path) -> list[dict[str, object]]:
    log_path = root / "logs" / "wiki.jsonl"
    if not log_path.exists():
        return []
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def seed_index_and_log(root: Path) -> None:
    write_text(
        root / "wiki" / "index.md",
        """
        # Wiki Index

        ## Sources
        <!-- SOURCES:START -->
        <!-- SOURCES:END -->

        ## Concepts
        - [[concepts/test-entry]] - Minimal concept page for lint coverage.

        ## People
        - Add philosopher pages here as they emerge.

        ## Questions
        - [[questions/test-question]] - Minimal question page for lint coverage.
        """,
    )
    write_text(
        root / "wiki" / "log.md",
        """
        # Wiki Log

        Append ingests, major queries, and lint passes here in chronological order.
        """,
    )


def seed_clean_workspace(root: Path, *, question_sources: list[str]) -> None:
    paths.ensure_workspace()
    seed_index_and_log(root)

    entry = SourceEntry(
        source_type="sep",
        slug="test-entry",
        title="Test Entry",
        url="https://example.invalid/test-entry",
        authors=["Example, Ada"],
        first_published="2026/04/17",
        pubinfo="First published Thu Apr 17, 2026",
        fetched_at="2026-04-17T00:00:00+00:00",
    )

    raw_entry_dir = paths.raw_root(entry.source_type) / entry.slug
    raw_entry_dir.mkdir(parents=True, exist_ok=True)
    write_text(raw_entry_dir / "source.md", "# Test Entry\n")
    write_text(raw_entry_dir / "source.html", "<html></html>\n")

    create_source_note(entry, force=False)
    append_log_entry(entry)

    write_text(
        root / "wiki" / "concepts" / "test-entry.md",
        """
        ---
        title: "Test Entry"
        type: concept
        status: seed
        description: "Minimal concept page for lint coverage."
        tags:
          - "test-cluster"
          - "lint"
        source_notes:
          - "[[sources/test-entry]]"
        related_questions:
          - "[[questions/test-question]]"
        ---

        # Test Entry

        ## Related Pages
        - [[sources/test-entry]]
        - [[questions/test-question]]
        """,
    )

    source_lines = "\n".join(f'  - "{source}"' for source in question_sources)
    write_text(
        root / "wiki" / "questions" / "test-question.md",
        (
            "---\n"
            'title: "Test Question"\n'
            "type: question\n"
            "status: seed\n"
            'description: "Minimal question page for lint coverage."\n'
            "tags:\n"
            '  - "test-cluster"\n'
            '  - "question"\n'
            "sources:\n"
            f"{source_lines}\n"
            "---\n\n"
            "# Test Question\n\n"
            "## Related Pages\n"
            "- [[concepts/test-entry]]\n"
        ),
    )

    build_index()
