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

    assert reloaded.ROOT == tmp_path.resolve()
    assert reloaded.RAW_SEP_ROOT == tmp_path.resolve() / "raw" / "sep"
    assert reloaded.RAW_ARXIV_ROOT == tmp_path.resolve() / "raw" / "arxiv"
    assert reloaded.RAW_ROOT == tmp_path.resolve() / "raw" / "sep"
    assert reloaded.WIKI_ROOT == tmp_path.resolve() / "wiki"

    monkeypatch.chdir(project_root)
    importlib.reload(paths)
