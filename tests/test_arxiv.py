from __future__ import annotations

import textwrap
from email.message import Message
from pathlib import Path

import pytest

from wiki_cli.arxiv import (
    archive_suffix,
    build_reading_markdown,
    convert_tex_to_markdown,
    extract_reference_labels,
    expand_tex_file,
    filename_from_headers,
    normalize_arxiv_identifier,
    parse_arxiv_entry,
    tabular_to_markdown,
)
from wiki_cli.models import SourceEntry


EXTRACTED_ROOT = Path("extracted")
SMOKE_FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "arxiv_smoke"


def render_markdown(
    tex: str,
    *,
    custom_macros: dict[str, str] | None = None,
    reference_labels: dict[str, tuple[str, str]] | None = None,
) -> str:
    return convert_tex_to_markdown(
        textwrap.dedent(tex),
        EXTRACTED_ROOT,
        custom_macros=custom_macros or {},
        reference_labels=reference_labels or {},
    )


def extract_tabular_body(tex_table: str, spec: str) -> str:
    return (
        tex_table.split(rf"\begin{{tabular}}{{{spec}}}", 1)[1]
        .split(r"\end{tabular}", 1)[0]
        .strip()
    )


def load_arxiv_smoke_fixture(slug: str) -> str:
    return (SMOKE_FIXTURES_ROOT / slug / "main.tex").read_text(encoding="utf-8")


def write_arxiv_smoke_fixture(tmp_path: Path, slug: str) -> Path:
    entry_dir = tmp_path / slug
    extracted = entry_dir / "extracted"
    extracted.mkdir(parents=True)
    (extracted / "main.tex").write_text(load_arxiv_smoke_fixture(slug), encoding="utf-8")
    return entry_dir


def make_arxiv_entry(slug: str, title: str) -> SourceEntry:
    canonical_id = slug.replace("-", ".", 1)
    return SourceEntry(
        source_type="arxiv",
        slug=slug,
        title=title,
        url=f"https://arxiv.org/abs/{canonical_id}",
        authors=["Example, Ada"],
        first_published="2026/04/18",
        pubinfo="Submitted on 18 Apr 2026",
        fetched_at="2026-04-18T00:00:00+00:00",
        canonical_id=canonical_id,
        source_archive_name="source.tar.gz",
        primary_source_path="extracted/main.tex",
    )


