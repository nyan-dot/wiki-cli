from __future__ import annotations

import gzip
import html
import re
import tarfile
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path

from .models import SourceEntry
from .utils import markdown_heading_anchor, normalize_inline, slugify

ARXIV_USER_AGENT = "wiki-cli/0.1 (+https://example.invalid/local-knowledge-base)"
TEX_INCLUDE_RE = re.compile(r"\\(input|include|subfile)\{([^}]+)\}")
TEX_SECTION_RE = re.compile(
    r"\\(?P<name>section|subsection|subsubsection)\*?(?:\[[^\]]*\])?\{(?P<title>[^{}]+)\}"
)
TEX_PARAGRAPH_RE = re.compile(
    r"\\(?P<name>paragraph|subparagraph)\*?(?:\[[^\]]*\])?\{(?P<title>[^{}]+)\}"
)
TEX_SIMPLE_ARG_TEMPLATE = r"\\{command}\{{([^{{}}]+)\}}"
TEX_DOUBLE_ARG_TEMPLATE = r"\\{command}\{{([^{{}}]+)\}}\{{([^{{}}]+)\}}"
TEX_CITE_RE = re.compile(r"\\cite\w*\*?(?:\[[^\]]*\])?(?:\[[^\]]*\])?\{([^{}]+)\}")
TEX_REF_RE = re.compile(r"\\(?:eqref|ref|autoref)\{([^{}]+)\}")
TEX_LABEL_RE = re.compile(r"\\label\{([^{}]+)\}")
TEX_BIBITEM_RE = re.compile(r"\\bibitem(?:\[[^\]]*\])?\{([^{}]+)\}")
TEX_SECTION_WITH_LABEL_RE = re.compile(
    r"\\(?P<name>section|subsection|subsubsection)\*?(?:\[[^\]]*\])?\{(?P<title>[^{}]+)\}\s*(?:\\label\{(?P<label>[^{}]+)\})?"
)
TEX_ENV_RE = re.compile(
    r"\\begin\{(?P<env>figure\*?|table\*?)\}(?P<body>.*?)\\end\{(?P=env)\}",
    re.DOTALL,
)
TEX_TABULAR_RE = re.compile(
    r"\\begin\{tabular\}(?:\[[^\]]*\])?\{(?P<spec>(?:[^{}]|\{[^{}]*\})*)\}(?P<body>.*?)\\end\{tabular\}",
    re.DOTALL,
)
TEX_TABULARX_RE = re.compile(
    r"\\begin\{tabularx\}(?:\[[^\]]*\])?\{(?:[^{}]|\{[^{}]*\})*\}\{(?P<spec>(?:[^{}]|\{[^{}]*\})*)\}(?P<body>.*?)\\end\{tabularx\}",
    re.DOTALL,
)
TEX_MATH_ENV_NAMES = [
    "equation",
    "equation*",
    "align",
    "align*",
    "alignat",
    "alignat*",
    "gather",
    "gather*",
    "multline",
    "multline*",
    "eqnarray",
    "eqnarray*",
]
TEX_INLINE_COMMANDS = {
    "textbf": ("**", "**"),
    "textit": ("*", "*"),
    "emph": ("*", "*"),
    "texttt": ("`", "`"),
    "textsc": ("", ""),
    "text": ("", ""),
}
TEX_REPLACE_WITH_SECOND_ARG = ["textcolor"]
TEX_DROP_COMMANDS = [
    r"\\maketitle\b",
    r"\\bibliographystyle\{[^{}]*\}",
    r"\\footnotemark(?:\[[^\]]*\])?",
    r"\\newpage\b",
    r"\\centering\b",
    r"\\large\b",
    r"\\small\b",
    r"\\normalsize\b",
    r"\\color\{[^{}]*\}",
    r"\\vspace\*?\{[^{}]*\}",
    r"\\hspace\*?\{[^{}]*\}",
    r"\\noindent\b",
    r"\\newblock\b",
]


class ArxivMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, list[str]] = {}
        self._inside_submission_history = False
        self.submission_history_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "meta":
            name = attr_map.get("name") or attr_map.get("property")
            content = attr_map.get("content")
            if name and content:
                self.meta.setdefault(name, []).append(html.unescape(content))
        elif tag == "div" and attr_map.get("class", "") == "submission-history":
            self._inside_submission_history = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._inside_submission_history:
            self._inside_submission_history = False

    def handle_data(self, data: str) -> None:
        if self._inside_submission_history:
            self.submission_history_parts.append(data)


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": ARXIV_USER_AGENT})
    with urllib.request.urlopen(request) as response:
        return response.read().decode("utf-8", errors="ignore")


def fetch_binary(url: str) -> tuple[bytes, Message]:
    request = urllib.request.Request(url, headers={"User-Agent": ARXIV_USER_AGENT})
    with urllib.request.urlopen(request) as response:
        return response.read(), response.headers


