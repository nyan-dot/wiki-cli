from __future__ import annotations

import os
from pathlib import Path


def default_root() -> Path:
    configured_root = os.environ.get("WIKI_CONTENT_ROOT")
    if configured_root:
        return Path(configured_root).expanduser().resolve()
    return Path.cwd().resolve()


ROOT = default_root()
RAW_SEP_ROOT = ROOT / "raw" / "sep"
RAW_ARXIV_ROOT = ROOT / "raw" / "arxiv"
RAW_ROOT = RAW_SEP_ROOT
RAW_SOURCE_ROOTS = {
    "sep": RAW_SEP_ROOT,
    "arxiv": RAW_ARXIV_ROOT,
}
WIKI_ROOT = ROOT / "wiki"
SOURCE_NOTES_ROOT = WIKI_ROOT / "sources"


def log_root() -> Path:
    return ROOT / "logs"


def activity_log_path() -> Path:
    return log_root() / "wiki.jsonl"


def raw_root(source_type: str) -> Path:
    try:
        return RAW_SOURCE_ROOTS[source_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported source type: {source_type}") from exc


def ensure_workspace() -> None:
    for path in [
        RAW_SEP_ROOT,
        RAW_ARXIV_ROOT,
        SOURCE_NOTES_ROOT,
        WIKI_ROOT / "concepts",
        WIKI_ROOT / "people",
        WIKI_ROOT / "questions",
        log_root(),
    ]:
        path.mkdir(parents=True, exist_ok=True)
