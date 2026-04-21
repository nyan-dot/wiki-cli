from __future__ import annotations

import html
import json
import re
import urllib.parse
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import PurePosixPath

from .models import SourceEntry
from .sep import MarkdownArticleParser, SepLinkContext, rewrite_same_entry_links
from .sep import fetch_url as sep_fetch_url
from .utils import normalize_inline, slugify

TRANSFORMER_CIRCUITS_HOSTS = {
    "transformer-circuits.pub",
    "www.transformer-circuits.pub",
}
FRONT_MATTER_RE = re.compile(
    r"<d-front-matter>\s*<script type=(['\"])text/json\1>\s*(\{.*?\})\s*</script>\s*</d-front-matter>",
    re.IGNORECASE | re.DOTALL,
)
D_CONTENTS_RE = re.compile(
    r"<d-contents\b[^>]*>.*?</d-contents>",
    re.IGNORECASE | re.DOTALL,
)
D_FOOTNOTE_RE = re.compile(
    r"<d-footnote\b[^>]*>(?P<body>.*?)</d-footnote>",
    re.IGNORECASE | re.DOTALL,
)
D_HA_BLOCK_RE = re.compile(
    r"<div\b(?P<attrs>[^>]*)class=(?P<quote>['\"])(?P<classname>[^'\"]*\bha-block\b[^'\"]*)(?P=quote)(?P<rest>[^>]*)>(?P<body>.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)
BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
FOOTNOTE_TOKEN_TEMPLATE = "__WIKI_ANTHROPIC_FOOTNOTE_{number}__"


class AnthropicMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, list[str]] = {}
        self.title_text: list[str] = []
        self._inside_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "meta":
            name = attr_map.get("name") or attr_map.get("property")
            content = attr_map.get("content")
            if name and content:
                self.meta.setdefault(name, []).append(html.unescape(content))
        elif tag == "title":
            self._inside_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title_text.append(data)


def normalize_anthropic_url(url: str) -> tuple[str, str, str, str | None]:
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("Missing Anthropic interpretability URL.")

    parsed = urllib.parse.urlparse(cleaned)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.netloc not in TRANSFORMER_CIRCUITS_HOSTS
    ):
        raise ValueError(
            "Anthropic interpretability imports currently require a "
            "`https://transformer-circuits.pub/...` article URL."
        )

    normalized_path = parsed.path.rstrip("/")
    if not normalized_path.endswith(".html"):
        raise ValueError(
            "Anthropic interpretability imports require an article URL ending in "
            "`.html`, such as "
            "`https://transformer-circuits.pub/2025/attribution-graphs/biology.html`."
        )

    canonical_url = urllib.parse.urlunparse(
        ("https", "transformer-circuits.pub", normalized_path, "", "", "")
    )
    canonical_id = normalized_path.lstrip("/")[: -len(".html")]
    url_slug = PurePosixPath(normalized_path).stem
    year = infer_transformer_circuits_year(normalized_path)
    return canonical_url, canonical_id, url_slug, year


def infer_transformer_circuits_year(path: str) -> str | None:
    match = re.match(r"^/(?P<year>\d{4})/", path)
    if match is None:
        return None
    return match.group("year")


def fetch_url(url: str) -> str:
    return sep_fetch_url(url)


def parse_anthropic_entry(
    url: str,
    page_html: str,
    slug: str | None = None,
) -> SourceEntry:
    normalized_url, canonical_id, url_slug, year = normalize_anthropic_url(url)

    parser = AnthropicMetaParser()
    parser.feed(page_html)
    front_matter = parse_front_matter(page_html)

    title = (
        first_meta_value(parser.meta, "og:title")
        or front_matter_string(front_matter, "title")
        or normalize_inline("".join(parser.title_text))
        or None
    )
    if not title:
        raise ValueError("Could not determine the Anthropic article title.")

    description = (
        first_meta_value(parser.meta, "og:description")
        or front_matter_string(front_matter, "description")
        or None
    )
    authors = front_matter_authors(front_matter)
    pubinfo = (
        f"Transformer Circuits article ({year})"
        if year
        else "Transformer Circuits article"
    )
    derived_slug = slug or url_slug or slugify(title)

    return SourceEntry(
        source_type="anthropic",
        slug=derived_slug,
        title=title,
        url=normalized_url,
        authors=authors,
        first_published=year,
        pubinfo=pubinfo,
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        abstract=description,
        canonical_id=canonical_id,
    )


def parse_front_matter(page_html: str) -> dict[str, object]:
    match = FRONT_MATTER_RE.search(page_html)
    if match is None:
        return {}

    try:
        data = json.loads(match.group(2))
    except json.JSONDecodeError:
        return {}

    if not isinstance(data, dict):
        return {}
    return data


def front_matter_string(front_matter: dict[str, object], key: str) -> str | None:
    value = front_matter.get(key)
    if not isinstance(value, str):
        return None
    normalized = normalize_inline(value)
    return normalized or None


def front_matter_authors(front_matter: dict[str, object]) -> list[str]:
    raw_authors = front_matter.get("authors")
    if not isinstance(raw_authors, list):
        return []

    authors: list[str] = []
    for author in raw_authors:
        if isinstance(author, str):
            normalized = normalize_inline(author)
            if normalized:
                authors.append(normalized)
            continue

        if isinstance(author, dict):
            for key in ["name", "author"]:
                value = author.get(key)
                if isinstance(value, str):
                    normalized = normalize_inline(value)
                    if normalized:
                        authors.append(normalized)
                    break

    return authors


