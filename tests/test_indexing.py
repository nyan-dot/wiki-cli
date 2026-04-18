from __future__ import annotations

from pathlib import Path

from wiki_cli import paths
from wiki_cli.indexing import build_index

from .support import write_text


def test_build_index_uses_frontmatter_descriptions_and_titles(
    isolated_workspace: Path,
) -> None:
    paths.ensure_workspace()
    write_text(
        isolated_workspace / "wiki" / "sources" / "zeta.md",
        """
        ---
        title: "Zeta"
        type: source
        source_type: sep
        slug: zeta
        url: "https://example.invalid/zeta"
        authors:
          - "Zee"
        first_published: "2026/04/17"
        fetched_at: "2026-04-17T00:00:00+00:00"
        status: seed
        description: "Later source note."
        ---

        # Zeta
        """,
    )
    write_text(
        isolated_workspace / "wiki" / "sources" / "alpha.md",
        """
        ---
        title: "Alpha"
        type: source
        source_type: sep
        slug: alpha
        url: "https://example.invalid/alpha"
        authors:
          - "Able, Ann"
        first_published: "2026/04/17"
        fetched_at: "2026-04-17T00:00:00+00:00"
        status: seed
        description: "Earlier source note."
        ---

        # Alpha
        """,
    )

    build_index()
    updated = (isolated_workspace / "wiki" / "index.md").read_text(encoding="utf-8")

    assert updated.index("[[sources/alpha|Alpha]]") < updated.index(
        "[[sources/zeta|Zeta]]"
    )
    assert "- [[sources/alpha|Alpha]] - Earlier source note." in updated
    assert "- [[sources/zeta|Zeta]] - Later source note." in updated
