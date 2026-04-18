from __future__ import annotations

import os
from pathlib import Path


def default_root() -> Path:
    configured_root = os.environ.get("WIKI_CONTENT_ROOT")
    if configured_root:
        return Path(configured_root).expanduser().resolve()
    return Path.cwd().resolve()


ROOT = default_root()
RAW_ROOT = ROOT / "raw" / "sep"
WIKI_ROOT = ROOT / "wiki"
SOURCE_NOTES_ROOT = WIKI_ROOT / "sources"


def log_root() -> Path:
    return ROOT / "logs"


def activity_log_path() -> Path:
    return log_root() / "wiki.jsonl"


def ensure_workspace() -> None:
    for path in [
        RAW_ROOT,
        SOURCE_NOTES_ROOT,
        WIKI_ROOT / "concepts",
        WIKI_ROOT / "people",
        WIKI_ROOT / "questions",
        log_root(),
    ]:
        path.mkdir(parents=True, exist_ok=True)
