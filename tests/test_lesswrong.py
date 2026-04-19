from __future__ import annotations

import textwrap
from pathlib import Path

from wiki_cli import paths
from wiki_cli.lesswrong import (
    convert_lesswrong_html_to_markdown,
    extract_lesswrong_post_html,
    normalize_lesswrong_url,
    parse_lesswrong_entry,
    postprocess_lesswrong_markdown,
)
from wiki_cli.notes import import_lesswrong

from .support import seed_index_and_log


def sample_lesswrong_html() -> str:
    return textwrap.dedent(
        """
        <html>
          <head>
            <title>interpreting GPT: the logit lens — LessWrong</title>
            <meta name="description" content="A quick interpretability note.">
            <meta name="citation_title" content="interpreting GPT: the logit lens">
            <meta name="citation_author" content="nostalgebraist">
            <link rel="canonical" href="https://www.lesswrong.com/posts/AcKRB8wDpdaN6v6ru/interpreting-gpt-the-logit-lens">
          </head>
          <body>
            <div id="postBody">
              <div class="PostsPage-title">
                <time datetime="2020-08-31T02:47:08.426Z">31st Aug 2020</time>
              </div>
              <div class="PostsPage-postContent">
                <div id="postContent">
                  <div>
                    <p>Intro paragraph with a <a href="/w/gpt">tag link</a>.</p>
                    <h2>Overview</h2>
                    <p>Key claim.</p>
                    <ul>
                      <li>Parent point
                        <ul>
                          <li>Child point</li>
                        </ul>
                      </li>
                    </ul>
                    <p>Claim with footnote <a href="about:blank#fn-abc-1">[1]</a>.</p>
                    <pre><code>print("hello")</code></pre>
                    <p><img src="/image.png" alt="Diagram"></p>
                    <hr>
                    <ol type="1">
                      <li>Footnote body <a href="about:blank#fnref-abc-1">↩︎</a><br></li>
                    </ol>
                  </div>
                </div>
              </div>
            </div>
          </body>
        </html>
        """
    )


def sample_rich_lesswrong_html() -> str:
    return textwrap.dedent(
        """
        <html>
          <head>
            <title>Simulators — LessWrong</title>
            <meta name="description" content="A rich LessWrong post.">
            <meta name="citation_title" content="Simulators">
            <meta name="citation_author" content="janus">
            <link rel="canonical" href="https://www.lesswrong.com/posts/vJFdjigzmcXMhNTsx/simulators">
          </head>
          <body>
            <div id="postBody">
              <div class="PostsPage-title">
                <time datetime="2022-09-08T00:00:00.000Z">8th Sep 2022</time>
              </div>
              <div class="PostsPage-postContent">
                <div id="postContent">
                  <div>
                    <p><i>This work was carried out while at</i><span><span><a href="https://www.conjecture.dev/"><i> Conjecture</i></a></span></span><i>.</i></p>
                    <figure class="image">
                      <img src="https://example.com/image.png" alt="Image">
                    </figure>
                    <p>Caption text.</p>
                    <blockquote>
                      <p>Quoted line one.</p>
                      <p>Quoted line two.</p>
                    </blockquote>
                    <p>Sentence with footnote<span class="footnote-reference" role="doc-noteref" id="fnrefone"><sup><span><a href="#fnone">[1]</a></span></sup></span>.</p>
                    <figure class="table">
                      <table>
                        <tbody>
                          <tr><td>Thing</td><td>Value</td></tr>
                          <tr><td>GPT</td><td>X</td></tr>
                        </tbody>
                      </table>
                    </figure>
                    <ol>
                      <li id="fnone"><p>Footnote body <a href="#fnrefone">[^]</a></p></li>
                    </ol>
                  </div>
                </div>
              </div>
            </div>
          </body>
        </html>
        """
    )


def test_normalize_lesswrong_url_canonicalizes_post_urls() -> None:
    canonical_url, post_id, slug = normalize_lesswrong_url(
        "https://lesswrong.com/posts/AcKRB8wDpdaN6v6ru/interpreting-gpt-the-logit-lens?ref=foo#comments"
    )

    assert (
        canonical_url
        == "https://www.lesswrong.com/posts/AcKRB8wDpdaN6v6ru/interpreting-gpt-the-logit-lens"
    )
    assert post_id == "AcKRB8wDpdaN6v6ru"
    assert slug == "interpreting-gpt-the-logit-lens"


def test_parse_lesswrong_entry_reads_meta_and_time() -> None:
    entry = parse_lesswrong_entry(
        "https://www.lesswrong.com/posts/AcKRB8wDpdaN6v6ru/interpreting-gpt-the-logit-lens",
        sample_lesswrong_html(),
    )

    assert entry.source_type == "lesswrong"
    assert entry.slug == "interpreting-gpt-the-logit-lens"
    assert entry.title == "interpreting GPT: the logit lens"
    assert entry.authors == ["nostalgebraist"]
    assert entry.first_published == "2020-08-31"
    assert entry.pubinfo == "31st Aug 2020"
    assert entry.abstract == "A quick interpretability note."
    assert entry.canonical_id == "AcKRB8wDpdaN6v6ru"


