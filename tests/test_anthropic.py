from __future__ import annotations

import textwrap
from pathlib import Path

from wiki_cli import paths
from wiki_cli.anthropic import (
    convert_anthropic_html_to_markdown,
    extract_anthropic_article_html,
    normalize_anthropic_url,
    parse_anthropic_entry,
)
from wiki_cli.notes import import_anthropic

from .support import seed_index_and_log

FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "anthropic"


def sample_anthropic_html() -> str:
    return textwrap.dedent(
        """
        <html>
          <head>
            <title>On the Biology of a Large Language Model</title>
            <meta property="og:title" content="On the Biology of a Large Language Model">
            <meta property="og:description" content="A circuit-tracing tour through Claude 3.5 Haiku.">
          </head>
          <body>
            <d-front-matter>
              <script type="text/json">
                {
                  "title": "On the Biology of a Large Language Model",
                  "description": "",
                  "authors": []
                }
              </script>
            </d-front-matter>
            <d-article>
              <d-contents>
                <nav><a href="#intro">Contents</a></nav>
              </d-contents>
              <p>
                Intro paragraph with a <a href="./appendix.html">relative link</a>,
                a <a href="#intro">local jump</a>, and a
                <a href="https://transformer-circuits.pub/2025/attribution-graphs/biology.html#intro">canonical local jump</a>.
                <d-footnote>Inline note about <a href="#intro">this section</a>.</d-footnote>
              </p>
              <h2 id="intro">Introduction</h2>
              <p>Key claim.</p>
              <ul>
                <li>Mechanism
                  <ul>
                    <li>Subfeature</li>
                  </ul>
                </li>
              </ul>
              <figure>
                <img src="./png/biology.png" alt="Biology diagram">
              </figure>
              <blockquote>
                <p>Interpretable models are easier to study.</p>
              </blockquote>
              <div class="ha-block">
                <p>Human: What is 2+2?</p><br>
                <p>Assistant: 4</p>
              </div>
              <table>
                <tr><th>Feature</th><th>Role</th></tr>
                <tr><td>Neuron</td><td>Signal</td></tr>
              </table>
            </d-article>
          </body>
        </html>
        """
    )


def test_normalize_anthropic_url_canonicalizes_article_urls() -> None:
    canonical_url, canonical_id, slug, year = normalize_anthropic_url(
        "https://www.transformer-circuits.pub/2025/attribution-graphs/biology.html?ref=foo#intro"
    )

    assert (
        canonical_url
        == "https://transformer-circuits.pub/2025/attribution-graphs/biology.html"
    )
    assert canonical_id == "2025/attribution-graphs/biology"
    assert slug == "biology"
    assert year == "2025"


def test_parse_anthropic_entry_reads_meta_and_path_metadata() -> None:
    entry = parse_anthropic_entry(
        "https://transformer-circuits.pub/2025/attribution-graphs/biology.html",
        sample_anthropic_html(),
    )

    assert entry.source_type == "anthropic"
    assert entry.slug == "biology"
    assert entry.title == "On the Biology of a Large Language Model"
    assert entry.authors == []
    assert entry.first_published == "2025"
    assert entry.pubinfo == "Transformer Circuits article (2025)"
    assert entry.abstract == "A circuit-tracing tour through Claude 3.5 Haiku."
    assert entry.canonical_id == "2025/attribution-graphs/biology"


def test_extract_and_convert_anthropic_body_to_markdown() -> None:
    article_html = extract_anthropic_article_html(sample_anthropic_html())
    markdown = convert_anthropic_html_to_markdown(
        article_html,
        base_url="https://transformer-circuits.pub/2025/attribution-graphs/biology.html",
        title="On the Biology of a Large Language Model",
        description="A circuit-tracing tour through Claude 3.5 Haiku.",
    )

    assert "# On the Biology of a Large Language Model" in markdown
    assert "A circuit-tracing tour through Claude 3.5 Haiku." in markdown
    assert "Contents" not in markdown
    assert (
        "[relative link](https://transformer-circuits.pub/2025/attribution-graphs/appendix.html)"
        in markdown
    )
    assert "[local jump](#introduction)" in markdown
    assert "[canonical local jump](#introduction)" in markdown
    assert "[canonical local jump](#introduction). [^1]" in markdown
    assert "[^1]" in markdown
    assert "[^1]: Inline note about [this section](#introduction)." in markdown
    assert "## Introduction" in markdown
    assert "- Mechanism" in markdown
    assert "  - Subfeature" in markdown
    assert (
        "![Biology diagram](https://transformer-circuits.pub/2025/attribution-graphs/png/biology.png)"
        in markdown
    )
    assert "> Interpretable models are easier to study." in markdown
    assert "> Human: What is 2+2?" in markdown
    assert "> Assistant: 4" in markdown
    assert "| Feature | Role |" in markdown
    assert "| Neuron | Signal |" in markdown