def normalize_arxiv_identifier(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Missing arXiv identifier or URL.")

    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.strip("/")
        if not path:
            raise ValueError(f"Could not determine an arXiv identifier from `{value}`.")
        parts = path.split("/")
        if parts[0] in {"abs", "src", "pdf"} and len(parts) >= 2:
            candidate = parts[1]
        else:
            candidate = parts[-1]
        if candidate.endswith(".pdf"):
            candidate = candidate[:-4]
        return candidate

    return cleaned.removesuffix(".pdf")


def build_abs_url(identifier: str) -> str:
    return f"https://arxiv.org/abs/{identifier}"


def build_src_url(identifier: str) -> str:
    return f"https://arxiv.org/src/{identifier}"


def parse_arxiv_entry(
    identifier: str,
    page_html: str,
    *,
    slug: str | None = None,
) -> SourceEntry:
    parser = ArxivMetaParser()
    parser.feed(page_html)

    title = first_meta_value(parser.meta, "citation_title")
    if not title:
        raise ValueError("Could not determine the arXiv entry title.")

    authors = parser.meta.get("citation_author", [])
    first_published = first_meta_value(parser.meta, "citation_date")
    canonical_id = first_meta_value(parser.meta, "citation_arxiv_id") or identifier
    abstract = first_meta_value(parser.meta, "citation_abstract")
    pubinfo = normalize_inline("".join(parser.submission_history_parts)) or None
    derived_slug = slug or slugify(canonical_id)

    return SourceEntry(
        source_type="arxiv",
        slug=derived_slug,
        title=title,
        url=build_abs_url(identifier),
        authors=authors,
        first_published=first_published,
        pubinfo=pubinfo,
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        abstract=abstract,
        canonical_id=canonical_id,
    )


def first_meta_value(meta: dict[str, list[str]], key: str) -> str | None:
    values = meta.get(key) or []
    return values[0] if values else None


def archive_suffix(filename: str | None) -> str:
    if not filename:
        return ".bin"

    lowered = filename.casefold()
    for suffix in [".tar.gz", ".tgz", ".tar", ".zip", ".gz"]:
        if lowered.endswith(suffix):
            return suffix
    return Path(filename).suffix or ".bin"


def filename_from_headers(headers: Message) -> str | None:
    content_disposition = headers.get("Content-Disposition")
    if not content_disposition:
        return None

    match = re.search(r'filename="([^"]+)"', content_disposition)
    if match:
        return match.group(1)
    match = re.search(r"filename=([^;]+)", content_disposition)
    if match:
        return match.group(1).strip()
    return None


def extract_archive(
    archive_path: Path,
    extracted_dir: Path,
) -> list[Path]:
    extracted_dir.mkdir(parents=True, exist_ok=True)
    safe_members: list[str] = []

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                validate_member_path(member.filename, extracted_dir)
                archive.extract(member, extracted_dir)
                if not member.is_dir():
                    safe_members.append(member.filename)
        return sorted(Path(member) for member in safe_members)

    try:
        with tarfile.open(archive_path, "r:*") as archive:
            members = archive.getmembers()
            for member in members:
                validate_member_path(member.name, extracted_dir)
                if member.isdir():
                    continue
                if member.issym() or member.islnk():
                    continue
                safe_members.append(member.name)
            archive.extractall(
                extracted_dir,
                members=[
                    member
                    for member in members
                    if not member.issym() and not member.islnk()
                ],
            )
        return sorted(Path(member) for member in safe_members)
    except tarfile.ReadError:
        pass

    if archive_path.suffix.casefold() == ".gz":
        payload = gzip.decompress(archive_path.read_bytes())
        output_name = archive_path.stem or "source"
        validate_member_path(output_name, extracted_dir)
        output_path = extracted_dir / output_name
        output_path.write_bytes(payload)
        return [Path(output_name)]

    raise ValueError(f"Unsupported arXiv source archive format: {archive_path.name}")


def validate_member_path(member_name: str, extracted_dir: Path) -> None:
    member_path = Path(member_name)
    if member_path.is_absolute():
        raise ValueError(f"Archive member uses an absolute path: {member_name}")

    destination = (extracted_dir / member_path).resolve()
    if not destination.is_relative_to(extracted_dir.resolve()):
        raise ValueError(
            f"Archive member escapes the extraction directory: {member_name}"
        )


def choose_primary_source(entry_dir: Path, extracted_files: list[Path]) -> str | None:
    candidates = [path for path in extracted_files if path.suffix.casefold() == ".tex"]
    if not candidates:
        return None

    scored: list[tuple[int, str]] = []
    for path in candidates:
        full_path = entry_dir / "extracted" / path
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        score = 0
        lowered = content.casefold()
        if "\\documentclass" in lowered:
            score += 5
        if "\\begin{document}" in lowered:
            score += 3
        if "\\title" in lowered:
            score += 1
        if path.name.casefold() in {"main.tex", "paper.tex", "ms.tex"}:
            score += 2
        if len(path.parts) == 1:
            score += 1
        scored.append((score, path.as_posix()))

    if not scored:
        return None

    best_path = max(scored, key=lambda item: (item[0], -len(item[1]), item[1]))[1]
    return f"extracted/{best_path}"


def build_reading_markdown(entry: SourceEntry, entry_dir: Path) -> str:
    lines = [f"# {entry.title}", ""]

    lines.extend(
        [
            "## Source Snapshot",
            f"- arXiv ID: {entry.canonical_id or 'Unknown'}",
            "- Abstract page HTML: [abs.html](abs.html)",
            f"- Source archive: [{entry.source_archive_name}]({entry.source_archive_name})"
            if entry.source_archive_name
            else "- Source archive: Unknown",
            f"- Primary source candidate: [{entry.primary_source_path}]({entry.primary_source_path})"
            if entry.primary_source_path
            else "- Primary source candidate: Could not determine one automatically.",
            "- Source manifest: [manifest.md](manifest.md)",
            "",
        ]
    )

    if not entry.primary_source_path:
        lines.extend(
            [
                "## Abstract",
                entry.abstract or "No abstract metadata captured.",
                "",
                "## Notes",
                "A generated reading copy could not be built automatically because no primary `.tex` file was detected.",
                "Use `manifest.md` and the files under `extracted/` directly.",
                "",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    primary_path = entry_dir / entry.primary_source_path
    extracted_root = entry_dir / "extracted"
    expanded_source = expand_tex_file(primary_path, extracted_root, set())
    custom_macros = extract_custom_macros(expanded_source)
    body = extract_document_body(expanded_source)
    reference_labels = extract_reference_labels(body, custom_macros)
    rendered_body = convert_tex_to_markdown(
        body,
        extracted_root,
        custom_macros=custom_macros,
        reference_labels=reference_labels,
    )

    lines.extend(
        [
            "## Generated Reading Copy",
            "This Markdown was generated from the primary TeX source for reading and LLM ingestion.",
            "",
            rendered_body.strip(),
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def expand_tex_file(path: Path, extracted_root: Path, active_paths: set[Path]) -> str:
    resolved_path = path.resolve()
    if resolved_path in active_paths:
        return f"\n[Recursive include skipped: {path.name}]\n"

    active_paths.add(resolved_path)
    try:
        text = strip_tex_comments(path.read_text(encoding="utf-8", errors="ignore"))

        def replace_include(match: re.Match[str]) -> str:
            include_target = match.group(2).strip()
            include_path = resolve_tex_path(include_target, path.parent, extracted_root)
            if include_path is None or not include_path.exists():
                return f"\n[Missing include: {include_target}]\n"
            return (
                "\n"
                + expand_tex_file(include_path, extracted_root, active_paths)
                + "\n"
            )

        return TEX_INCLUDE_RE.sub(replace_include, text)
    finally:
        active_paths.remove(resolved_path)


def strip_tex_comments(text: str) -> str:
    stripped_lines: list[str] = []
    for line in text.splitlines():
        current: list[str] = []
        escaped = False
        for character in line:
            if character == "%" and not escaped:
                break
            current.append(character)
            escaped = character == "\\" and not escaped
            if character != "\\":
                escaped = False
        stripped_lines.append("".join(current))
    return "\n".join(stripped_lines)


def resolve_tex_path(
    target: str, current_dir: Path, extracted_root: Path
) -> Path | None:
    target_path = Path(target)
    candidates = [target_path]
    if not target_path.suffix:
        candidates.append(Path(f"{target}.tex"))

    for base_dir in [current_dir, extracted_root]:
        for candidate in candidates:
            resolved = (base_dir / candidate).resolve()
            if resolved.exists():
                return resolved
    return None


def extract_document_body(text: str) -> str:
    start_match = re.search(r"\\begin\{document\}", text)
    end_match = re.search(r"\\end\{document\}", text)
    if start_match and end_match and end_match.start() > start_match.end():
        return text[start_match.end() : end_match.start()]
    return text


def convert_tex_to_markdown(
    text: str,
    extracted_root: Path,
    *,
    custom_macros: dict[str, str] | None = None,
    reference_labels: dict[str, tuple[str, str]] | None = None,
) -> str:
    custom_macros = custom_macros or {}
    reference_labels = reference_labels or {}
    rendered = preprocess_tex_for_conversion(text)
    rendered = expand_custom_macros(rendered, custom_macros)
    rendered = replace_abstract_environment(rendered)
    rendered = replace_section_commands(rendered)
    rendered = replace_paragraph_commands(rendered)
    rendered = replace_figure_environments(rendered, extracted_root)
    rendered = replace_table_environments(rendered)
    rendered = replace_standalone_tabular_environments(rendered)
    rendered = replace_lstlisting_environments(rendered)
    rendered = replace_quote_environments(rendered)
    rendered = replace_math_environments(rendered)
    rendered = replace_list_environments(rendered)
    rendered = replace_bibliography(rendered)
    rendered = replace_inline_commands(
        rendered,
        reference_labels=reference_labels,
    )
    rendered = remove_newcommand_definitions(rendered)
    rendered = remove_tex_commands(rendered)
    rendered = cleanup_markdown(rendered)
    return rendered


def preprocess_tex_for_conversion(text: str) -> str:
    rendered = text.replace("\r\n", "\n")
    rendered = normalize_reference_syntax(rendered)
    rendered = remove_document_metadata_commands(rendered)
    return rendered


def normalize_reference_syntax(text: str) -> str:
    return re.sub(
        r"\\(?P<command>eqref|ref|autoref)\s+(?P<label>[A-Za-z0-9:_/-]+(?:\.[A-Za-z0-9:_/-]+)*)(?P<suffix>[.,;:])?",
        lambda match: (
            f"\\{match.group('command')}{{{match.group('label')}}}"
            f"{match.group('suffix') or ''}"
        ),
        text,
    )


def remove_document_metadata_commands(text: str) -> str:
    rendered = text
    for command in ["title", "author", "date"]:
        rendered = replace_command_with_balanced_arguments(
            rendered,
            command,
            lambda _args: "",
        )

    rendered = replace_command_with_multiple_balanced_arguments(
        rendered,
        "setcounter",
        2,
        lambda _args: "",
    )
    rendered = re.sub(r"\\tableofcontents\b", "", rendered)
    return rendered


def replace_abstract_environment(text: str) -> str:
    text = re.sub(r"\\begin\{abstract\}", "\n\n## Abstract\n\n", text)
    text = re.sub(r"\\end\{abstract\}", "\n", text)
    return text


def replace_section_commands(text: str) -> str:
    level_map = {
        "section": "##",
        "subsection": "###",
        "subsubsection": "####",
    }

    def replace(match: re.Match[str]) -> str:
        heading = cleanup_inline_tex(match.group("title"))
        return f"\n\n{level_map[match.group('name')]} {heading}\n\n"

    return TEX_SECTION_RE.sub(replace, text)


def replace_paragraph_commands(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        heading = cleanup_inline_tex(match.group("title")).rstrip(":.")
        return f"\n\n**{heading}:** "

    return TEX_PARAGRAPH_RE.sub(replace, text)


def replace_figure_environments(text: str, extracted_root: Path) -> str:
    pattern = re.compile(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", re.DOTALL)

    def replace(match: re.Match[str]) -> str:
        block = match.group(1)
        caption = nearest_preceding_caption(
            extract_command_arguments_with_positions(
                block,
                "caption",
                allow_optional=True,
            ),
            len(block) + 1,
        )
        assets = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}", block)
        lines = ["> Figure."]
        if caption:
            lines.append(f"> Caption: {cleanup_inline_tex(caption)}")
        for asset in assets:
            asset_path = resolve_graphic_asset(asset, extracted_root)
            lines.append(f"> Asset: [{asset_path}]({asset_path})")
        return "\n\n" + "\n".join(lines) + "\n\n"

    return pattern.sub(replace, text)


def replace_table_environments(text: str) -> str:
    pattern = re.compile(r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", re.DOTALL)

    def replace(match: re.Match[str]) -> str:
        block = match.group(1)
        caption = extract_command_argument(block, "caption", allow_optional=True)
        tabular_match = find_first_tabular_match(block)
        lines = ["> Table."]
        if caption:
            lines.append(f"> Caption: {cleanup_inline_tex(caption)}")

        if tabular_match:
            table_markdown = tabular_to_markdown(tabular_match.group("body"))
            if table_markdown:
                return "\n\n" + "\n".join(lines) + "\n\n" + table_markdown + "\n\n"

        return "\n\n" + "\n".join(lines) + "\n\n```tex\n" + block.strip() + "\n```\n\n"

    return pattern.sub(replace, text)


def find_first_tabular_match(text: str) -> re.Match[str] | None:
    tabular_match = TEX_TABULAR_RE.search(text)
    tabularx_match = TEX_TABULARX_RE.search(text)
    matches = [match for match in [tabular_match, tabularx_match] if match is not None]
    if not matches:
        return None
    return min(matches, key=lambda match: match.start())


def replace_standalone_tabular_environments(text: str) -> str:
    rendered = text
    rendered = TEX_TABULARX_RE.sub(replace_tabular_like_match, rendered)
    rendered = TEX_TABULAR_RE.sub(replace_tabular_like_match, rendered)
    return rendered


def replace_tabular_like_match(match: re.Match[str]) -> str:
    table_markdown = tabular_to_markdown(match.group("body"))
    if table_markdown:
        return "\n\n" + table_markdown + "\n\n"
    return "\n\n```tex\n" + match.group(0).strip() + "\n```\n\n"


def replace_lstlisting_environments(text: str) -> str:
    pattern = re.compile(
        r"\\begin\{lstlisting\}(?:\[[^\]]*\])?(?P<body>.*?)\\end\{lstlisting\}",
        re.DOTALL,
    )
    return pattern.sub(
        lambda match: f"\n\n```text\n{match.group('body').strip()}\n```\n\n",
        text,
    )


def replace_quote_environments(text: str) -> str:
    pattern = re.compile(r"\\begin\{quote\}(?P<body>.*?)\\end\{quote\}", re.DOTALL)

    def replace(match: re.Match[str]) -> str:
        body = cleanup_markdown(match.group("body")).strip()
        if not body:
            return "\n\n"
        quoted_lines = [f"> {line}" if line else ">" for line in body.splitlines()]
        return "\n\n" + "\n".join(quoted_lines) + "\n\n"

    return pattern.sub(replace, text)


def resolve_graphic_asset(target: str, extracted_root: Path) -> str:
    target_path = Path(target)
    candidates = [target_path]
    if not target_path.suffix:
        for suffix in [".png", ".jpg", ".jpeg", ".pdf", ".svg"]:
            candidates.append(Path(f"{target}{suffix}"))

    for candidate in candidates:
        resolved = (extracted_root / candidate).resolve()
        if resolved.exists():
            return (Path("extracted") / resolved.relative_to(extracted_root)).as_posix()

    fallback = target if target_path.suffix else f"{target}.png"
    return (Path("extracted") / fallback).as_posix()


def replace_math_environments(text: str) -> str:
    rendered = text
    for env_name in TEX_MATH_ENV_NAMES:
        pattern = re.compile(
            rf"\\begin\{{{re.escape(env_name)}\}}(.*?)\\end\{{{re.escape(env_name)}\}}",
            re.DOTALL,
        )
        rendered = pattern.sub(
            lambda match: f"\n\n```tex\n{match.group(1).strip()}\n```\n\n",
            rendered,
        )
    return rendered


def replace_list_environments(text: str) -> str:
    rendered = re.sub(r"\\begin\{(?:itemize|enumerate)\}", "\n", text)
    rendered = re.sub(r"\\end\{(?:itemize|enumerate)\}", "\n", rendered)
    rendered = re.sub(r"\\item\b", "\n- ", rendered)
    return rendered


def replace_bibliography(text: str) -> str:
    rendered = re.sub(
        r"\\begin\{thebibliography\}\{[^{}]*\}", "\n\n## References\n\n", text
    )
    rendered = re.sub(r"\\end\{thebibliography\}", "\n", rendered)
    rendered = TEX_BIBITEM_RE.sub(lambda match: f"\n- [{match.group(1)}] ", rendered)
    return rendered


def replace_inline_commands(
    text: str,
    *,
    reference_labels: dict[str, tuple[str, str]],
) -> str:
    rendered = text

    for command, wrappers in TEX_INLINE_COMMANDS.items():
        rendered = replace_simple_argument_command(
            rendered,
            command,
            lambda content, left=wrappers[0], right=wrappers[1]: (
                f"{left}{cleanup_inline_tex(content)}{right}"
            ),
        )

    for command in TEX_REPLACE_WITH_SECOND_ARG:
        rendered = replace_double_argument_command(
            rendered,
            command,
            lambda _first, second: cleanup_inline_tex(second),
        )

    rendered = replace_double_argument_command(
        rendered,
        "href",
        lambda url, label: f"[{cleanup_inline_tex(label)}]({cleanup_inline_tex(url)})",
    )
    rendered = replace_simple_argument_command(
        rendered,
        "url",
        lambda content: (
            f"[{cleanup_inline_tex(content)}]({cleanup_inline_tex(content)})"
        ),
    )
    rendered = replace_simple_argument_command(
        rendered,
        "nl",
        lambda content: f'"{cleanup_inline_tex(content)}"',
    )
    rendered = TEX_CITE_RE.sub(
        lambda match: f"[cite: {cleanup_inline_tex(match.group(1))}]",
        rendered,
    )
    rendered = TEX_REF_RE.sub(
        lambda match: render_reference(match.group(1), reference_labels),
        rendered,
    )
    rendered = TEX_LABEL_RE.sub("", rendered)
    rendered = replace_command_with_balanced_arguments(
        rendered,
        "footnote",
        lambda args: f" (Footnote: {cleanup_inline_tex(args[0])})",
    )
    return rendered


def replace_simple_argument_command(
    text: str,
    command: str,
    formatter: callable,
) -> str:
    pattern = re.compile(TEX_SIMPLE_ARG_TEMPLATE.format(command=re.escape(command)))
    rendered = text
    while True:
        updated = pattern.sub(lambda match: formatter(match.group(1)), rendered)
        if updated == rendered:
            return updated
        rendered = updated


def replace_double_argument_command(
    text: str,
    command: str,
    formatter: callable,
) -> str:
    pattern = re.compile(TEX_DOUBLE_ARG_TEMPLATE.format(command=re.escape(command)))
    rendered = text
    while True:
        updated = pattern.sub(
            lambda match: formatter(match.group(1), match.group(2)),
            rendered,
        )
        if updated == rendered:
            return updated
        rendered = updated


def cleanup_inline_tex(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.replace("``", '"')
    cleaned = cleaned.replace("''", '"')
    cleaned = cleaned.replace(r"\@", "")
    cleaned = re.sub(r"\\(?=\s)", "", cleaned)
    cleaned = cleaned.replace("\t", " ")
    cleaned = cleaned.replace("~", " ")
    cleaned = cleaned.replace(r"\&", "&")
    cleaned = cleaned.replace(r"\%", "%")
    cleaned = cleaned.replace(r"\_", "_")
    cleaned = cleaned.replace(r"\#", "#")
    cleaned = cleaned.replace(r"\$", "$")
    cleaned = cleaned.replace(r"\cdot", "·")
    cleaned = re.sub(r"\\newline\b", " ", cleaned)
    cleaned = re.sub(r"\\(?:quad|qquad)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def remove_tex_commands(text: str) -> str:
    rendered = text
    for pattern in TEX_DROP_COMMANDS:
        rendered = re.sub(pattern, "", rendered)

    rendered = re.sub(
        r"\\begin\{(?:center|minipage)\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?", "\n", rendered
    )
    rendered = re.sub(r"\\end\{(?:center|minipage)\}", "\n", rendered)
    rendered = re.sub(r"\\\\", "\n", rendered)
    rendered = rendered.replace("~", " ")
    rendered = rendered.replace(r"\&", "&")
    rendered = rendered.replace(r"\%", "%")
    rendered = rendered.replace(r"\_", "_")
    rendered = rendered.replace(r"\#", "#")
    rendered = rendered.replace(r"\$", "$")
    rendered = re.sub(r"\\pagebreak\b", "", rendered)
    return rendered


def cleanup_markdown(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned: list[str] = []
    previous_blank = False
    in_fence = False

    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("```"):
            in_fence = not in_fence
            cleaned.append(stripped_line)
            previous_blank = False
            continue

        normalized_line = re.sub(r"[ \t]+", " ", line).strip()
        if not in_fence:
            normalized_line = normalize_prose_line(normalized_line)

        if not normalized_line:
            if not previous_blank:
                cleaned.append("")
            previous_blank = True
            continue

        if normalized_line == "-":
            continue
        if (
            normalized_line
            == "Provided proper attribution is provided, Google hereby grants permission to reproduce the tables and figures in this paper solely for use in journalistic or scholarly works."
        ):
            continue

        cleaned.append(normalized_line)
        previous_blank = False

    return "\n".join(cleaned).strip() + "\n"


def normalize_prose_line(text: str) -> str:
    normalized = text
    normalized = normalized.replace("``", '"')
    normalized = normalized.replace("''", '"')
    normalized = normalized.replace(r"\@", "")
    normalized = re.sub(r"\\(?=\s)", "", normalized)
    normalized = re.sub(
        r"(?<![A-Za-z0-9_^\\])\{([A-Za-z0-9][A-Za-z0-9 .,+:/'\-]{0,80})\}",
        r"\1",
        normalized,
    )
    return normalized.strip()


def extract_custom_macros(text: str) -> dict[str, str]:
    macros: dict[str, str] = {}
    index = 0

    while index < len(text):
        if text.startswith(r"\newcommand", index):
            parsed = parse_newcommand_definition(text, index)
            if parsed is not None:
                name, value, index = parsed
                if name and value is not None:
                    macros[name] = value
                continue
        index += 1

    return macros


def remove_newcommand_definitions(text: str) -> str:
    pieces: list[str] = []
    index = 0

    while index < len(text):
        match_index = text.find(r"\newcommand", index)
        if match_index == -1:
            pieces.append(text[index:])
            break

        pieces.append(text[index:match_index])
        parsed = parse_newcommand_definition(text, match_index)
        if parsed is None:
            pieces.append(r"\newcommand")
            index = match_index + len(r"\newcommand")
            continue

        _, _, next_index = parsed
        index = next_index

    return "".join(pieces)


def parse_newcommand_definition(
    text: str, start_index: int
) -> tuple[str | None, str | None, int] | None:
    index = start_index + len(r"\newcommand")
    index = skip_whitespace(text, index)

    if index < len(text) and text[index] == "*":
        index += 1
        index = skip_whitespace(text, index)

    if index >= len(text):
        return None

    macro_name: str | None = None
    if text[index] == "{":
        name_token, index = extract_balanced_content(text, index, "{", "}")
        macro_name = name_token.lstrip("\\")
    elif text[index] == "\\":
        macro_name, index = parse_control_sequence_name(text, index)
    else:
        return None

    index = skip_whitespace(text, index)
    arg_count = 0
    if index < len(text) and text[index] == "[":
        count_token, index = extract_balanced_content(text, index, "[", "]")
        try:
            arg_count = int(count_token.strip())
        except ValueError:
            arg_count = 0
        index = skip_whitespace(text, index)

    if arg_count != 0:
        body = None
        if index < len(text) and text[index] == "{":
            _, index = extract_balanced_content(text, index, "{", "}")
        return macro_name, body, index

    if index >= len(text) or text[index] != "{":
        return None

    body, index = extract_balanced_content(text, index, "{", "}")
    return macro_name, body, index


def expand_custom_macros(text: str, custom_macros: dict[str, str]) -> str:
    if not custom_macros:
        return text

    rendered = text
    for _ in range(5):
        updated = rendered
        for macro_name, macro_body in sorted(
            custom_macros.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            updated = re.sub(
                rf"\\{re.escape(macro_name)}\b",
                lambda _match, body=macro_body: body,
                updated,
            )
        if updated == rendered:
            break
        rendered = updated
    return rendered


def extract_reference_labels(
    text: str,
    custom_macros: dict[str, str],
) -> dict[str, tuple[str, str]]:
    expanded = expand_custom_macros(text, custom_macros)
    labels: dict[str, tuple[str, str]] = {}

    for match in TEX_SECTION_WITH_LABEL_RE.finditer(expanded):
        label = match.group("label")
        if not label:
            continue
        title = cleanup_inline_tex(match.group("title"))
        labels[label] = ("heading", title)

    for match in TEX_ENV_RE.finditer(expanded):
        env_name = match.group("env")
        body = match.group("body")
        kind = "table" if env_name.startswith("table") else "figure"
        captions = extract_command_arguments_with_positions(
            body,
            "caption",
            allow_optional=True,
        )
        env_labels = extract_command_arguments_with_positions(body, "label")

        for label, label_position in env_labels:
            caption = nearest_preceding_caption(captions, label_position)
            if not caption:
                continue
            labels[label] = (kind, cleanup_inline_tex(caption))

    for env_name in TEX_MATH_ENV_NAMES:
        pattern = re.compile(
            rf"\\begin\{{{re.escape(env_name)}\}}(?P<body>.*?)\\end\{{{re.escape(env_name)}\}}",
            re.DOTALL,
        )
        for match in pattern.finditer(expanded):
            body = match.group("body")
            label = extract_command_argument(body, "label")
            if not label:
                continue
            labels[label] = ("equation", summarize_equation_body(body))

    for match in TEX_LABEL_RE.finditer(expanded):
        label = match.group(1)
        if label in labels:
            continue
        inferred = infer_reference_target_from_following_context(
            expanded[match.end() :]
        )
        if inferred is not None:
            labels[label] = inferred

    return labels


def render_reference(
    label: str,
    reference_labels: dict[str, tuple[str, str]],
) -> str:
    cleaned_label = cleanup_inline_tex(label)
    target = reference_labels.get(cleaned_label)
    if target is None:
        return render_unresolved_reference(cleaned_label)

    kind, title = target
    if kind == "heading":
        return f"[{title}](#{markdown_heading_anchor(title)})"
    if kind == "table":
        summary = summarize_reference_title(title)
        return f'"{summary}"' if summary else "the table"
    if kind == "figure":
        summary = summarize_reference_title(title)
        return f'"{summary}"' if summary else "the figure"
    if kind == "equation":
        summary = summarize_reference_title(title)
        return f'"{summary}"' if summary else "the equation"
    return f"[ref: {title}]"


def render_unresolved_reference(label: str) -> str:
    if label.startswith("fig:"):
        return "the figure"
    if label.startswith("tab:"):
        return "the table"
    if label.startswith("sec:"):
        return "the section"
    if label.startswith("apdx:"):
        return "the appendix"
    if label.startswith("eq:"):
        return "the equation"
    return f"[ref: {label}]"


def summarize_reference_title(title: str) -> str:
    cleaned = cleanup_inline_tex(title).strip().rstrip(".")
    if not cleaned:
        return ""

    first_sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0].rstrip(".")
    if len(first_sentence) <= 80:
        return first_sentence
    return first_sentence[:77].rstrip() + "..."


def summarize_equation_body(body: str) -> str:
    cleaned = re.sub(r"\\label\{[^{}]+\}", "", body)
    cleaned = replace_simple_argument_command(
        cleaned,
        "text",
        lambda content: cleanup_inline_tex(content),
    )
    cleaned = cleanup_inline_tex(cleaned)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0]


def extract_command_argument(
    text: str,
    command: str,
    *,
    allow_optional: bool = False,
) -> str | None:
    token = f"\\{command}"
    index = text.find(token)
    while index != -1:
        command_end = index + len(token)
        if command_end < len(text) and text[command_end].isalpha():
            index = text.find(token, command_end)
            continue
        cursor = skip_whitespace(text, command_end)
        if allow_optional and cursor < len(text) and text[cursor] == "[":
            _, cursor = extract_balanced_content(text, cursor, "[", "]")
            cursor = skip_whitespace(text, cursor)
        if cursor < len(text) and text[cursor] == "{":
            content, _ = extract_balanced_content(text, cursor, "{", "}")
            return content
        index = text.find(token, command_end)
    return None


def extract_command_arguments_with_positions(
    text: str,
    command: str,
    *,
    allow_optional: bool = False,
) -> list[tuple[str, int]]:
    token = f"\\{command}"
    index = text.find(token)
    arguments: list[tuple[str, int]] = []

    while index != -1:
        command_end = index + len(token)
        if command_end < len(text) and text[command_end].isalpha():
            index = text.find(token, command_end)
            continue
        cursor = skip_whitespace(text, command_end)
        if allow_optional and cursor < len(text) and text[cursor] == "[":
            _, cursor = extract_balanced_content(text, cursor, "[", "]")
            cursor = skip_whitespace(text, cursor)
        if cursor < len(text) and text[cursor] == "{":
            content, _ = extract_balanced_content(text, cursor, "{", "}")
            arguments.append((content, index))
        index = text.find(token, command_end)

    return arguments


def nearest_preceding_caption(
    captions: list[tuple[str, int]],
    label_position: int,
) -> str | None:
    chosen_caption: str | None = None

    for caption, caption_position in captions:
        if caption_position > label_position:
            break
        if cleanup_inline_tex(caption):
            chosen_caption = caption

    if chosen_caption is not None:
        return chosen_caption

    for caption, _ in captions:
        if cleanup_inline_tex(caption):
            return caption

    return None


def infer_reference_target_from_following_context(
    trailing_text: str,
) -> tuple[str, str] | None:
    next_heading = TEX_SECTION_RE.search(trailing_text)
    next_env = TEX_ENV_RE.search(trailing_text)

    heading_position = next_heading.start() if next_heading is not None else None
    env_position = next_env.start() if next_env is not None else None

    if heading_position is not None and (
        env_position is None or heading_position < env_position
    ):
        return ("heading", cleanup_inline_tex(next_heading.group("title")))

    if next_env is not None:
        kind = "table" if next_env.group("env").startswith("table") else "figure"
        captions = extract_command_arguments_with_positions(
            next_env.group("body"),
            "caption",
            allow_optional=True,
        )
        caption = nearest_preceding_caption(captions, len(next_env.group("body")) + 1)
        if caption:
            return (kind, cleanup_inline_tex(caption))

    return None


def replace_command_with_balanced_arguments(
    text: str,
    command: str,
    formatter: callable,
) -> str:
    token = f"\\{command}"
    pieces: list[str] = []
    index = 0

    while index < len(text):
        match_index = text.find(token, index)
        if match_index == -1:
            pieces.append(text[index:])
            break

        command_end = match_index + len(token)
        if command_end < len(text) and text[command_end].isalpha():
            pieces.append(text[index : match_index + 1])
            index = match_index + 1
            continue

        pieces.append(text[index:match_index])
        cursor = skip_whitespace(text, command_end)
        if cursor >= len(text) or text[cursor] != "{":
            pieces.append(token)
            index = command_end
            continue

        content, next_index = extract_balanced_content(text, cursor, "{", "}")
        pieces.append(formatter([content]))
        index = next_index

    return "".join(pieces)


def replace_command_with_multiple_balanced_arguments(
    text: str,
    command: str,
    argument_count: int,
    formatter: callable,
) -> str:
    token = f"\\{command}"
    pieces: list[str] = []
    index = 0

    while index < len(text):
        match_index = text.find(token, index)
        if match_index == -1:
            pieces.append(text[index:])
            break

        command_end = match_index + len(token)
        if command_end < len(text) and text[command_end].isalpha():
            pieces.append(text[index : match_index + 1])
            index = match_index + 1
            continue

        pieces.append(text[index:match_index])
        cursor = command_end
        arguments: list[str] = []
        success = True

        for _ in range(argument_count):
            cursor = skip_whitespace(text, cursor)
            if cursor >= len(text) or text[cursor] != "{":
                success = False
                break
            argument, cursor = extract_balanced_content(text, cursor, "{", "}")
            arguments.append(argument)

        if not success:
            pieces.append(token)
            index = command_end
            continue

        pieces.append(formatter(arguments))
        index = cursor

    return "".join(pieces)


def tabular_to_markdown(tabular_body: str) -> str:
    cleaned = tabular_body
    cleaned = re.sub(r"\\(?:toprule|midrule|bottomrule|hline)\b", "", cleaned)
    cleaned = re.sub(r"\\cmidrule(?:\([^)]*\))?\{[^{}]*\}", "", cleaned)
    cleaned = re.sub(r"\\specialrule\{[^{}]*\}\{[^{}]*\}\{[^{}]*\}", "", cleaned)
    cleaned = re.sub(r"\\rule\{[^{}]*\}\{[^{}]*\}", "", cleaned)
    cleaned = cleaned.replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    row_chunks = [chunk.strip() for chunk in cleaned.split(r"\\") if chunk.strip()]

    rows: list[list[str]] = []
    for chunk in row_chunks:
        cells: list[str] = []
        for raw_cell in split_tabular_row(chunk):
            cells.extend(expand_table_cell(raw_cell))
        while cells and not cells[-1]:
            cells.pop()
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    max_columns = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (max_columns - len(row)) for row in rows]
    normalized_rows = merge_header_rows(normalized_rows)
    normalized_rows = drop_empty_columns(normalized_rows)
    max_columns = len(normalized_rows[0])

    header = normalized_rows[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * max_columns) + " |",
    ]
    for row in normalized_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def split_tabular_row(row_chunk: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []

    for index, character in enumerate(row_chunk):
        if character == "&" and (index == 0 or row_chunk[index - 1] != "\\"):
            cells.append("".join(current))
            current = []
            continue
        current.append(character)

    cells.append("".join(current))
    return cells


def expand_table_cell(cell: str) -> list[str]:
    cleaned = cell.strip()
    multicolumn = parse_balanced_command_arguments(cleaned, "multicolumn", 3)
    if multicolumn is not None:
        span_text, _, content = multicolumn
        try:
            span = max(int(span_text.strip()), 1)
        except ValueError:
            span = 1
        return [cleanup_table_cell(content)] + [""] * (span - 1)

    multirow = parse_balanced_command_arguments(cleaned, "multirow", 3)
    if multirow is not None:
        return [cleanup_table_cell(multirow[2])]

    return [cleanup_table_cell(cleaned)]


def parse_balanced_command_arguments(
    text: str,
    command: str,
    argument_count: int,
) -> list[str] | None:
    stripped = text.strip()
    token = f"\\{command}"
    if not stripped.startswith(token):
        return None

    cursor = len(token)
    arguments: list[str] = []
    for _ in range(argument_count):
        cursor = skip_whitespace(stripped, cursor)
        if cursor >= len(stripped) or stripped[cursor] != "{":
            return None
        argument, cursor = extract_balanced_content(stripped, cursor, "{", "}")
        arguments.append(argument)

    if stripped[cursor:].strip():
        return None
    return arguments


def merge_header_rows(rows: list[list[str]]) -> list[list[str]]:
    if len(rows) < 2:
        return rows

    first_row = rows[0]
    second_row = rows[1]
    second_row_nonempty = [cell for cell in second_row if cell]
    if not second_row_nonempty:
        return [first_row, *rows[2:]]

    if any("[cite:" in cell for cell in second_row_nonempty):
        return rows

    if any(re.search(r"\d", cell) for cell in second_row_nonempty):
        return rows

    # Only merge when the first two rows look like a multi-line header.
    first_row_nonempty_count = sum(1 for cell in first_row if cell)
    second_row_nonempty_count = sum(1 for cell in second_row if cell)
    has_header_gap = any(not cell for cell in first_row)
    is_sparse_second_header = second_row_nonempty_count < first_row_nonempty_count
    if not has_header_gap and not is_sparse_second_header:
        return rows

    merged: list[str] = []
    previous_header = ""
    for first_cell, second_cell in zip(first_row, second_row, strict=False):
        if first_cell:
            previous_header = first_cell

        if first_cell and second_cell:
            merged.append(f"{first_cell} {second_cell}".strip())
        elif second_cell:
            prefix = previous_header if previous_header else ""
            merged.append(f"{prefix} {second_cell}".strip())
        else:
            merged.append(first_cell)

    return [merged, *rows[2:]]


def drop_empty_columns(rows: list[list[str]]) -> list[list[str]]:
    if not rows:
        return rows

    keep_indices = [
        index
        for index in range(len(rows[0]))
        if any(row[index].strip() for row in rows)
    ]
    return [[row[index] for index in keep_indices] for row in rows]


def cleanup_table_cell(cell: str) -> str:
    cleaned = cell.strip()
    cleaned = replace_command_with_multiple_balanced_arguments(
        cleaned,
        "multicolumn",
        3,
        lambda args: args[2],
    )
    cleaned = replace_command_with_multiple_balanced_arguments(
        cleaned,
        "multirow",
        3,
        lambda args: args[2],
    )
    cleaned = cleaned.replace(r"\boldmath", "")
    cleaned = re.sub(r"\{\\bf\s+([^{}]+)\}", r"\1", cleaned)
    cleaned = re.sub(r"\\bf\b", "", cleaned)
    cleaned = re.sub(r"\\vspace\*?\{[^{}]*\}", "", cleaned)
    cleaned = re.sub(r"\\rule\{[^{}]*\}\{[^{}]*\}", "", cleaned)
    return cleanup_inline_tex(cleaned)


def skip_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def extract_balanced_content(
    text: str,
    start_index: int,
    open_char: str,
    close_char: str,
) -> tuple[str, int]:
    if start_index >= len(text) or text[start_index] != open_char:
        raise ValueError(f"Expected `{open_char}` at index {start_index}.")

    depth = 0
    content: list[str] = []
    index = start_index

    while index < len(text):
        character = text[index]
        if character == open_char:
            depth += 1
            if depth > 1:
                content.append(character)
        elif character == close_char:
            depth -= 1
            if depth == 0:
                return "".join(content), index + 1
            content.append(character)
        else:
            content.append(character)
        index += 1

    raise ValueError(f"Unbalanced `{open_char}{close_char}` pair in LaTeX source.")


def parse_control_sequence_name(text: str, start_index: int) -> tuple[str, int]:
    if start_index >= len(text) or text[start_index] != "\\":
        raise ValueError("Expected a control sequence.")

    index = start_index + 1
    while index < len(text) and text[index].isalpha():
        index += 1
    return text[start_index + 1 : index], index
