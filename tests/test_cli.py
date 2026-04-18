from __future__ import annotations

import sys
from pathlib import Path

import pytest

from wiki_cli import paths
from wiki_cli.cli import main
from wiki_cli.commands.ingest import seed_person_command
from wiki_cli.commands.maintenance import build_index_command, list_pages_command

from .support import read_machine_log, seed_clean_workspace, seed_index_and_log


def test_seed_person_creates_page_updates_index_and_logs(
    isolated_workspace: Path,
) -> None:
    paths.ensure_workspace()
    seed_index_and_log(isolated_workspace)

    args = type(
        "Args",
        (),
        {"slug": "augustine", "title": "Augustine", "force": False},
    )()

    seed_person_command(args)

    person_path = isolated_workspace / "wiki" / "people" / "augustine.md"
    person_text = person_path.read_text(encoding="utf-8")
    index_text = (isolated_workspace / "wiki" / "index.md").read_text(encoding="utf-8")
    log_text = (isolated_workspace / "wiki" / "log.md").read_text(encoding="utf-8")

    assert 'title: "Augustine"' in person_text
    assert (
        'description: "Seed person page for Augustine and their relevance to the current cluster."'
        in person_text
    )
    assert "type: person" in person_text
    assert "## Why This Person Matters" in person_text
    assert (
        "- [[people/augustine|Augustine]] - "
        "Seed person page for Augustine and their relevance to the current cluster."
    ) in index_text
    assert "seed | Person | Augustine" in log_text


def test_list_pages_filters_records(
    isolated_workspace: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed_clean_workspace(
        isolated_workspace,
        question_sources=[
            "[[sources/test-entry]]",
            "[[sources/test-entry]]",
        ],
    )

    args = type(
        "Args",
        (),
        {
            "type": "concept",
            "status": "seed",
            "tag": ["lint"],
            "contains": "lint",
            "format": "text",
        },
    )()

    list_pages_command(args)
    output = capsys.readouterr().out

    assert (
        "concept | seed | Test Entry | wiki/concepts/test-entry.md | "
        "Minimal concept page for lint coverage. | tags=test-cluster, lint"
    ) in output
    assert "question |" not in output


def test_build_index_command_writes_machine_log(isolated_workspace: Path) -> None:
    seed_clean_workspace(
        isolated_workspace,
        question_sources=[
            "[[sources/test-entry]]",
            "[[sources/test-entry]]",
        ],
    )

    build_index_command(type("Args", (), {})())
    events = read_machine_log(isolated_workspace)

    assert any(event["event"] == "index_rebuilt" for event in events)
    rebuilt = next(event for event in events if event["event"] == "index_rebuilt")
    assert rebuilt["command"] == "build-index"
    assert rebuilt["page_count"] >= 3
    assert rebuilt["path"] == "wiki/index.md"


def test_main_logs_failed_command(
    isolated_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths.ensure_workspace()
    seed_index_and_log(isolated_workspace)
    monkeypatch.setattr(sys, "argv", ["main.py", "seed-note", "missing-slug"])

    exit_code = main()
    events = read_machine_log(isolated_workspace)

    assert exit_code == 1
    assert any(event["event"] == "command_started" for event in events)
    failed = next(event for event in events if event["event"] == "command_failed")
    assert failed["command"] == "seed-note"
    assert failed["error_type"] == "FileNotFoundError"
