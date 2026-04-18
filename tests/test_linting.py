from __future__ import annotations

from pathlib import Path

from wiki_cli.linting import lint_wiki

from .support import seed_clean_workspace, write_text


def test_lint_wiki_accepts_clean_minimal_workspace(isolated_workspace: Path) -> None:
    seed_clean_workspace(
        isolated_workspace,
        question_sources=[
            "[[sources/test-entry]]",
            "[[sources/test-entry]]",
        ],
    )

    assert lint_wiki() == []


def test_lint_wiki_warns_when_question_has_only_one_source(isolated_workspace: Path) -> None:
    seed_clean_workspace(
        isolated_workspace,
        question_sources=["[[sources/test-entry]]"],
    )

    findings = lint_wiki()

    assert any(
        "Question pages should usually cite at least two `sources` entries."
        in finding.message
        for finding in findings
    )


def test_lint_wiki_warns_when_index_is_out_of_date(isolated_workspace: Path) -> None:
    seed_clean_workspace(
        isolated_workspace,
        question_sources=[
            "[[sources/test-entry]]",
            "[[sources/test-entry]]",
        ],
    )

    write_text(
        isolated_workspace / "wiki" / "index.md",
        """
        # Wiki Index
        """,
    )

    findings = lint_wiki()

    assert any(
        "wiki/index.md is out of date. Run `python main.py build-index`."
        in finding.message
        for finding in findings
    )


def test_lint_wiki_warns_when_tag_needs_normalization(
    isolated_workspace: Path,
) -> None:
    seed_clean_workspace(
        isolated_workspace,
        question_sources=[
            "[[sources/test-entry]]",
            "[[sources/test-entry]]",
        ],
    )

    concept_path = isolated_workspace / "wiki" / "concepts" / "test-entry.md"
    concept_text = concept_path.read_text(encoding="utf-8").replace(
        '  - "test-cluster"\n  - "lint"\n',
        '  - "Test Cluster"\n  - "lint"\n',
    )
    concept_path.write_text(concept_text, encoding="utf-8")

    findings = lint_wiki()

    assert any(
        "Frontmatter tag `Test Cluster` should be normalized as `test-cluster`."
        in finding.message
        for finding in findings
    )
