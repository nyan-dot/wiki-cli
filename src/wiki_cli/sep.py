from __future__ import annotations

import html
import re
from collections.abc import Callable
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser

from .models import SourceEntry
from .sep_notes import (
    SepFootnoteBlock,
    SepNotesParser,
    footnote_number_from_note_id,
    format_sep_note_cross_reference,
    render_sep_footnotes,
    strip_sep_note_backlink,
    trim_blank_lines,
)
from .utils import markdown_heading_anchor, normalize_inline, slugify


SEP_TAIL_SECTIONS_TO_DROP = {
    "Academic Tools",
    "Other Internet Resources",
}
MARKDOWN_LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<url>[^)\s]+)\)")
SEP_INLINE_NOTE_REF_RE = re.compile(r"\[\[(?P<number>\d+)\]\((?P<url>[^)]+)\)\]")


@dataclass
class PendingLink:
    href: str
    parts: list[str] = field(default_factory=list)


@dataclass
class MarkdownTableBuffer:
    depth: int = 0
    rows: list[list[str]] | None = None
    current_row: list[str] | None = None
    current_cell_parts: list[str] | None = None

    def start_table(self) -> None:
        if self.depth == 0:
            self.rows = []
            self.current_row = None
            self.current_cell_parts = None
        self.depth += 1

    def end_table(self) -> str | None:
        if self.depth == 0:
            return None

        self.depth -= 1
        if self.depth != 0:
            return None

        rendered = render_markdown_table(self.rows or [])
        self.rows = None
        self.current_row = None
        self.current_cell_parts = None
        return rendered

    def start_row(self) -> None:
        if self.inside_table():
            self.current_row = []

    def start_cell(self) -> None:
        if self.inside_table():
            self.current_cell_parts = []

    def append_to_cell(self, text: str) -> None:
        if self.current_cell_parts is not None:
            self.current_cell_parts.append(text)

    def finish_cell(self) -> None:
        if self.current_row is None or self.current_cell_parts is None:
            return
        text = normalize_inline("".join(self.current_cell_parts))
        self.current_row.append(text)
        self.current_cell_parts = None

    def finish_row(self) -> None:
        if self.rows is None or self.current_row is None:
            return
        if any(cell.strip() for cell in self.current_row):
            self.rows.append(self.current_row)
        self.current_row = None

    def inside_table(self) -> bool:
        return self.depth > 0

    def inside_cell(self) -> bool:
        return self.current_cell_parts is not None


@dataclass
class SepLinkContext:
    entry_url: str
    heading_ids_to_anchors: dict[str, str]
    notes_url: str | None = None
    note_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        self._normalized_entry_url = normalize_url_without_fragment(self.entry_url)
        self._normalized_notes_url = (
            normalize_url_without_fragment(self.notes_url)
            if self.notes_url is not None
            else None
        )

    def same_entry_anchor(self, url: str) -> str | None:
        if not self.heading_ids_to_anchors:
            return None
        return same_entry_fragment_to_anchor(
            url,
            self._normalized_entry_url,
            self.heading_ids_to_anchors,
        )

    def same_note_number(self, url: str) -> int | None:
        if self._normalized_notes_url is None or not self.note_ids:
            return None

        normalized_target, fragment = normalize_link_fragment_target(
            url,
            fallback_url=self._normalized_notes_url,
        )
        if normalized_target != self._normalized_notes_url or fragment is None:
            return None
        if fragment not in self.note_ids:
            return None
        return footnote_number_from_note_id(fragment)

    def is_note_reference(self, url: str, number: int) -> bool:
        if self._normalized_notes_url is None:
            return False

        normalized_target, fragment = normalize_link_fragment_target(
            url,
            fallback_url=self._normalized_notes_url,
        )
        return (
            normalized_target == self._normalized_notes_url
            and fragment == f"note-{number}"
        )


class MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, list[str]] = {}
        self.title_text: list[str] = []
        self._inside_title = False
        self._inside_pubinfo = False
        self.pubinfo_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "meta":
            name = attr_map.get("name") or attr_map.get("property")
            content = attr_map.get("content")
            if name and content:
                self.meta.setdefault(name, []).append(html.unescape(content))
        elif tag == "title":
            self._inside_title = True
        elif tag == "div" and attr_map.get("id") == "pubinfo":
            self._inside_pubinfo = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._inside_title = False
        elif tag == "div" and self._inside_pubinfo:
            self._inside_pubinfo = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title_text.append(data)
        if self._inside_pubinfo:
            self.pubinfo_parts.append(data)


class MarkdownArticleParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript"}
    HEADING_LEVELS = {
        "h1": 1,
        "h2": 2,
        "h3": 3,
        "h4": 4,
        "h5": 5,
        "h6": 6,
    }

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.parts: list[str] = []
        self.link_stack: list[PendingLink] = []
        self.skip_depth = 0
        self.list_depth = 0
        self.blockquote_depth = 0
        self._blockquote_just_started = 0
        self.in_pre = False
        self.in_inline_code = False
        self.table_buffer = MarkdownTableBuffer()
        self.heading_ids_to_anchors: dict[str, str] = {}
        self._heading_anchor_counts: dict[str, int] = {}
        self._current_heading_id: str | None = None
        self._current_heading_parts: list[str] | None = None
        self._start_tag_handlers = {
            "p": self._start_paragraph,
            "blockquote": self._start_blockquote,
            "br": self._emit_line_break,
            "hr": self._emit_horizontal_rule,
            "figure": self._start_figure,
            "pre": self._start_preformatted,
            "code": self._start_code,
        }
        self._start_tag_attr_handlers = {
            "a": self._start_link,
            "img": self._emit_image,
        }
        self._end_tag_handlers = {
            "blockquote": self._end_blockquote,
            "figure": self._end_figure,
            "pre": self._end_preformatted,
            "code": self._end_code,
            "a": self._close_link,
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        if self.skip_depth:
            return

        attr_map = {key: value or "" for key, value in attrs}

        if self._current_heading_parts is not None and self._current_heading_id is None:
            nested_heading_id = (
                attr_map.get("id", "").strip() or attr_map.get("name", "").strip()
            )
            if nested_heading_id:
                self._current_heading_id = nested_heading_id

        if tag in self.HEADING_LEVELS:
            self._start_heading(tag, attr_map)
        elif tag == "p":
            self._dispatch_start_tag(tag)
        elif tag in {"ul", "ol"}:
            self._start_list()
        elif tag == "li":
            self._start_list_item()
        elif tag == "table":
            self._start_table()
        elif tag == "tr" and self._inside_table():
            self.table_buffer.start_row()
        elif tag in {"td", "th"} and self._inside_table():
            self.table_buffer.start_cell()
        else:
            self._dispatch_start_tag(tag, attr_map)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth = max(self.skip_depth - 1, 0)
            return

        if self.skip_depth:
            return

        if tag in {"ul", "ol"}:
            self._end_list()
        elif tag in self.HEADING_LEVELS:
            self._end_heading()
        elif tag in {"td", "th"} and self._inside_table():
            self.table_buffer.finish_cell()
        elif tag == "tr" and self._inside_table():
            self.table_buffer.finish_row()
        elif tag == "table" and self._inside_table():
            self._end_table()
        else:
            self._dispatch_end_tag(tag)

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return

        text = html.unescape(data)
        if not text:
            return

        if self.in_pre:
            self._emit(text)
        else:
            collapsed = re.sub(r"\s+", " ", text.replace("\xa0", " "))
            if self._current_heading_parts is not None:
                self._current_heading_parts.append(collapsed)
            self._emit(collapsed)

    def to_markdown(self) -> str:
        text = "".join(self.parts)
        lines = [line.rstrip() for line in text.splitlines()]

        cleaned: list[str] = []
        previous_blank = False
        for line in lines:
            normalized = normalize_markdown_line(line)
            if not normalized:
                if not previous_blank:
                    cleaned.append("")
                previous_blank = True
                continue
            cleaned.append(normalized)
            previous_blank = False

        return "\n".join(cleaned).strip() + "\n"

    def _emit(self, text: str) -> None:
        if self.link_stack:
            self.link_stack[-1].parts.append(text)
        elif self._inside_table_cell():
            self.table_buffer.append_to_cell(text)
        else:
            self.parts.append(text)

    def _dispatch_start_tag(
        self,
        tag: str,
        attr_map: dict[str, str] | None = None,
    ) -> None:
        handler = self._start_tag_handlers.get(tag)
        if handler is not None:
            handler()
            return

        if attr_map is None:
            return

        attr_handler = self._start_tag_attr_handlers.get(tag)
        if attr_handler is not None:
            attr_handler(attr_map)

    def _dispatch_end_tag(self, tag: str) -> None:
        handler = self._end_tag_handlers.get(tag)
        if handler is not None:
            handler()

    def _start_paragraph(self) -> None:
        if self._inside_table_cell():
            if self.table_buffer.current_cell_parts:
                self._emit("\n")
            return

        if self.blockquote_depth:
            if self._blockquote_just_started:
                self._blockquote_just_started -= 1
            else:
                self._emit("\n>\n> ")
            return

        self._emit("\n\n")

    def _start_heading(self, tag: str, attr_map: dict[str, str]) -> None:
        level = self.HEADING_LEVELS[tag]
        self._current_heading_id = attr_map.get("id", "").strip() or None
        self._current_heading_parts = []
        self._emit(f"\n\n{'#' * level} ")

    def _end_heading(self) -> None:
        self._finish_heading()
        self._emit("\n")

    def _start_list(self) -> None:
        self.list_depth += 1
        self._emit("\n")

    def _end_list(self) -> None:
        self.list_depth = max(self.list_depth - 1, 0)
        self._emit("\n")

    def _start_list_item(self) -> None:
        indent = "  " * max(self.list_depth - 1, 0)
        self._emit(f"\n{indent}- ")

    def _start_blockquote(self) -> None:
        self.blockquote_depth += 1
        self._blockquote_just_started += 1
        self._emit("\n\n> ")

    def _end_blockquote(self) -> None:
        self.blockquote_depth = max(self.blockquote_depth - 1, 0)
        if self.blockquote_depth == 0:
            self._blockquote_just_started = 0
        self._emit("\n")

    def _emit_line_break(self) -> None:
        if self.blockquote_depth:
            self._emit("\n> ")
        else:
            self._emit("\n")

    def _emit_horizontal_rule(self) -> None:
        self._emit("\n\n---\n\n")

    def _start_figure(self) -> None:
        self._emit("\n\n")

    def _end_figure(self) -> None:
        self._emit("\n\n")

    def _start_table(self) -> None:
        if not self._inside_table():
            self._emit("\n\n")
        self.table_buffer.start_table()

    def _end_table(self) -> None:
        rendered = self.table_buffer.end_table()
        if rendered is not None:
            self._emit(rendered)
            self._emit("\n\n")

    def _start_preformatted(self) -> None:
        self.in_pre = True
        self._emit("\n\n```\n")

    def _end_preformatted(self) -> None:
        self._emit("\n```\n")
        self.in_pre = False

    def _start_code(self) -> None:
        if self.in_pre:
            return
        self.in_inline_code = True
        self._emit("`")

    def _end_code(self) -> None:
        if not self.in_inline_code:
            return
        self._emit("`")
        self.in_inline_code = False

    def _start_link(self, attr_map: dict[str, str]) -> None:
        self.link_stack.append(PendingLink(href=attr_map.get("href", "").strip()))

    def _emit_image(self, attr_map: dict[str, str]) -> None:
        src = attr_map.get("src", "").strip()
        if not src:
            return
        alt = normalize_inline(attr_map.get("alt", "")) or "Image"
        absolute_src = urllib.parse.urljoin(self.base_url, src)
        self._emit(f"![{alt}]({absolute_src})")

    def _close_link(self) -> None:
        if not self.link_stack:
            return
        link = self.link_stack.pop()
        raw_text = "".join(link.parts)
        text = normalize_inline(raw_text)
        if not text:
            return

        prefix = " " if raw_text[:1].isspace() else ""
        suffix = " " if raw_text[-1:].isspace() else ""
        if link.href:
            absolute_href = urllib.parse.urljoin(self.base_url, link.href)
            self._emit(f"{prefix}[{text}]({absolute_href}){suffix}")
        else:
            self._emit(f"{prefix}{text}{suffix}")

    def _finish_heading(self) -> None:
        heading_text = normalize_inline("".join(self._current_heading_parts or []))
        if self._current_heading_id and heading_text:
            base_anchor = markdown_heading_anchor(heading_text)
            occurrence = self._heading_anchor_counts.get(base_anchor, 0)
            anchor = base_anchor if occurrence == 0 else f"{base_anchor}-{occurrence}"
            self._heading_anchor_counts[base_anchor] = occurrence + 1
            self.heading_ids_to_anchors[self._current_heading_id] = anchor

        self._current_heading_id = None
        self._current_heading_parts = None

    def _inside_table(self) -> bool:
        return self.table_buffer.inside_table()

    def _inside_table_cell(self) -> bool:
        return self.table_buffer.inside_cell()


LIST_LINE_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>(?:[-*+])|(?:\d+\.))\s+(?P<body>.*)$")