@pytest.mark.parametrize(
    (
        "identifier",
        "tex",
        "custom_macros",
        "reference_labels",
        "expected_fragments",
        "unexpected_fragments",
    ),
    [
        pytest.param(
            "1706.03762",
            r"""
            \paragraph{Encoder:} Uses \dmodel.
            \begin{table}
            \caption{Results summary.}
            \label{tab:results}
            \begin{tabular}{lccccc}
            \toprule
            \multirow{2}{*}{\vspace{-2mm}Model} & \multicolumn{2}{c}{BLEU} & & \multicolumn{2}{c}{Training Cost (FLOPs)} \\
            & EN-DE & EN-FR & & EN-DE & EN-FR \\
            \hline
            Transformer (base model) & 27.3 & 38.1 & & \multicolumn{2}{c}{\boldmath$3.3\cdot10^{18}$}\\
            \end{tabular}
            \end{table}
            See Table \ref{tab:results}.
            """,
            {"dmodel": r"d_{\text{model}}"},
            {"tab:results": ("table", "Results summary. Extra detail.")},
            (
                "**Encoder:** Uses d_{model}.",
                "| Model | BLEU EN-DE | BLEU EN-FR | Training Cost (FLOPs) EN-DE | Training Cost (FLOPs) EN-FR |",
                'See Table "Results summary".',
            ),
            (
                "d_{ ext{model}}",
                r"\begin{table}",
            ),
            id="1706-03762-transformer-regressions",
        ),
        pytest.param(
            "2012.14913",
            r"""
            We compare \nl{a} and \nl{while}.
            \begin{table}
            \caption{Pattern examples.}
            \begin{tabular}{l|p{2.8cm}|p{10.cm}}
            Key & Pattern & Example \\
            \hline
            $k_1$ & Topic & Prefix \\
            \end{tabular}
            \end{table}
            """,
            {},
            {},
            (
                '"a"',
                '"while"',
                "| Key | Pattern | Example |",
                "| $k_1$ | Topic | Prefix |",
            ),
            (r"\begin{tabular}",),
            id="2012-14913-nl-and-p-column-table",
        ),
        pytest.param(
            "2203.02155",
            r"""
            \title{Training language models to follow instructions with human feedback}
            \author{OpenAI}
            \tableofcontents
            where \( \pi_{\phi}^{\mathrm{RL}}\) is the learned RL policy.
            \newpage
            """,
            {},
            {},
            (r"\mathrm{RL}",),
            (
                r"\title{",
                r"\author{",
                r"\tableofcontents",
                r"\newpage",
            ),
            id="2203-02155-metadata-and-inline-math",
        ),
        pytest.param(
            "2204.05862",
            r"""
            \begin{quote}
            Important quoted text.
            \end{quote}
            \begin{lstlisting}[frame=none]
            def greet():
                return "hi"
            \end{lstlisting}
            {\footnotesize
            \begin{tabularx}{\linewidth}{p{3cm} | p{10cm}}
            Prompt & Response \\
            \hline
            Q & A \\
            \end{tabularx}}
            See Figure \ref fig:overview.
            """,
            {},
            {"fig:overview": ("figure", "Model overview.")},
            (
                "> Important quoted text.",
                "```text",
                'return "hi"',
                "| Prompt | Response |",
                'See Figure "Model overview".',
            ),
            (
                r"\begin{quote}",
                r"\begin{lstlisting}",
                r"\begin{tabularx}",
            ),
            id="2204-05862-quote-listing-tabularx-and-ref",
        ),
    ],
)
def test_convert_tex_to_markdown_handles_known_arxiv_regressions(
    identifier: str,
    tex: str,
    custom_macros: dict[str, str],
    reference_labels: dict[str, tuple[str, str]],
    expected_fragments: tuple[str, ...],
    unexpected_fragments: tuple[str, ...],
) -> None:
    markdown = render_markdown(
        tex,
        custom_macros=custom_macros,
        reference_labels=reference_labels,
    )

    for fragment in expected_fragments:
        assert fragment in markdown, f"{identifier} is missing `{fragment}`"

    for fragment in unexpected_fragments:
        assert fragment not in markdown, f"{identifier} still contains `{fragment}`"


@pytest.mark.parametrize(
    ("slug", "title", "expected_fragments", "unexpected_fragments"),
    [
        pytest.param(
            "1706-03762",
            "Smoke Fixture 1706.03762",
            (
                "# Smoke Fixture 1706.03762",
                "## Abstract",
                "## Introduction",
                "**Encoder:** Uses d_{model}.",
                "| Model | BLEU EN-DE | BLEU EN-FR | Training Cost (FLOPs) EN-DE | Training Cost (FLOPs) EN-FR |",
                'See Table "Results summary".',
            ),
            (
                "d_{ ext{model}}",
                r"\begin{table}",
            ),
            id="1706-03762-reading-copy-smoke",
        ),
        pytest.param(
            "2012-14913",
            "Smoke Fixture 2012.14913",
            (
                "# Smoke Fixture 2012.14913",
                "## Abstract",
                "## Method",
                '"a"',
                '"while"',
                "| Key | Pattern | Example |",
            ),
            (r"\begin{tabular}",),
            id="2012-14913-reading-copy-smoke",
        ),
        pytest.param(
            "2203-02155",
            "Smoke Fixture 2203.02155",
            (
                "# Smoke Fixture 2203.02155",
                "## Abstract",
                "## Method",
                r"\mathrm{RL}",
            ),
            (
                r"\title{",
                r"\author{",
                r"\tableofcontents",
                r"\newpage",
            ),
            id="2203-02155-reading-copy-smoke",
        ),
        pytest.param(
            "2204-05862",
            "Smoke Fixture 2204.05862",
            (
                "# Smoke Fixture 2204.05862",
                "## Abstract",
                "## Overview",
                "> Important quoted text.",
                "```text",
                "| Prompt | Response |",
                'See Figure "Model overview".',
            ),
            (
                r"\begin{quote}",
                r"\begin{lstlisting}",
                r"\begin{tabularx}",
            ),
            id="2204-05862-reading-copy-smoke",
        ),
    ],
)
def test_build_reading_markdown_smoke_samples(
    tmp_path: Path,
    slug: str,
    title: str,
    expected_fragments: tuple[str, ...],
    unexpected_fragments: tuple[str, ...],
) -> None:
    entry_dir = write_arxiv_smoke_fixture(tmp_path, slug)
    entry = make_arxiv_entry(slug, title)

    markdown = build_reading_markdown(entry, entry_dir)

    for fragment in expected_fragments:
        assert fragment in markdown, f"{slug} reading copy is missing `{fragment}`"

    for fragment in unexpected_fragments:
        assert (
            fragment not in markdown
        ), f"{slug} reading copy still contains `{fragment}`"


