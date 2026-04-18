from __future__ import annotations

import html
import re
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser

from .models import SourceEntry
from .sep import MarkdownArticleParser
from .sep import fetch_url as sep_fetch_url
from .utils import normalize_inline, slugify


LESSWRONG_HOSTS = {"lesswrong.com", "www.lesswrong.com"}
POST_PATH_RE = re.compile(
    r"^/posts/(?P<post_id>[A-Za-z0-9]+)/?(?P<slug>[A-Za-z0-9-]+)?/?$"
)
INLINE_FOOTNOTE_RE = re.compile(
    r"\[\[(?P<number>\d+)\]\]\((?P<url>[^)]+#(?:fn|fnd)[^)]+)\)"
)
TRAILING_FOOTNOTE_MARKER_RE = re.compile(r"^- \[\^\]\((?P<url>[^)]+#fnref[^)]+)\)$")
TRAILING_FOOTNOTE_BULLET_RE = re.compile(r"^-\s*$")
TRAILING_FOOTNOTE_BACKLINK_RE = re.compile(
    r"\s*\[\[\^\]\]\([^)]+#fnref[^)]+\)$"
)


@dataclass
class FootnoteBlock:
    number: int
    body_lines: list[str]


class LessWrongMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, list[str]] = {}
        self.canonical_url: str | None = None
        self.time_datetime: str | None = None
        self.time_text_parts: list[str] = []
        self._inside_title = False
        self._inside_time = False
        self.title_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "meta":
            name = attr_map.get("name") or attr_map.get("property")
            content = attr_map.get("content")
            if name and content:
                self.meta.setdefault(name, []).append(html.unescape(content))
        elif tag == "link" and attr_map.get("rel") == "canonical":
            href = attr_map.get("href", "").strip()
            if href:
                self.canonical_url = href
        elif tag == "title":
            self._inside_title = True
        elif tag == "time" and self.time_datetime is None:
            self.time_datetime = attr_map.get("datetime", "").strip() or None
            self._inside_time = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._inside_title = False
        elif tag == "time" and self._inside_time:
            self._inside_time = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title_text.append(data)
        if self._inside_time:
            self.time_text_parts.append(data)


def normalize_lesswrong_url(url: str) -> tuple[str, str, str | None]:
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("Missing LessWrong URL.")

    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or parsed.netloc not in LESSWRONG_HOSTS:
        raise ValueError("LessWrong imports require a https://www.lesswrong.com/posts/... URL.")

    match = POST_PATH_RE.match(parsed.path)
    if match is None:
        raise ValueError(
            "LessWrong imports require a post URL like "
            "`https://www.lesswrong.com/posts/<post-id>/<slug>`."
        )

    post_id = match.group("post_id")
    slug = match.group("slug")
    canonical_path = f"/posts/{post_id}"
    if slug:
        canonical_path += f"/{slug}"

    canonical_url = urllib.parse.urlunparse(
        ("https", "www.lesswrong.com", canonical_path, "", "", "")
    )
    return canonical_url, post_id, slug


def fetch_url(url: str) -> str:
    return sep_fetch_url(url)


def parse_lesswrong_entry(
    url: str,
    page_html: str,
    slug: str | None = None,
) -> SourceEntry:
    normalized_url, post_id, url_slug = normalize_lesswrong_url(url)

    parser = LessWrongMetaParser()
    parser.feed(page_html)

    title = first_meta_value(parser.meta, "citation_title")
    if not title:
        raw_title = "".join(parser.title_text).strip()
        title = re.sub(r"\s*[—-]\s*LessWrong\s*$", "", raw_title)
    if not title:
        raise ValueError("Could not determine the LessWrong post title.")

    authors = parser.meta.get("citation_author", [])
    description = first_meta_value(parser.meta, "description")

    published_at = parse_iso_datetime(parser.time_datetime)
    published_text = normalize_inline("".join(parser.time_text_parts)) or None
    first_published = published_at.date().isoformat() if published_at else None

    canonical_url = parser.canonical_url or normalized_url
    derived_slug = slug or url_slug or slugify(title)

    return SourceEntry(
        source_type="lesswrong",
        slug=derived_slug,
        title=title,
        url=canonical_url,
        authors=authors,
        first_published=first_published,
        pubinfo=published_text,
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        abstract=description,
        canonical_id=post_id,
    )


def first_meta_value(meta: dict[str, list[str]], key: str) -> str | None:
    values = meta.get(key) or []
    return values[0] if values else None


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def extract_lesswrong_post_html(page_html: str) -> str:
    match = re.search(
        r"<div\b[^>]*\bid=(['\"])postContent\1[^>]*>",
        page_html,
        re.IGNORECASE,
    )
    if match is None:
        raise ValueError("Could not locate the LessWrong post body in the HTML.")

    start_index = match.end()
    depth = 1
    token_re = re.compile(r"<div\b[^>]*>|</div>", re.IGNORECASE)

    for token_match in token_re.finditer(page_html, start_index):
        token = token_match.group(0)
        if token.startswith("</"):
            depth -= 1
        else:
            depth += 1

        if depth == 0:
            return page_html[start_index : token_match.start()]

    raise ValueError("Could not determine the end of the LessWrong post body.")