def normalize_markdown_line(line: str) -> str:
    if not line.strip():
        return ""

    list_match = LIST_LINE_RE.match(line)
    if list_match:
        indent = list_match.group("indent")
        marker = list_match.group("marker")
        body = re.sub(r" +", " ", list_match.group("body")).strip()
        return f"{indent}{marker} {body}".rstrip()

    if line.lstrip().startswith(">"):
        stripped = line.lstrip()
        quote_prefix = "> "
        quote_body = stripped[1:].strip()
        return f"{quote_prefix}{re.sub(r' +', ' ', quote_body)}".rstrip()

    return re.sub(r" +", " ", line).strip()


def is_markdown_link_list_item(line: str) -> bool:
    match = LIST_LINE_RE.match(line)
    if match is None:
        return False
    return match.group("body").lstrip().startswith("[")


def render_markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""

    max_columns = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (max_columns - len(row)) for row in rows]
    header = normalized_rows[0]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * max_columns) + " |",
    ]
    for row in normalized_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def fetch_url(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "wiki-cli/0.1 (+https://example.invalid/local-knowledge-base)"
        },
    )
    with urllib.request.urlopen(request) as response:
        return response.read().decode("utf-8", errors="ignore")


def fetch_optional_url(url: str) -> str | None:
    try:
        return fetch_url(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def extract_sep_article_html(page_html: str) -> str:
    start_marker = '<div id="aueditable">'
    end_marker = "</div><!-- #aueditable -->"

    start_index = page_html.find(start_marker)
    end_index = page_html.find(end_marker)

    if start_index == -1 or end_index == -1 or end_index <= start_index:
        raise ValueError("Could not locate the main SEP article body in the HTML.")

    start_index += len(start_marker)
    return page_html[start_index:end_index]


def parse_sep_entry(url: str, page_html: str, slug: str | None = None) -> SourceEntry:
    parser = MetaParser()
    parser.feed(page_html)

    title = first_meta_value(parser.meta, "citation_title")
    if not title:
        raw_title = "".join(parser.title_text).strip()
        title = re.sub(r"\s*\(Stanford Encyclopedia of Philosophy\)\s*$", "", raw_title)
    if not title:
        raise ValueError("Could not determine the SEP entry title.")

    authors = parser.meta.get("citation_author", [])
    first_published = first_meta_value(parser.meta, "citation_publication_date")
    pubinfo = normalize_inline("".join(parser.pubinfo_parts)) or None

    parsed_url = urllib.parse.urlparse(url)
    derived_slug = slug or slugify(parsed_url.path.rstrip("/").split("/")[-1] or title)

    return SourceEntry(
        source_type="sep",
        slug=derived_slug,
        title=title,
        url=url,
        authors=authors,
        first_published=first_published,
        pubinfo=pubinfo,
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        canonical_id=derived_slug,
    )


def first_meta_value(meta: dict[str, list[str]], key: str) -> str | None:
    values = meta.get(key) or []
    return values[0] if values else None


def convert_sep_html_to_markdown(
    article_html: str,
    base_url: str,
    *,
    notes_html: str | None = None,
    notes_url: str | None = None,
) -> str:
    parser = MarkdownArticleParser(base_url)
    parser.feed(article_html)
    link_context = SepLinkContext(
        entry_url=base_url,
        heading_ids_to_anchors=parser.heading_ids_to_anchors,
        notes_url=notes_url,
    )
    markdown = parser.to_markdown()
    markdown = rewrite_same_entry_links(markdown, link_context)
    markdown = postprocess_sep_markdown(markdown)
    if notes_html and notes_url:
        footnotes = extract_sep_footnotes(
            notes_html,
            link_context=link_context,
        )
        if footnotes:
            markdown = apply_sep_footnotes(
                markdown,
                link_context=link_context,
                footnotes=footnotes,
            )
    return markdown


def rewrite_markdown_links(
    markdown: str,
    replacer: Callable[[str, str], str | None],
) -> str:
    def replace_link(match: re.Match[str]) -> str:
        replacement = replacer(match.group("label"), match.group("url"))
        return replacement if replacement is not None else match.group(0)

    return MARKDOWN_LINK_RE.sub(replace_link, markdown)


def rewrite_same_entry_links(markdown: str, link_context: SepLinkContext) -> str:
    if not link_context.heading_ids_to_anchors:
        return markdown

    def replace_link(label: str, url: str) -> str | None:
        anchor = link_context.same_entry_anchor(url)
        if anchor is None:
            return None
        return f"[{label}](#{anchor})"

    return rewrite_markdown_links(markdown, replace_link)


def same_entry_fragment_to_anchor(
    url: str,
    normalized_base: str,
    heading_ids_to_anchors: dict[str, str],
) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if not parsed.fragment:
        return None

    if parsed.scheme or parsed.netloc or parsed.path or parsed.query:
        normalized_target = normalize_url_without_fragment(url)
        if normalized_target != normalized_base:
            return None

    fragment = urllib.parse.unquote(parsed.fragment)
    return heading_ids_to_anchors.get(fragment)


def normalize_link_fragment_target(
    url: str,
    *,
    fallback_url: str,
) -> tuple[str | None, str | None]:
    parsed = urllib.parse.urlparse(url)
    if not parsed.fragment:
        return None, None

    normalized_target = (
        normalize_url_without_fragment(url)
        if parsed.scheme or parsed.netloc or parsed.path or parsed.query
        else fallback_url
    )
    fragment = urllib.parse.unquote(parsed.fragment)
    return normalized_target, fragment


def normalize_url_without_fragment(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    normalized_path = parsed.path
    if normalized_path.endswith("/index.html"):
        normalized_path = normalized_path[: -len("/index.html")] or "/"
    normalized_path = normalized_path.rstrip("/") or "/"
    return urllib.parse.urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            "",
            parsed.query,
            "",
        )
    )