def test_convert_anthropic_html_to_markdown_from_realistic_fixture() -> None:
    article_html = (FIXTURES_ROOT / "biology_excerpt.html").read_text(encoding="utf-8")

    markdown = convert_anthropic_html_to_markdown(
        article_html,
        base_url="https://transformer-circuits.pub/2025/attribution-graphs/biology.html",
        title="On the Biology of a Large Language Model",
    )

    assert "Contents" not in markdown
    assert "## [Introduction](#introduction)" in markdown
    assert "[Related Work](#related-work)" in markdown
    assert "[Limitations](#limitations)" in markdown
    assert "[^1]" in markdown
    assert "[^1]: The analogy should not be taken too literally." in markdown
    assert "> Human: Please reason step by step." in markdown
    assert "> Assistant: I will trace the internal features." in markdown
    assert (
        "[the companion paper](https://transformer-circuits.pub/2025/attribution-graphs/methods.html)"
        in markdown
    )


def test_convert_anthropic_html_to_markdown_keeps_cross_article_links_remote() -> None:
    article_html = textwrap.dedent(
        """
        <d-article>
          <p>
            Read the <a href="https://transformer-circuits.pub/2025/attribution-graphs/methods.html#graphs-tutorial">methods tutorial</a>.
          </p>
          <h2 id="intro">Introduction</h2>
        </d-article>
        """
    )

    markdown = convert_anthropic_html_to_markdown(
        article_html,
        base_url="https://transformer-circuits.pub/2025/attribution-graphs/biology.html",
    )

    assert (
        "[methods tutorial](https://transformer-circuits.pub/2025/attribution-graphs/methods.html#graphs-tutorial)"
        in markdown
    )


def test_convert_anthropic_html_to_markdown_renders_multiline_footnotes() -> None:
    article_html = textwrap.dedent(
        """
        <d-article>
          <p>Body text<d-footnote><p>First line.</p><p>Second line.</p></d-footnote></p>
        </d-article>
        """
    )

    markdown = convert_anthropic_html_to_markdown(
        article_html,
        base_url="https://transformer-circuits.pub/2025/attribution-graphs/biology.html",
    )

    assert "Body text[^1]" in markdown
    assert "[^1]: First line." in markdown
    assert "    Second line." in markdown


def test_convert_anthropic_html_to_markdown_preserves_two_digit_footnote_numbers() -> (
    None
):
    footnotes = "".join(
        f"<p>Item {index}<d-footnote>Footnote {index}</d-footnote></p>"
        for index in range(1, 13)
    )
    article_html = f"<d-article>{footnotes}</d-article>"

    markdown = convert_anthropic_html_to_markdown(
        article_html,
        base_url="https://transformer-circuits.pub/2025/attribution-graphs/biology.html",
    )

    assert "Item 9[^9]" in markdown
    assert "Item 10[^10]" in markdown
    assert "Item 11[^11]" in markdown
    assert "Item 12[^12]" in markdown
    assert "[^10]: Footnote 10" in markdown
    assert "[^11]: Footnote 11" in markdown
    assert "[^12]: Footnote 12" in markdown


def test_import_anthropic_writes_expected_files(
    isolated_workspace: Path,
    monkeypatch,
) -> None:
    paths.ensure_workspace()
    seed_index_and_log(isolated_workspace)
    monkeypatch.setattr(
        "wiki_cli.notes.anthropic.fetch_url",
        lambda _url: sample_anthropic_html(),
    )

    entry = import_anthropic(
        "https://transformer-circuits.pub/2025/attribution-graphs/biology.html",
        slug=None,
        force=False,
    )

    raw_dir = paths.raw_root("anthropic") / entry.slug
    assert (raw_dir / "source.html").exists()
    assert (raw_dir / "source.md").exists()
    assert (raw_dir / "meta.json").exists()

    note_text = (isolated_workspace / "wiki" / "sources" / "biology.md").read_text(
        encoding="utf-8"
    )
    assert "source_type: anthropic" in note_text
    assert (
        "- Transformer Circuits article ID: 2025/attribution-graphs/biology"
        in note_text
    )
    assert "Raw markdown:" in note_text
