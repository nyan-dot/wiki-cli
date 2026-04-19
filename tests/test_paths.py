from __future__ import annotations

import importlib
from pathlib import Path

import wiki_cli.paths as paths


def test_paths_root_defaults_to_current_working_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = Path(__file__).resolve().parents[1]

    monkeypatch.delenv("WIKI_CONTENT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    reloaded = importlib.reload(paths)

    assert tmp_path.resolve() == reloaded.ROOT
    assert tmp_path.resolve() / "raw" / "sep" == reloaded.RAW_SEP_ROOT
    assert tmp_path.resolve() / "raw" / "arxiv" == reloaded.RAW_ARXIV_ROOT
    assert tmp_path.resolve() / "raw" / "sep" == reloaded.RAW_ROOT
    assert tmp_path.resolve() / "wiki" == reloaded.WIKI_ROOT

    monkeypatch.chdir(project_root)
    importlib.reload(paths)