def postprocess_sep_markdown(markdown: str) -> str:
    lines = markdown.splitlines()
    lines = remove_sep_toc_block(lines)
    lines = drop_sep_tail_sections(lines, SEP_TAIL_SECTIONS_TO_DROP)
    lines = rewrite_related_entries_section(lines)
    return collapse_blank_lines(lines)


def extract_sep_footnotes(
    notes_html: str,
    *,
    link_context: SepLinkContext,
) -> list[SepFootnoteBlock]:
    if link_context.notes_url is None:
        return []

    notes_article_html = extract_sep_article_html(notes_html)
    parser = SepNotesParser()
    parser.feed(notes_article_html)

    note_ids = tuple(parser.note_html_by_id.keys())
    note_link_context = SepLinkContext(
        entry_url=link_context.entry_url,
        heading_ids_to_anchors=link_context.heading_ids_to_anchors,
        notes_url=link_context.notes_url,
        note_ids=frozenset(note_ids),
    )
    footnotes: list[SepFootnoteBlock] = []
    for note_id in note_ids:
        number = footnote_number_from_note_id(note_id)
        if number is None:
            continue

        note_markdown = convert_sep_note_html_to_markdown(
            parser.note_html_by_id[note_id],
            link_context=note_link_context,
        )
        body_lines = trim_blank_lines(note_markdown.splitlines())
        if not body_lines:
            continue

        footnotes.append(
            SepFootnoteBlock(number=number, note_id=note_id, body_lines=body_lines)
        )

    return footnotes
