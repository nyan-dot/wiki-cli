from __future__ import annotations

import textwrap

from wiki_cli.sep import convert_sep_html_to_markdown, parse_sep_entry, slugify


def test_slugify_normalizes_text() -> None:
    assert (
        slugify(" Free Will & Moral Responsibility ")
        == "free-will-moral-responsibility"
    )
    assert slugify("!!!") == "sep-entry"


def test_parse_sep_entry_reads_meta_and_pubinfo() -> None:
    html = textwrap.dedent(
        """
        <html>
          <head>
            <title>Free Will (Stanford Encyclopedia of Philosophy)</title>
            <meta name="citation_title" content="Free Will">
            <meta name="citation_author" content="O窶僂onnor, Timothy">
            <meta name="citation_author" content="Franklin, Christopher">
            <meta name="citation_publication_date" content="2002/01/07">
          </head>
          <body>
            <div id="pubinfo">
              First published Mon Jan 7, 2002; substantive revision Thu Nov 3, 2022
            </div>
          </body>
        </html>
        """
    )

    entry = parse_sep_entry(
        "https://plato.stanford.edu/entries/freewill/",
        html,
    )

    assert entry.slug == "freewill"
    assert entry.title == "Free Will"
    assert entry.authors == ["O窶僂onnor, Timothy", "Franklin, Christopher"]
    assert entry.first_published == "2002/01/07"
    assert (
        entry.pubinfo
        == "First published Mon Jan 7, 2002; substantive revision Thu Nov 3, 2022"
    )
    assert entry.source_type == "sep"


def test_parse_sep_entry_falls_back_to_title_and_override_slug() -> None:
    html = textwrap.dedent(
        """
        <html>
          <head>
            <title>Moral Luck (Stanford Encyclopedia of Philosophy)</title>
          </head>
          <body>
            <div id="pubinfo">First published Mon Jan 26, 2004</div>
          </body>
        </html>
        """
    )

    entry = parse_sep_entry(
        "https://plato.stanford.edu/entries/moral-luck/",
        html,
        slug="custom-luck",
    )

    assert entry.title == "Moral Luck"
    assert entry.slug == "custom-luck"
    assert entry.authors == []
    assert entry.first_published is None
    assert entry.source_type == "sep"


def test_convert_sep_html_to_markdown_trims_sep_noise_but_keeps_latex() -> None:
    article_html = textwrap.dedent(
        """
        <p>Intro with \\(S\\) and \\(\\phi\\).</p>
        <p>Here is an overview of what follows.</p>
        <ul>
          <li><a href="#one">1. One</a></li>
          <li><a href="#two">2. Two</a></li>
          <li><a href="#three">3. Three</a></li>
        </ul>
        <hr>
        <h2 id="one">1. One</h2>
        <p>Main body paragraph.</p>
        <h2>Academic Tools</h2>
        <blockquote><p><a href="/tools">How to cite this entry</a></p></blockquote>
        <h2>Other Internet Resources</h2>
        <ul><li><a href="/other">External project</a></li></ul>
        <h2>Related Entries</h2>
        <p><a href="/entries/action/">action</a> | <a href="/entries/agency/">agency</a></p>
        """
    )

    markdown = convert_sep_html_to_markdown(
        article_html,
        "https://plato.stanford.edu/entries/test-entry/",
    )

    assert "Intro with \\(S\\) and \\(\\phi\\)." in markdown
    assert "- [1. One]" not in markdown
    assert "## Academic Tools" not in markdown
    assert "## Other Internet Resources" not in markdown
    assert "## Related Entries" in markdown
    assert "- [action](https://plato.stanford.edu/entries/action/)" in markdown
    assert "- [agency](https://plato.stanford.edu/entries/agency/)" in markdown


def test_convert_sep_html_to_markdown_rewrites_same_entry_links_to_local_anchors() -> (
    None
):
    article_html = textwrap.dedent(
        """
        <p>See <a href="#target">Section 2</a> and
        <a href="https://plato.stanford.edu/entries/test-entry/#deep">deep dive</a>.</p>
        <p>Cross-entry links should stay remote:
        <a href="https://plato.stanford.edu/entries/other-entry/#elsewhere">other</a>.</p>
        <h2 id="target">2. Target Section</h2>
        <h3 id="deep">2.1 Deep Dive</h3>
        """
    )

    markdown = convert_sep_html_to_markdown(
        article_html,
        "https://plato.stanford.edu/entries/test-entry/",
    )

    assert "[Section 2](#2-target-section)" in markdown
    assert "[deep dive](#21-deep-dive)" in markdown
    assert (
        "[other](https://plato.stanford.edu/entries/other-entry/#elsewhere)" in markdown
    )


def test_markdown_heading_anchor_deduplicates_same_titles() -> None:
    article_html = textwrap.dedent(
        """
        <p><a href="#one">first</a> and <a href="#two">second</a></p>
        <h2 id="one">Notes</h2>
        <h2 id="two">Notes</h2>
        """
    )

    markdown = convert_sep_html_to_markdown(
        article_html,
        "https://plato.stanford.edu/entries/test-entry/",
    )

    assert "[first](#notes)" in markdown
    assert "[second](#notes-1)" in markdown


def test_convert_sep_html_to_markdown_preserves_nested_list_indentation() -> None:
    article_html = textwrap.dedent(
        """
        <ul>
          <li>Outer
            <ul>
              <li>Inner</li>
            </ul>
          </li>
        </ul>
        """
    )

    markdown = convert_sep_html_to_markdown(
        article_html,
        "https://plato.stanford.edu/entries/test-entry/",
    )

    assert "- Outer" in markdown
    assert "  - Inner" in markdown


def test_convert_sep_html_to_markdown_removes_nested_sep_toc_block() -> None:
    article_html = textwrap.dedent(
        """
        <p>Overview paragraph.</p>
        <ul>
          <li><a href="#one">1. One</a>
            <ul>
              <li><a href="#one-a">1.1 One A</a></li>
            </ul>
          </li>
          <li><a href="#two">2. Two</a></li>
          <li><a href="#three">3. Three</a></li>
        </ul>
        <hr>
        <h2 id="one">1. One</h2>
        <h3 id="one-a">1.1 One A</h3>
        <h2 id="two">2. Two</h2>
        <h2 id="three">3. Three</h2>
        """
    )

    markdown = convert_sep_html_to_markdown(
        article_html,
        "https://plato.stanford.edu/entries/test-entry/",
    )

    assert "[1. One](#1-one)" not in markdown
    assert "[1.1 One A](#11-one-a)" not in markdown
    assert sum(1 for line in markdown.splitlines() if line.startswith("## ")) == 3


def test_convert_sep_html_to_markdown_formats_blockquotes_without_empty_markers() -> (
    None
):
    article_html = textwrap.dedent(
        """
        <p>Lead in.</p>
        <blockquote>
          <p>
            If determinism is true, then our acts are the consequences of the
            laws of nature and events in the remote past.
          </p>
        </blockquote>
        <p>After quote.</p>
        """
    )

    markdown = convert_sep_html_to_markdown(
        article_html,
        "https://plato.stanford.edu/entries/test-entry/",
    )

    assert "\n>\n" not in markdown
    assert (
        "> If determinism is true, then our acts are the consequences of the laws "
        "of nature and events in the remote past."
    ) in markdown
