from __future__ import annotations

from pathlib import Path

import pytest

from wiki_cli import paths


@pytest.fixture
def isolated_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "RAW_SEP_ROOT", tmp_path / "raw" / "sep")
    monkeypatch.setattr(paths, "RAW_ARXIV_ROOT", tmp_path / "raw" / "arxiv")
    monkeypatch.setattr(paths, "RAW_LESSWRONG_ROOT", tmp_path / "raw" / "lesswrong")
    monkeypatch.setattr(paths, "RAW_ANTHROPIC_ROOT", tmp_path / "raw" / "anthropic")
    monkeypatch.setattr(paths, "RAW_ROOT", tmp_path / "raw" / "sep")
    monkeypatch.setattr(
        paths,
        "RAW_SOURCE_ROOTS",
        {
            "sep": tmp_path / "raw" / "sep",
            "arxiv": tmp_path / "raw" / "arxiv",
            "lesswrong": tmp_path / "raw" / "lesswrong",
            "anthropic": tmp_path / "raw" / "anthropic",
        },
    )
    monkeypatch.setattr(paths, "WIKI_ROOT", tmp_path / "wiki")
    monkeypatch.setattr(paths, "SOURCE_NOTES_ROOT", tmp_path / "wiki" / "sources")
    return tmp_path