def convert_sep_note_html_to_markdown(
    note_html: str,
    *,
    link_context: SepLinkContext,
) -> str:
    if link_context.notes_url is None:
        return ""

    parser = MarkdownArticleParser(link_context.notes_url)
    parser.feed(note_html)
    markdown = parser.to_markdown()
    markdown = rewrite_same_entry_links(markdown, link_context)
    markdown = rewrite_sep_note_internal_links(
        markdown,
        link_context=link_context,
    )
    markdown = strip_sep_note_backlink(markdown)
    return collapse_blank_lines(markdown.splitlines())


def rewrite_sep_note_internal_links(
    markdown: str,
    *,
    link_context: SepLinkContext,
) -> str:
    if not link_context.note_ids:
        return markdown

    def replace_link(label: str, url: str) -> str | None:
        note_number = link_context.same_note_number(url)
        if note_number is None:
            return None
        return format_sep_note_cross_reference(label, note_number)

    return rewrite_markdown_links(markdown, replace_link)


def apply_sep_footnotes(
    markdown: str,
    *,
    link_context: SepLinkContext,
    footnotes: list[SepFootnoteBlock],
) -> str:
    rewritten = rewrite_sep_inline_footnote_references(
        markdown,
        link_context=link_context,
        footnote_numbers={footnote.number for footnote in footnotes},
    )
    rendered = render_sep_footnotes(footnotes)
    if not rendered:
        return rewritten

    lines = rewritten.splitlines()
    insert_at = next(
        (index for index, line in enumerate(lines) if line == "## Bibliography"),
        len(lines),
    )

    rebuilt = lines[:insert_at]
    if rebuilt and rebuilt[-1].strip():
        rebuilt.append("")
    rebuilt.extend(rendered)

    if insert_at < len(lines):
        if rebuilt and rebuilt[-1].strip():
            rebuilt.append("")
        rebuilt.extend(lines[insert_at:])

    return collapse_blank_lines(rebuilt)