def test_parse_arxiv_entry_reads_meta_and_submission_history() -> None:
    html = textwrap.dedent(
        """
        <html>
          <head>
            <meta name="citation_title" content="Attention Is All You Need">
            <meta name="citation_author" content="Vaswani, Ashish">
            <meta name="citation_author" content="Shazeer, Noam">
            <meta name="citation_date" content="2017/06/12">
            <meta name="citation_arxiv_id" content="1706.03762">
            <meta name="citation_abstract" content="Transformer paper abstract.">
          </head>
          <body>
            <div class="submission-history">
              Submitted on 12 Jun 2017; revised 2 Aug 2023
            </div>
          </body>
        </html>
        """
    )

    entry = parse_arxiv_entry("1706.03762", html)

    assert entry.source_type == "arxiv"
    assert entry.slug == "1706-03762"
    assert entry.title == "Attention Is All You Need"
    assert entry.authors == ["Vaswani, Ashish", "Shazeer, Noam"]
    assert entry.first_published == "2017/06/12"
    assert entry.abstract == "Transformer paper abstract."
    assert entry.canonical_id == "1706.03762"
    assert entry.pubinfo == "Submitted on 12 Jun 2017; revised 2 Aug 2023"


def test_arxiv_identifier_helpers_handle_urls_and_headers() -> None:
    assert normalize_arxiv_identifier("1706.03762") == "1706.03762"
    assert (
        normalize_arxiv_identifier("https://arxiv.org/src/1706.03762") == "1706.03762"
    )
    assert (
        normalize_arxiv_identifier("https://arxiv.org/pdf/1706.03762.pdf")
        == "1706.03762"
    )

    headers = Message()
    headers["Content-Disposition"] = 'attachment; filename="arXiv-1706.03762v7.tar.gz"'
    assert filename_from_headers(headers) == "arXiv-1706.03762v7.tar.gz"
    assert archive_suffix(filename_from_headers(headers)) == ".tar.gz"