def test_extract_and_convert_lesswrong_body_to_markdown() -> None:
    article_html = extract_lesswrong_post_html(sample_lesswrong_html())
    markdown = convert_lesswrong_html_to_markdown(
        article_html,
        "https://www.lesswrong.com/posts/AcKRB8wDpdaN6v6ru/interpreting-gpt-the-logit-lens",
    )

    assert "[tag link](https://www.lesswrong.com/w/gpt)" in markdown
    assert "## Overview" in markdown
    assert "- Parent point" in markdown
    assert "  - Child point" in markdown
    assert "Claim with footnote [^1]." in markdown
    assert "[^1]: Footnote body" in markdown
    assert "```" in markdown
    assert 'print("hello")' in markdown
    assert "![Diagram](https://www.lesswrong.com/image.png)" in markdown


def test_import_lesswrong_writes_expected_files(
    isolated_workspace: Path,
    monkeypatch,
) -> None:
    paths.ensure_workspace()
    seed_index_and_log(isolated_workspace)
    monkeypatch.setattr(
        "wiki_cli.notes.lesswrong.fetch_url", lambda _url: sample_lesswrong_html()
    )

    entry = import_lesswrong(
        "https://www.lesswrong.com/posts/AcKRB8wDpdaN6v6ru/interpreting-gpt-the-logit-lens",
        slug=None,
        force=False,
    )

    raw_dir = paths.raw_root("lesswrong") / entry.slug
    assert (raw_dir / "source.html").exists()
    assert (raw_dir / "source.md").exists()
    assert (raw_dir / "meta.json").exists()

    note_text = (
        isolated_workspace / "wiki" / "sources" / "interpreting-gpt-the-logit-lens.md"
    ).read_text(encoding="utf-8")
    assert "source_type: lesswrong" in note_text
    assert "- LessWrong post ID: AcKRB8wDpdaN6v6ru" in note_text
    assert "Raw markdown:" in note_text


def test_postprocess_lesswrong_markdown_preserves_nested_lists_and_edit_blocks() -> (
    None
):
    markdown = postprocess_lesswrong_markdown(
        textwrap.dedent(
            """
            [Edit: note]

            [Edit 5/17/21: details:

            - one
            - two

            ]

            - Parent sentence.

              - Should flatten.
              - Another one.

            - Parent intro:

              - Should stay nested.

            Link to [Universal Transformers](https://arxiv.org/abs/1807.03819)which matters.
            """
        ).strip()
        + "\n"
    )

    assert "[Edit: note]" in markdown
    assert "\n]\n" in markdown
    assert "  - Should flatten." in markdown
    assert "  - Should stay nested." in markdown
    assert (
        "[Universal Transformers](https://arxiv.org/abs/1807.03819) which matters."
        in markdown
    )


def test_postprocess_lesswrong_markdown_preserves_title_groups() -> None:
    markdown = postprocess_lesswrong_markdown(
        textwrap.dedent(
            """
            - Input and output

              - As input...
            - As output...
            - That is...

            - Vocab and embedding spaces

              - The vocab...
            - There is a matrix...
            """
        ).strip()
        + "\n"
    )

    assert "- Input and output" in markdown
    assert "  - As input..." in markdown
    assert "- As output..." in markdown
    assert "- That is..." in markdown
    assert "- There is a matrix..." in markdown


def test_convert_lesswrong_html_to_markdown_handles_blockquotes_tables_and_footnotes() -> (
    None
):
    article_html = extract_lesswrong_post_html(sample_rich_lesswrong_html())
    markdown = convert_lesswrong_html_to_markdown(
        article_html,
        "https://www.lesswrong.com/posts/vJFdjigzmcXMhNTsx/simulators",
    )

    assert (
        "This work was carried out while at [Conjecture](https://www.conjecture.dev/)."
        in markdown
    )
    assert "\n\n![Image](https://example.com/image.png)\n\nCaption text." in markdown
    assert "> Quoted line one." in markdown
    assert "> Quoted line two." in markdown
    assert "Sentence with footnote[^1]." in markdown
    assert "| Thing | Value |" in markdown
    assert "| GPT | X |" in markdown
    assert "[^1]: Footnote body" in markdown


def test_postprocess_lesswrong_markdown_preserves_multiline_linked_footnotes() -> None:
    markdown = postprocess_lesswrong_markdown(
        textwrap.dedent(
            """
            Main text[^1] and table[^2].

            - [^](https://www.lesswrong.com/posts/example#fnrefone)

            First paragraph.

            Second paragraph.
            - [^](https://www.lesswrong.com/posts/example#fnreftwo)

            | Col A | Col B |
            | --- | --- |
            | A | B |
            """
        ).strip()
        + "\n"
    )

    assert "Main text[^1] and table[^2]." in markdown
    assert "[^1]:" in markdown
    assert "    First paragraph." in markdown
    assert "\n\n    Second paragraph.\n" in markdown
    assert "[^2]:" in markdown
    assert "    | Col A | Col B |" in markdown
    assert "    | --- | --- |" in markdown
    assert "    | A | B |" in markdown
