from __future__ import annotations

import textwrap

from wiki_cli.utils import parse_frontmatter


def test_parse_frontmatter_parses_lists_and_quotes() -> None:
    frontmatter = parse_frontmatter(
        textwrap.dedent(
            """
            ---
            title: "Sample"
            type: question
            status: seed
            description: "Sample question."
            tags:
              - "free-will"
              - "comparison"
            sources:
              - "[[sources/freewill]]"
              - "[[sources/compatibilism]]"
            ---
            """
        ).strip()
    )

    assert frontmatter["title"] == "Sample"
    assert frontmatter["type"] == "question"
    assert frontmatter["description"] == "Sample question."
    assert frontmatter["tags"] == ["free-will", "comparison"]
    assert frontmatter["sources"] == ["[[sources/freewill]]", "[[sources/compatibilism]]"]