def test_expand_tex_file_inlines_inputs(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "main.tex").write_text(
        textwrap.dedent(
            """
            \\documentclass{article}
            \\begin{document}
            Before.
            \\input{part}
            After.
            \\end{document}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (extracted / "part.tex").write_text("Middle.\n", encoding="utf-8")

    expanded = expand_tex_file(extracted / "main.tex", extracted, set())

    assert "Before." in expanded
    assert "Middle." in expanded
    assert "After." in expanded


def test_convert_tex_to_markdown_makes_reading_copy_more_readable() -> None:
    tex = textwrap.dedent(
        r"""
        \begin{abstract}
        Short \textbf{abstract}.
        \end{abstract}
        \section{Intro}
        \label{sec:intro}
        See \citep{vaswani2017}. \footnote{Helpful note with $d_k$ inside.}
        \paragraph{Encoder:} Uses \dmodel.
        \begin{itemize}
        \item First point
        \item Second point
        \end{itemize}
        Refer back to \ref{sec:intro}.
        \begin{equation}
        a = b
        \end{equation}
        \begin{figure}
        \includegraphics{Figures/test-figure}
        \caption{A useful figure. See Section~\ref{sec:intro}.}
        \label{fig:test}
        \end{figure}
        \begin{table}
        \caption{Results summary.}
        \label{tab:test}
        \begin{tabular}{lc}
        Name & Score \\
        Base & 27.3 \\
        Big & 28.4 \\
        \end{tabular}
        \end{table}
        See Figure \ref{fig:test} and Table \ref{tab:test}.
        """
    )

    markdown = render_markdown(
        tex,
        custom_macros={"dmodel": "d_{model}"},
        reference_labels={
            "sec:intro": ("heading", "Intro"),
            "fig:test": ("figure", "A useful figure. More detail."),
            "tab:test": ("table", "Results summary. Extra detail."),
        },
    )

    assert "## Abstract" in markdown
    assert "## Intro" in markdown
    assert "**abstract**" in markdown
    assert "- First point" in markdown
    assert "[cite: vaswani2017]" in markdown
    assert "Footnote: Helpful note with $d_k$ inside." in markdown
    assert "**Encoder:** Uses d_{model}." in markdown
    assert "[Intro](#intro)" in markdown
    assert 'Figure "A useful figure"' in markdown
    assert 'Table "Results summary"' in markdown
    assert "```tex" in markdown
    assert "> Caption: A useful figure. See Section [Intro](#intro)." in markdown
    assert "extracted/Figures/test-figure.png" in markdown
    assert "> Table." in markdown
    assert "| Name | Score |" in markdown
    assert r"\begin{table}" not in markdown


def test_convert_tex_to_markdown_preserves_backslashes_in_macro_expansion() -> None:
    markdown = render_markdown(
        r"""
        \newcommand{\dmodel}{d_{\text{model}}}
        \paragraph{Encoder:} Uses \dmodel.
        """,
        custom_macros={"dmodel": r"d_{\text{model}}"},
    )

    assert "**Encoder:** Uses d_{model}." in markdown
    assert "d_{ ext{model}}" not in markdown


def test_convert_tex_to_markdown_resolves_equation_refs() -> None:
    tex = textwrap.dedent(
        r"""
        \begin{align}
        \text{FF}(\xx) = f(\xx \cdot K^{\top}) \cdot V
        \label{eq:ffn}
        \end{align}
        Compare \ref{eq:ffn}.
        """
    )

    reference_labels = extract_reference_labels(tex, {})
    markdown = render_markdown(tex, reference_labels=reference_labels)

    assert 'Compare "FF(\\xx) = f(\\xx · K^{\\top}) · V".' in markdown
    assert "[ref: eq:ffn]" not in markdown


def test_tabular_to_markdown_merges_split_headers_and_multicolumns() -> None:
    tex_table = textwrap.dedent(
        r"""
        \begin{tabular}{lccccc}
        \toprule
        \multirow{2}{*}{\vspace{-2mm}Model} & \multicolumn{2}{c}{BLEU} & & \multicolumn{2}{c}{Training Cost (FLOPs)} \\
        & EN-DE & EN-FR & & EN-DE & EN-FR \\
        \hline
        Transformer (base model) & 27.3 & 38.1 & & \multicolumn{2}{c}{\boldmath$3.3\cdot10^{18}$}\\
        \end{tabular}
        """
    )

    markdown = tabular_to_markdown(extract_tabular_body(tex_table, "lccccc"))

    assert (
        "| Model | BLEU EN-DE | BLEU EN-FR | Training Cost (FLOPs) EN-DE | Training Cost (FLOPs) EN-FR |"
        in markdown
    )
    assert "| Transformer (base model) | 27.3 | 38.1 | $3.3·10^{18}$ |  |" in markdown
    assert "| --- | --- | --- | --- | --- |" in markdown


def test_convert_tex_to_markdown_handles_tabular_with_nested_column_specs() -> None:
    markdown = render_markdown(
        r"""
        \begin{table}
        \caption{Pattern examples.}
        \begin{tabular}{l|p{2.8cm}|p{10.cm}}
        Key & Pattern & Example \\
        \hline
        $k_1$ & Topic & Prefix \\
        \end{tabular}
        \end{table}
        """
    )

    assert "| Key | Pattern | Example |" in markdown
    assert r"\begin{tabular}" not in markdown


def test_extract_reference_labels_handles_multiple_captions_in_one_table_env() -> None:
    tex = textwrap.dedent(
        r"""
        \begin{table}
        \caption{First caption.}
        \label{tab:first}
        \begin{tabular}{lc}
        A & B \\
        \end{tabular}
        \caption{Second caption.}
        \label{tab:second}
        \begin{tabular}{lc}
        C & D \\
        \end{tabular}
        \end{table}
        """
    )

    labels = extract_reference_labels(tex, {})

    assert labels["tab:first"] == ("table", "First caption.")
    assert labels["tab:second"] == ("table", "Second caption.")


def test_convert_tex_to_markdown_prefers_main_figure_caption_over_empty_subfigure_captions() -> (
    None
):
    tex = textwrap.dedent(
        r"""
        \begin{figure}
        \begin{subfigure}[b]{1.0\textwidth}
        \includegraphics{Figures/one}
        \caption{}
        \end{subfigure}
        \begin{subfigure}[b]{1.0\textwidth}
        \includegraphics{Figures/two}
        \caption{}
        \end{subfigure}
        \caption{Screenshots of our labeling interface.}
        \label{fig:labelserver}
        \end{figure}
        See Figure \ref{fig:labelserver}.
        """
    )

    labels = extract_reference_labels(tex, {})
    markdown = render_markdown(tex, reference_labels=labels)

    assert "> Caption: Screenshots of our labeling interface." in markdown
    assert 'Figure "Screenshots of our labeling interface"' in markdown


def test_extract_reference_labels_can_infer_target_from_following_context() -> None:
    tex = textwrap.dedent(
        r"""
        \label{apdx:details}
        \begin{figure}
        \caption{Metadata by model size.}
        \label{fig:metadata}
        \end{figure}
        See Appendix \ref{apdx:details}.
        """
    )

    labels = extract_reference_labels(tex, {})

    assert labels["apdx:details"] == ("figure", "Metadata by model size.")


def test_convert_tex_to_markdown_cleans_common_prose_tex_artifacts() -> None:
    markdown = render_markdown(
        r"""
        In human evaluations, outputs from the 175B {GPT-3} model are preferred less often.
        On closed-domain tasks (e.g.\ summarization), the model helps.
        We compare "styles" like \nl{follow the instruction}.
        """
    )

    assert "{GPT-3}" not in markdown
    assert "175B GPT-3" in markdown
    assert "e.g. summarization" in markdown
    assert '"follow the instruction"' in markdown


def test_convert_tex_to_markdown_keeps_braces_for_inline_math_commands() -> None:
    markdown = render_markdown(
        r"""
        where \( \pi_{\phi}^{\mathrm{RL}}\) is the learned RL policy.
        \newpage
        """
    )

    assert r"\mathrm{RL}" in markdown
    assert r"\newpage" not in markdown


def test_convert_tex_to_markdown_removes_document_metadata_commands() -> None:
    markdown = render_markdown(
        r"""
        \title{A Paper}
        \author{Alice \thanks{Lead author.}}
        \date{Today}
        \tableofcontents
        \setcounter{footnote}{0}
        \section{Intro}
        Body.
        """
    )

    assert r"\title{" not in markdown
    assert r"\author{" not in markdown
    assert r"\tableofcontents" not in markdown
    assert r"\setcounter" not in markdown
    assert "## Intro" in markdown
    assert "Body." in markdown


def test_convert_tex_to_markdown_normalizes_ref_without_braces() -> None:
    markdown = render_markdown(
        r"See Figure \ref fig:test.",
        reference_labels={"fig:test": ("figure", "Main result figure.")},
    )

    assert 'See Figure "Main result figure".' in markdown


def test_convert_tex_to_markdown_converts_lstlisting_to_fenced_block() -> None:
    markdown = render_markdown(
        r"""
        Before.
        \begin{lstlisting}[frame=none]
        def greet():
            return "hi"
        \end{lstlisting}
        After.
        """
    )

    assert "```text" in markdown
    assert 'return "hi"' in markdown
    assert r"\begin{lstlisting}" not in markdown


def test_convert_tex_to_markdown_converts_quote_environment() -> None:
    markdown = render_markdown(
        r"""
        \begin{quote}
        Important quoted text.
        \end{quote}
        """
    )

    assert "> Important quoted text." in markdown
    assert r"\begin{quote}" not in markdown


def test_convert_tex_to_markdown_converts_standalone_tabularx() -> None:
    markdown = render_markdown(
        r"""
        {\footnotesize
        \begin{tabularx}{\linewidth}{p{3cm} | p{10cm}}
        Prompt & Response \\
        \hline
        Q & A \\
        \end{tabularx}}
        """
    )

    assert "| Prompt | Response |" in markdown
    assert "| Q | A |" in markdown
    assert r"\begin{tabularx}" not in markdown


def test_tabular_to_markdown_does_not_merge_simple_two_row_table() -> None:
    tex_table = textwrap.dedent(
        r"""
        \begin{tabular}{ll}
        Prompt & Response \\
        Q & A \\
        \end{tabular}
        """
    )

    markdown = tabular_to_markdown(extract_tabular_body(tex_table, "ll"))

    assert "| Prompt | Response |" in markdown
    assert "| Q | A |" in markdown


def test_convert_tex_to_markdown_uses_readable_fallback_for_unresolved_appendix_ref() -> (
    None
):
    markdown = render_markdown("See Appendix \\ref{apdx:details}.")

    assert "See Appendix the appendix." in markdown


def test_tabular_to_markdown_keeps_escaped_ampersands_inside_cells() -> None:
    tex_table = textwrap.dedent(
        r"""
        \begin{tabular}{c|c|c}
        \hline
        {\bf Parser} & {\bf Training} & {\bf WSJ 23 F1} \\
        \hline
        Vinyals \& Kaiser et al. (2014) & semi-supervised & 92.1 \\
        \end{tabular}
        """
    )

    markdown = tabular_to_markdown(extract_tabular_body(tex_table, "c|c|c"))

    assert "| Parser | Training | WSJ 23 F1 |" in markdown
    assert "| Vinyals & Kaiser et al. (2014) | semi-supervised | 92.1 |" in markdown


def test_build_reading_markdown_uses_primary_tex_file(tmp_path: Path) -> None:
    entry_dir = tmp_path / "1706-03762"
    extracted = entry_dir / "extracted"
    extracted.mkdir(parents=True)
    (extracted / "main.tex").write_text(
        textwrap.dedent(
            r"""
            \documentclass{article}
            \begin{document}
            \begin{abstract}
            Generated abstract.
            \end{abstract}
            \newcommand{\dmodel}{d_{model}}
            \section{Intro}\label{sec:intro}
            A readable paragraph with \dmodel and \footnote{A note.}
            \paragraph{Decoder:} Reads \ref{sec:intro}.
            \end{document}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    entry = SourceEntry(
        source_type="arxiv",
        slug="1706-03762",
        title="Attention Is All You Need",
        url="https://arxiv.org/abs/1706.03762",
        authors=["Vaswani, Ashish"],
        first_published="2017/06/12",
        pubinfo="Submitted on 12 Jun 2017",
        fetched_at="2026-04-18T00:00:00+00:00",
        canonical_id="1706.03762",
        source_archive_name="source.tar.gz",
        primary_source_path="extracted/main.tex",
    )

    markdown = build_reading_markdown(entry, entry_dir)

    assert "# Attention Is All You Need" in markdown
    assert "## Generated Reading Copy" in markdown
    assert "## Abstract" in markdown
    assert "## Intro" in markdown
    assert "A readable paragraph with d_{model}" in markdown
    assert "Footnote: A note." in markdown
    assert "**Decoder:** Reads [Intro](#intro)." in markdown
    assert "Source manifest: [manifest.md](manifest.md)" in markdown
