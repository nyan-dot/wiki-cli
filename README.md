# wiki-cli

CLI tools for maintaining a local LLM-assisted research wiki.

This repository contains the Python package, tests, and command wiring. It is
meant to be installed and then used from a separate content repository that
holds `wiki/`, `raw/`, and `AGENTS.md`.

## What Lives Here

- `src/wiki_cli/`: package code for SEP import, arXiv source import, Markdown
  conversion, indexing, linting, and activity logging
- `tests/`: lightweight regression tests for the core workflows
- `main.py`: thin compatibility entry point for `python main.py ...` during
  local development

## Development

Run the test suite:

```bash
uv run pytest
```

Run lint checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

Apply auto-fixable lint changes:

```bash
uv run ruff check . --fix
uv run ruff format .
```

Install local pre-commit hooks:

```bash
uv run pre-commit install
```

Run the pre-commit suite across the whole repository:

```bash
uv run pre-commit run --all-files
```

Run a quick compile check:

```bash
python -m compileall main.py src tests
```

## Install

For local editable use:

```bash
uv tool install --editable .
```

If you prefer a project environment instead of a tool install:

```bash
uv pip install -e .
```

## Use From A Content Repo

Once installed, run the CLI inside a separate content repository:

```bash
wiki init
wiki import-sep https://plato.stanford.edu/entries/freewill/
wiki import-lesswrong https://www.lesswrong.com/posts/AcKRB8wDpdaN6v6ru/interpreting-gpt-the-logit-lens
wiki import-anthropic https://transformer-circuits.pub/2025/attribution-graphs/biology.html
wiki import-arxiv-src https://arxiv.org/src/1706.03762
wiki build-index
wiki lint-wiki
```

The companion content repository is expected to hold:

- `raw/`
- `wiki/`
- `AGENTS.md`

The CLI intentionally stays small and file-based so the content repo remains
plain Markdown plus source artifacts.

Current source ingest support includes:

- SEP entries via `wiki import-sep`
- LessWrong posts via `wiki import-lesswrong`
- Transformer Circuits / Anthropic interpretability articles via `wiki import-anthropic`
- arXiv source bundles via `wiki import-arxiv-src`

Markdown conversion is split into a small shared HTML-to-Markdown parser plus
source-specific cleanup:

- SEP and LessWrong both use a common parser for headings, lists, blockquotes,
  code blocks, images, links, and basic tables
- SEP then rewrites same-entry links and trims SEP-specific boilerplate such as
  the table of contents and tail resource sections
- When an SEP `notes.html` page exists, SEP imports also save it locally and
  rewrite note references into Markdown footnotes in `source.md`
- LessWrong then normalizes inline footnote references, preserves multiline
  footnotes and footnote tables, and keeps common author-side formatting such as
  bracketed `Edit` blocks
- Transformer Circuits / Anthropic interpretability articles reuse the shared
  parser and strip Distill-style `<d-contents>` table-of-contents scaffolding
  before converting the article body to Markdown

LessWrong imports store immutable post artifacts under `raw/lesswrong/<slug>/`:

- `meta.json` for normalized metadata including the LessWrong post ID
- `source.html` for the fetched post HTML
- `source.md` as generated reading Markdown intended for human reading and LLM use

Anthropic interpretability imports store immutable article artifacts under
`raw/anthropic/<slug>/`:

- `meta.json` for normalized metadata including the Transformer Circuits article ID
- `source.html` for the fetched article HTML
- `source.md` as generated reading Markdown intended for human reading and LLM use

`import-arxiv-src` stores immutable paper artifacts under `raw/arxiv/<slug>/`:

- `meta.json` for normalized metadata
- `abs.html` for the arXiv abstract page
- `source.*` for the downloaded source archive
- `extracted/` for the unpacked TeX and auxiliary files
- `source.md` as a generated reading Markdown file derived from the primary TeX source
- `manifest.md` as a file inventory that links into the extracted tree

SEP imports store immutable entry artifacts under `raw/sep/<slug>/`:

- `meta.json` for normalized metadata
- `source.html` for the fetched entry HTML
- `source.md` as generated reading Markdown
- `notes.html` when the SEP entry exposes a notes page used for local footnotes

## License

`wiki-cli` is licensed under the GNU General Public License, version 3 or any
later version (`GPL-3.0-or-later`). See [LICENSE](LICENSE).
