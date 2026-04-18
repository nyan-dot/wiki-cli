from __future__ import annotations

from pathlib import Path

import pytest

from wiki_cli import paths


@pytest.fixture
def isolated_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "RAW_ROOT", tmp_path / "raw" / "sep")
    monkeypatch.setattr(paths, "WIKI_ROOT", tmp_path / "wiki")
    monkeypatch.setattr(paths, "SOURCE_NOTES_ROOT", tmp_path / "wiki" / "sources")
    return tmp_path