def rewrite_sep_inline_footnote_references(
    markdown: str,
    *,
    link_context: SepLinkContext,
    footnote_numbers: set[int],
) -> str:
    def replace_reference(match: re.Match[str]) -> str:
        number = int(match.group("number"))
        if number not in footnote_numbers:
            return match.group(0)

        if not link_context.is_note_reference(match.group("url"), number):
            return match.group(0)
        return f"[^{number}]"

    return SEP_INLINE_NOTE_REF_RE.sub(replace_reference, markdown)


def remove_sep_toc_block(lines: list[str]) -> list[str]:
    try:
        hr_index = lines.index("---")
    except ValueError:
        return lines

    candidate_end = hr_index - 1
    while candidate_end >= 0 and not lines[candidate_end].strip():
        candidate_end -= 1

    if candidate_end < 0 or not is_markdown_link_list_item(lines[candidate_end]):
        return lines

    start = candidate_end
    while start >= 0 and (
        not lines[start].strip() or is_markdown_link_list_item(lines[start])
    ):
        start -= 1
    start += 1

    bullet_count = sum(
        1 for line in lines[start:hr_index] if is_markdown_link_list_item(line)
    )
    if bullet_count < 3:
        return lines

    next_index = hr_index + 1
    while next_index < len(lines) and not lines[next_index].strip():
        next_index += 1

    if next_index >= len(lines) or not lines[next_index].startswith("## "):
        return lines

    return lines[:start] + [""] + lines[next_index:]


def drop_sep_tail_sections(lines: list[str], section_titles: set[str]) -> list[str]:
    kept: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.startswith("## ") and line[3:] in section_titles:
            index += 1
            while index < len(lines) and not lines[index].startswith("## "):
                index += 1
            continue

        kept.append(line)
        index += 1

    return kept


def rewrite_related_entries_section(lines: list[str]) -> list[str]:
    rebuilt: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        rebuilt.append(line)

        if line == "## Related Entries":
            index += 1
            section_lines: list[str] = []
            while index < len(lines) and not lines[index].startswith("#"):
                section_lines.append(lines[index])
                index += 1

            nonempty = [item.strip() for item in section_lines if item.strip()]
            related_blob = " ".join(nonempty)
            if " | " in related_blob:
                rebuilt.append("")
                rebuilt.extend(
                    f"- {entry.strip()}"
                    for entry in related_blob.split(" | ")
                    if entry.strip()
                )
                if index < len(lines) and lines[index].startswith("#"):
                    rebuilt.append("")
            else:
                rebuilt.extend(section_lines)
            continue

        index += 1

    return rebuilt


def collapse_blank_lines(lines: list[str]) -> str:
    cleaned: list[str] = []
    previous_blank = False

    for line in lines:
        if not line.strip():
            if not previous_blank:
                cleaned.append("")
            previous_blank = True
            continue

        cleaned.append(line.rstrip())
        previous_blank = False

    return "\n".join(cleaned).strip() + "\n"
