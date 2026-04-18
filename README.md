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
uv run --extra dev pytest
```

Run lint checks:

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

Apply auto-fixable lint changes:

```bash
uv run --extra dev ruff check . --fix
uv run --extra dev ruff format .
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
- arXiv source bundles via `wiki import-arxiv-src`

`import-arxiv-src` stores immutable paper artifacts under `raw/arxiv/<slug>/`:

- `meta.json` for normalized metadata
- `abs.html` for the arXiv abstract page
- `source.*` for the downloaded source archive
- `extracted/` for the unpacked TeX and auxiliary files
- `source.md` as a generated reading Markdown file derived from the primary TeX source
- `manifest.md` as a file inventory that links into the extracted tree

## License

`wiki-cli` is licensed under the GNU General Public License, version 3 or any
later version (`GPL-3.0-or-later`). See [LICENSE](LICENSE).
