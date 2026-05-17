from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from wiki_cli import paths
from wiki_cli.notes import import_wittgenstein
from wiki_cli.wittgenstein import (
    convert_wittgenstein_html_to_markdown,
    extract_wittgenstein_main_html,
    normalize_wittgenstein_target,
    parse_wittgenstein_entry,
)

from .support import seed_index_and_log


def sample_wittgenstein_html() -> str:
    return textwrap.dedent(
        """
        <!DOCTYPE html>
        <html lang="de">
          <head>
            <title>Ms-175 &ndash; Wittgenstein&#39;s Writings</title>
          </head>
          <body>
            <nav><a href="/">Wittgenstein's Writings</a></nav>
            <main>
              <h1 id="ms-175">Ms-175</h1>
              <p class="lang-switcher"><span class="lang-active">German</span>
                (<a href="/epub/Ms-175.epub">epub</a>, <a href="/pdf/Ms-175.pdf">pdf</a>)
              </p>
              <details>
                <summary>244 published remarks, OC, VB</summary>
                <a href="#viz-Ms-175"><img class="viz" src="/viz/Ms-175.svg"></a>
              </details>
              <section>
                <h3 id="1r1"><a class="fragment-link" href="#1r1">section</a><a href="/w-oc/#ms-175-1r1">OC</a></h3>
                <span class="fac"><a href="#fac-Ms-175-1r">1r[1]</a></span>
                <div><p>First remark.</p></div>
              </section>
              <section>
                <h3 id="1r2"><a class="fragment-link" href="#1r2">section</a><a href="/w-oc/#ms-175-1r2">OC</a></h3>
                <span class="fac"><a href="#fac-Ms-175-1r">1r[2]</a></span>
                <div><p>Second <em>remark</em>.</p></div>
              </section>
              <section>
                <h3 id="1v1"><a class="fragment-link" href="#1v1">section</a><a href="/w-oc/#ms-175-1v1">OC</a></h3>
                <span class="fac"><a href="#fac-Ms-175-1v">1v[1]</a></span>
                <div><p>Third remark.</p></div>
              </section>
              <div id="fac-Ms-175-1r" class="lightbox">
                <img src="https://cdn.wittgensteinnachlass.com/2000px/webp/Ms-175/1r.webp">
              </div>
            </main>
          </body>
        </html>
        """
    )


def test_normalize_wittgenstein_target_accepts_ids_and_urls() -> None:
    assert normalize_wittgenstein_target("ms-175") == (
        "https://wittgensteinnachlass.com/ms-175/",
        "ms-175",
        "document",
    )
    assert normalize_wittgenstein_target(
        "https://www.wittgensteinnachlass.com/w-oc/#x"
    ) == (
        "https://wittgensteinnachlass.com/w-oc/",
        "w-oc",
        "collection",
    )


def test_parse_wittgenstein_entry_records_unit_and_range() -> None:
    entry = parse_wittgenstein_entry(
        "https://wittgensteinnachlass.com/ms-175/",
        sample_wittgenstein_html(),
        unit="auto",
        start="1r1",
        end="1r2",
    )

    assert entry.source_type == "wittgenstein"
    assert entry.slug == "ms-175-1r1-to-1r2"
    assert entry.title == "Ms-175"
    assert entry.authors == ["Ludwig Wittgenstein"]
    assert entry.canonical_id == "ms-175"
    assert entry.source_unit == "document"
    assert entry.reference_range == "1r1..1r2"
    assert entry.edition == "Wittgenstein's Writings"


def test_convert_wittgenstein_html_to_markdown_can_slice_remark_range() -> None:
    main_html = extract_wittgenstein_main_html(sample_wittgenstein_html())
    markdown = convert_wittgenstein_html_to_markdown(
        main_html,
        base_url="https://wittgensteinnachlass.com/ms-175/",
        start="1r2",
        end="1v1",
    )

    assert "# Ms-175" in markdown
    assert "First remark." not in markdown
    assert "Second remark." in markdown
    assert "Third remark." in markdown
    assert "2000px/webp" not in markdown


def test_import_wittgenstein_writes_expected_files(
    isolated_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths.ensure_workspace()
    seed_index_and_log(isolated_workspace)
    monkeypatch.setattr(
        "wiki_cli.notes.wittgenstein.fetch_url",
        lambda _url: sample_wittgenstein_html(),
    )

    entry = import_wittgenstein(
        "ms-175",
        slug=None,
        force=False,
        unit="auto",
        start="1r1",
        end="1r2",
    )

    raw_dir = paths.raw_root("wittgenstein") / entry.slug
    assert (raw_dir / "source.html").exists()
    assert (raw_dir / "source.md").exists()
    assert (raw_dir / "meta.json").exists()

    source_text = (raw_dir / "source.md").read_text(encoding="utf-8")
    assert "First remark." in source_text
    assert "Second remark." in source_text
    assert "Third remark." not in source_text

    note_text = (
        isolated_workspace / "wiki" / "sources" / "ms-175-1r1-to-1r2.md"
    ).read_text(encoding="utf-8")
    assert "source_type: wittgenstein" in note_text
    assert "- Wittgenstein page ID: ms-175" in note_text
    assert "- Source unit: document" in note_text
    assert "- Reference range: 1r1..1r2" in note_text