def first_meta_value(meta: dict[str, list[str]], key: str) -> str | None:
    values = meta.get(key) or []
    return values[0] if values else None


def extract_anthropic_article_html(page_html: str) -> str:
    for tag in ["d-article", "article", "main", "body"]:
        article_html = extract_tag_inner_html(page_html, tag)
        if article_html is not None:
            return article_html

    raise ValueError("Could not locate the Anthropic article body in the HTML.")


def extract_tag_inner_html(page_html: str, tag_name: str) -> str | None:
    match = re.search(
        rf"<{tag_name}\b[^>]*>",
        page_html,
        re.IGNORECASE,
    )
    if match is None:
        return None

    start_index = match.end()
    depth = 1
    token_re = re.compile(
        rf"<{tag_name}\b[^>]*>|</{tag_name}>",
        re.IGNORECASE,
    )

    for token_match in token_re.finditer(page_html, start_index):
        token = token_match.group(0)
        if token.startswith("</"):
            depth -= 1
        else:
            depth += 1

        if depth == 0:
            return page_html[start_index : token_match.start()]

    return None


def convert_anthropic_html_to_markdown(
    article_html: str,
    *,
    base_url: str,
    title: str | None = None,
    description: str | None = None,
) -> str:
    cleaned_html, footnote_html_blocks = preprocess_anthropic_article_html(article_html)
    parser = MarkdownArticleParser(base_url)
    parser.feed(cleaned_html)
    link_context = build_anthropic_link_context(
        base_url=base_url,
        heading_ids_to_anchors=parser.heading_ids_to_anchors,
    )
    body_markdown = parser.to_markdown()
    body_markdown = rewrite_same_entry_links(body_markdown, link_context).strip()
    if footnote_html_blocks:
        body_markdown = apply_anthropic_footnotes(
            body_markdown,
            footnote_html_blocks=footnote_html_blocks,
            base_url=base_url,
            heading_ids_to_anchors=parser.heading_ids_to_anchors,
        )

    parts: list[str] = []
    if title:
        parts.append(f"# {title}")
    if description:
        parts.append(description)
    if body_markdown:
        parts.append(body_markdown)

    return "\n\n".join(parts).strip() + "\n"


def preprocess_anthropic_article_html(article_html: str) -> tuple[str, list[str]]:
    cleaned_html = D_CONTENTS_RE.sub("", article_html)
    cleaned_html = rewrite_anthropic_quote_blocks(cleaned_html)
    return extract_anthropic_footnotes(cleaned_html)


def extract_anthropic_footnotes(article_html: str) -> tuple[str, list[str]]:
    footnotes: list[str] = []

    def replace_footnote(match: re.Match[str]) -> str:
        footnotes.append(match.group("body"))
        number = len(footnotes)
        return FOOTNOTE_TOKEN_TEMPLATE.format(number=number)

    rewritten = D_FOOTNOTE_RE.sub(replace_footnote, article_html)
    return rewritten, footnotes


def rewrite_anthropic_quote_blocks(article_html: str) -> str:
    def replace_ha_block(match: re.Match[str]) -> str:
        body = BR_TAG_RE.sub("", match.group("body"))
        return f"<blockquote>{body}</blockquote>"

    return D_HA_BLOCK_RE.sub(replace_ha_block, article_html)


def apply_anthropic_footnotes(
    markdown: str,
    *,
    footnote_html_blocks: list[str],
    base_url: str,
    heading_ids_to_anchors: dict[str, str],
) -> str:
    rewritten = markdown
    rendered_footnotes: list[str] = []

    for number, footnote_html in enumerate(footnote_html_blocks, start=1):
        token = FOOTNOTE_TOKEN_TEMPLATE.format(number=number)
        rewritten = rewritten.replace(token, f"[^{number}]")
        rendered_footnotes.extend(
            render_anthropic_footnote(
                number,
                convert_anthropic_footnote_html_to_markdown(
                    footnote_html,
                    base_url=base_url,
                    heading_ids_to_anchors=heading_ids_to_anchors,
                ),
            )
        )

    if rendered_footnotes:
        rewritten = rewritten.rstrip() + "\n\n" + "\n".join(rendered_footnotes)

    return rewritten.strip() + "\n"


def build_anthropic_link_context(
    *,
    base_url: str,
    heading_ids_to_anchors: dict[str, str],
) -> SepLinkContext:
    return SepLinkContext(
        entry_url=base_url,
        heading_ids_to_anchors=heading_ids_to_anchors,
    )


def convert_anthropic_footnote_html_to_markdown(
    footnote_html: str,
    *,
    base_url: str,
    heading_ids_to_anchors: dict[str, str],
) -> str:
    parser = MarkdownArticleParser(base_url)
    parser.feed(footnote_html)
    footnote_markdown = parser.to_markdown().strip()
    link_context = build_anthropic_link_context(
        base_url=base_url,
        heading_ids_to_anchors=heading_ids_to_anchors,
    )
    return rewrite_same_entry_links(footnote_markdown, link_context).strip()


def render_anthropic_footnote(number: int, body_markdown: str) -> list[str]:
    lines = [line.rstrip() for line in body_markdown.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines:
        return [f"[^{number}]: [Missing footnote text]"]

    if len(lines) == 1:
        return [f"[^{number}]: {lines[0]}"]

    rendered = [f"[^{number}]: {lines[0]}"]
    for line in lines[1:]:
        if line.strip():
            rendered.append(f"    {line}")
        else:
            rendered.append("")
    return rendered