def convert_lesswrong_html_to_markdown(article_html: str, base_url: str) -> str:
    parser = MarkdownArticleParser(base_url)
    parser.feed(article_html)
    markdown = parser.to_markdown()
    return postprocess_lesswrong_markdown(markdown)


def postprocess_lesswrong_markdown(markdown: str) -> str:
    lines = markdown.splitlines()
    lines = convert_footnote_footer(lines)
    collapsed = collapse_blank_lines(lines)
    return add_missing_spaces_after_links(collapsed)


def convert_footnote_footer(lines: list[str]) -> list[str]:
    footnotes: list[FootnoteBlock] = []
    rebuilt: list[str] = []
    footnote_start = trailing_footnote_start(lines)
    if footnote_start is None:
        index = 0
        while index < len(lines):
            line = lines[index]
            if line == "---":
                footnotes = parse_legacy_footnotes(lines[index + 1 :])
                if footnotes:
                    break
            rebuilt.append(line)
            index += 1
    else:
        rebuilt = lines[:footnote_start]
        footnotes = parse_linked_footnotes(lines[footnote_start:])

    text = "\n".join(rebuilt)
    text = rewrite_inline_footnote_references(text)

    rebuilt = text.splitlines()
    if footnotes:
        if rebuilt and rebuilt[-1].strip():
            rebuilt.append("")
        rebuilt.extend(render_footnotes(footnotes))
    return rebuilt


def trailing_footnote_start(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if TRAILING_FOOTNOTE_MARKER_RE.match(stripped) or TRAILING_FOOTNOTE_BULLET_RE.match(
            stripped
        ):
            return index
    return None


def parse_linked_footnotes(lines: list[str]) -> list[FootnoteBlock]:
    footnotes: list[FootnoteBlock] = []
    index = 0
    footnote_number = 1

    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue

        if not (
            TRAILING_FOOTNOTE_MARKER_RE.match(stripped)
            or TRAILING_FOOTNOTE_BULLET_RE.match(stripped)
        ):
            break

        index += 1
        content_lines: list[str] = []
        while index < len(lines):
            raw_line = lines[index].rstrip()
            candidate = raw_line.strip()
            if TRAILING_FOOTNOTE_MARKER_RE.match(
                candidate
            ) or TRAILING_FOOTNOTE_BULLET_RE.match(candidate):
                break
            sanitized = TRAILING_FOOTNOTE_BACKLINK_RE.sub("", raw_line).rstrip()
            content_lines.append(sanitized)
            index += 1

        trimmed = trim_blank_lines(content_lines)
        if trimmed:
            footnotes.append(FootnoteBlock(number=footnote_number, body_lines=trimmed))
            footnote_number += 1

    return footnotes


def render_footnotes(footnotes: list[FootnoteBlock]) -> list[str]:
    rendered: list[str] = []
    for footnote in footnotes:
        rendered.extend(render_footnote(footnote))
    return rendered


def render_footnote(footnote: FootnoteBlock) -> list[str]:
    if len(footnote.body_lines) == 1:
        return [f"[^{footnote.number}]: {footnote.body_lines[0].strip()}"]

    formatted = [f"[^{footnote.number}]:"]
    for line in footnote.body_lines:
        if not line.strip():
            formatted.append("")
        else:
            formatted.append(f"    {line}")
    return formatted


def trim_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)

    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1

    return lines[start:end]


def rewrite_inline_footnote_references(markdown: str) -> str:
    return INLINE_FOOTNOTE_RE.sub(
        lambda match: f"[^{match.group('number')}]",
        markdown,
    )


def parse_legacy_footnotes(lines: list[str]) -> list[FootnoteBlock]:
    footnotes: list[FootnoteBlock] = []

    for fallback_index, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if not stripped.startswith("- "):
            return []
        content = stripped[2:]
        footnote_number = legacy_footnote_number_from_line(content) or fallback_index
        content = re.sub(r"\s*\[↩︎\]\(about:blank#fnref-[^)]+\)", "", content).strip()
        if not content:
            continue
        footnotes.append(FootnoteBlock(number=footnote_number, body_lines=[content]))

    return footnotes


def legacy_footnote_number_from_line(line: str) -> int | None:
    match = re.search(r"about:blank#fnref-[^)]*-(\d+)\)", line)
    if match is None:
        return None
    return int(match.group(1))


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


def add_missing_spaces_after_links(markdown: str) -> str:
    return re.sub(r"(\[[^\]]+\]\([^)]+\))([A-Za-z])", r"\1 \2", markdown)
