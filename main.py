from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_ROOT = ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def run() -> int:
    from wiki_cli.cli import main

    return main()


if __name__ == "__main__":
    raise SystemExit(run())
