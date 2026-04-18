from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser

from .models import SourceEntry
from .utils import markdown_heading_anchor, normalize_inline, slugify


SEP_TAIL_SECTIONS_TO_DROP = {
    "Academic Tools",
    "Other Internet Resources",
}
MARKDOWN_LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<url>[^)\s]+)\)")


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
        self.link_stack: list[dict[str, str | list[str]]] = []
        self.skip_depth = 0
        self.list_depth = 0
        self.in_pre = False
        self.in_inline_code = False
        self.heading_ids_to_anchors: dict[str, str] = {}
        self._heading_anchor_counts: dict[str, int] = {}
        self._current_heading_id: str | None = None
        self._current_heading_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        if self.skip_depth:
            return

        attr_map = {key: value or "" for key, value in attrs}

        if tag in self.HEADING_LEVELS:
            level = self.HEADING_LEVELS[tag]
            self._current_heading_id = attr_map.get("id", "").strip() or None
            self._current_heading_parts = []
            self._emit(f"\n\n{'#' * level} ")
        elif tag == "p":
            self._emit("\n\n")
        elif tag in {"ul", "ol"}:
            self.list_depth += 1
            self._emit("\n")
        elif tag == "li":
            indent = "  " * max(self.list_depth - 1, 0)
            self._emit(f"\n{indent}- ")
        elif tag == "blockquote":
            self._emit("\n\n> ")
        elif tag == "br":
            self._emit("\n")
        elif tag == "hr":
            self._emit("\n\n---\n\n")
        elif tag == "pre":
            self.in_pre = True
            self._emit("\n\n```\n")
        elif tag == "code":
            if self.in_pre:
                return
            self.in_inline_code = True
            self._emit("`")
        elif tag == "a":
            self.link_stack.append(
                {"href": attr_map.get("href", "").strip(), "parts": []}
            )

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth = max(self.skip_depth - 1, 0)
            return

        if self.skip_depth:
            return

        if tag in {"ul", "ol"}:
            self.list_depth = max(self.list_depth - 1, 0)
            self._emit("\n")
        elif tag in self.HEADING_LEVELS:
            self._finish_heading()
            self._emit("\n")
        elif tag == "blockquote":
            self._emit("\n")
        elif tag == "pre":
            self._emit("\n```\n")
            self.in_pre = False
        elif tag == "code" and self.in_inline_code:
            self._emit("`")
            self.in_inline_code = False
        elif tag == "a" and self.link_stack:
            link = self.link_stack.pop()
            text = normalize_inline("".join(link["parts"]))
            href = str(link["href"]).strip()
            if text:
                if href:
                    absolute_href = urllib.parse.urljoin(self.base_url, href)
                    self._emit(f"[{text}]({absolute_href})")
                else:
                    self._emit(text)

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
            normalized = re.sub(r" +", " ", line).strip()
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
            self.link_stack[-1]["parts"].append(text)
        else:
            self.parts.append(text)

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


def fetch_url(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "wiki-cli/0.1 (+https://example.invalid/local-knowledge-base)"
        },
    )
    with urllib.request.urlopen(request) as response:
        return response.read().decode("utf-8", errors="ignore")


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


def convert_sep_html_to_markdown(article_html: str, base_url: str) -> str:
    parser = MarkdownArticleParser(base_url)
    parser.feed(article_html)
    markdown = parser.to_markdown()
    markdown = rewrite_same_entry_links(
        markdown,
        base_url,
        parser.heading_ids_to_anchors,
    )
    return postprocess_sep_markdown(markdown)


def rewrite_same_entry_links(
    markdown: str,
    base_url: str,
    heading_ids_to_anchors: dict[str, str],
) -> str:
    if not heading_ids_to_anchors:
        return markdown

    normalized_base = normalize_url_without_fragment(base_url)

    def replace_link(match: re.Match[str]) -> str:
        label = match.group("label")
        url = match.group("url")
        anchor = same_entry_fragment_to_anchor(
            url,
            normalized_base,
            heading_ids_to_anchors,
        )
        if anchor is None:
            return match.group(0)
        return f"[{label}](#{anchor})"

    return MARKDOWN_LINK_RE.sub(replace_link, markdown)


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


def normalize_url_without_fragment(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    normalized_path = parsed.path.rstrip("/") or "/"
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


def remove_sep_toc_block(lines: list[str]) -> list[str]:
    try:
        hr_index = lines.index("---")
    except ValueError:
        return lines

    candidate_end = hr_index - 1
    while candidate_end >= 0 and not lines[candidate_end].strip():
        candidate_end -= 1

    if candidate_end < 0 or not lines[candidate_end].startswith("- ["):
        return lines

    start = candidate_end
    while start >= 0 and (not lines[start].strip() or lines[start].startswith("- [")):
        start -= 1
    start += 1

    bullet_count = sum(1 for line in lines[start:hr_index] if line.startswith("- ["))
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
