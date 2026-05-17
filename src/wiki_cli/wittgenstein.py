from __future__ import annotations

import html
import re
import urllib.parse
from datetime import UTC, datetime
from html.parser import HTMLParser

from .models import SourceEntry
from .sep import MarkdownArticleParser, collapse_blank_lines
from .sep import fetch_url as sep_fetch_url
from .utils import normalize_inline, slugify

WITTGENSTEIN_WRITINGS_HOSTS = {
    "wittgensteinnachlass.com",
    "www.wittgensteinnachlass.com",
}
WITTGENSTEIN_BASE_URL = "https://wittgensteinnachlass.com"
WITTGENSTEIN_EDITION = "Wittgenstein's Writings"
WITTGENSTEIN_LICENSE_NOTE = (
    "Wittgenstein's Nachlass is public domain in life+70 jurisdictions; "
    "site text is CC0; graphics are mostly CC BY 4.0."
)
UNIT_CHOICES = {"auto", "page", "document", "collection", "index"}
LIGHTBOX_DIV_RE = re.compile(
    r"<div\b(?P<attrs>[^>]*)class=(?P<quote>['\"])(?P<classname>[^'\"]*\blightbox\b[^'\"]*)(?P=quote)(?P<rest>[^>]*)>.*?</div>",
    re.IGNORECASE | re.DOTALL,
)
FRAGMENT_LINK_RE = re.compile(
    r"<a\b[^>]*class=(?P<quote>['\"])[^'\"]*\bfragment-link\b[^'\"]*(?P=quote)[^>]*>.*?</a>",
    re.IGNORECASE | re.DOTALL,
)
SECTION_RE = re.compile(
    r"<section\b[^>]*>\s*<h3\b(?P<attrs>[^>]*)>.*?</section>",
    re.IGNORECASE | re.DOTALL,
)
ID_ATTR_RE = re.compile(
    r"\bid=(?P<quote>['\"])(?P<id>[^'\"]+)(?P=quote)",
    re.IGNORECASE,
)


class WittgensteinTitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self._inside_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "title":
            self._inside_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title_parts.append(data)


def normalize_wittgenstein_target(target: str) -> tuple[str, str, str]:
    cleaned = target.strip()
    if not cleaned:
        raise ValueError("Missing Wittgenstein target URL or page ID.")

    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme or parsed.netloc:
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.netloc not in WITTGENSTEIN_WRITINGS_HOSTS
        ):
            raise ValueError(
                "Wittgenstein imports currently require "
                "`https://wittgensteinnachlass.com/...` URLs or page IDs."
            )
        path_slug = page_slug_from_path(parsed.path)
    else:
        path_slug = cleaned.strip("/").casefold()
        if not path_slug:
            path_slug = "home"

    path = "/" if path_slug == "home" else f"/{path_slug}/"
    canonical_url = urllib.parse.urlunparse(
        ("https", "wittgensteinnachlass.com", path, "", "", "")
    )
    return canonical_url, path_slug, infer_wittgenstein_unit(path_slug)


def page_slug_from_path(path: str) -> str:
    path_slug = path.strip("/")
    if not path_slug:
        return "home"
    return path_slug.casefold()


def infer_wittgenstein_unit(page_slug: str) -> str:
    if page_slug in {"docs-by-name", "docs-by-date", "home"}:
        return "index"
    if re.match(r"^(?:ms|ts)-", page_slug):
        return "document"
    if re.match(r"^w-", page_slug):
        return "collection"
    return "page"


def fetch_url(url: str) -> str:
    return sep_fetch_url(url)


def parse_wittgenstein_entry(
    url: str,
    page_html: str,
    *,
    slug: str | None = None,
    unit: str = "auto",
    start: str | None = None,
    end: str | None = None,
) -> SourceEntry:
    if unit not in UNIT_CHOICES:
        raise ValueError(
            "Wittgenstein import unit must be one of: "
            + ", ".join(sorted(UNIT_CHOICES))
        )

    _, page_slug, inferred_unit = normalize_wittgenstein_target(url)
    resolved_unit = inferred_unit if unit == "auto" else unit
    title = parse_title(page_html)
    reference_range = format_reference_range(start, end)
    derived_slug = slug or derive_entry_slug(page_slug, reference_range)

    pubinfo = f"{WITTGENSTEIN_EDITION} {resolved_unit}"
    if reference_range:
        pubinfo = f"{pubinfo}; range {reference_range}"

    return SourceEntry(
        source_type="wittgenstein",
        slug=derived_slug,
        title=title,
        url=url,
        authors=["Ludwig Wittgenstein"],
        first_published=None,
        pubinfo=pubinfo,
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        abstract=(
            "Readable transcription from Wittgenstein's Writings; "
            "not a diplomatic edition of the Nachlass."
        ),
        canonical_id=page_slug,
        source_unit=resolved_unit,
        reference_range=reference_range,
        edition=WITTGENSTEIN_EDITION,
        license_note=WITTGENSTEIN_LICENSE_NOTE,
    )


def parse_title(page_html: str) -> str:
    parser = WittgensteinTitleParser()
    parser.feed(page_html)
    raw_title = normalize_inline(html.unescape("".join(parser.title_parts)))
    title = re.sub(
        r"\s*[\u2013-]\s*Wittgenstein(?:'|&#39;|\u2019)s Writings\s*$",
        "",
        raw_title,
    ).strip()
    return title or "Wittgenstein's Writings"


def format_reference_range(start: str | None, end: str | None) -> str | None:
    if start and end:
        return f"{start}..{end}"
    return start or end


def derive_entry_slug(page_slug: str, reference_range: str | None) -> str:
    if not reference_range:
        return slugify(page_slug)
    range_slug = slugify(reference_range.replace("..", "-to-"))
    return f"{slugify(page_slug)}-{range_slug}"


def extract_wittgenstein_main_html(page_html: str) -> str:
    article_html = extract_tag_inner_html(page_html, "main")
    if article_html is None:
        raise ValueError("Could not locate the Wittgenstein page body in the HTML.")
    return article_html


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
            return page_html[start_index:token_match.start()]

    return None


def convert_wittgenstein_html_to_markdown(
    article_html: str,
    *,
    base_url: str,
    start: str | None = None,
    end: str | None = None,
) -> str:
    cleaned_html = preprocess_wittgenstein_html(article_html)
    selected_html = select_section_range(cleaned_html, start=start, end=end)
    parser = MarkdownArticleParser(base_url)
    parser.feed(selected_html)
    markdown = parser.to_markdown()
    return postprocess_wittgenstein_markdown(markdown)


def preprocess_wittgenstein_html(article_html: str) -> str:
    without_lightboxes = LIGHTBOX_DIV_RE.sub("", article_html)
    return FRAGMENT_LINK_RE.sub("", without_lightboxes)


def select_section_range(
    article_html: str,
    *,
    start: str | None,
    end: str | None,
) -> str:
    if start is None and end is None:
        return article_html

    sections = list(iter_h3_sections(article_html))
    if not sections:
        raise ValueError("This Wittgenstein page has no selectable remark sections.")

    start_index = 0 if start is None else section_index_for_id(sections, start, "start")
    end_index = (
        len(sections) - 1 if end is None else section_index_for_id(sections, end, "end")
    )
    if end_index < start_index:
        raise ValueError("Wittgenstein range end must not come before range start.")

    first_start = sections[0][1]
    header_html = article_html[:first_start]
    selected_sections = "".join(
        section_html for _, _, _, section_html in sections[start_index : end_index + 1]
    )
    return header_html + selected_sections


def iter_h3_sections(article_html: str) -> list[tuple[str, int, int, str]]:
    sections: list[tuple[str, int, int, str]] = []
    for match in SECTION_RE.finditer(article_html):
        section_id = section_id_from_attrs(match.group("attrs"))
        if not section_id:
            continue
        sections.append((section_id, match.start(), match.end(), match.group(0)))
    return sections


def section_id_from_attrs(attrs: str) -> str | None:
    match = ID_ATTR_RE.search(attrs)
    if match is None:
        return None
    return html.unescape(match.group("id"))


def section_index_for_id(
    sections: list[tuple[str, int, int, str]],
    section_id: str,
    label: str,
) -> int:
    for index, (current_id, _, _, _) in enumerate(sections):
        if current_id == section_id:
            return index
    available = ", ".join(current_id for current_id, _, _, _ in sections[:5])
    suffix = ", ..." if len(sections) > 5 else ""
    raise ValueError(
        f"Could not find Wittgenstein {label} section `{section_id}`. "
        f"First available section ids: {available}{suffix}"
    )


def postprocess_wittgenstein_markdown(markdown: str) -> str:
    lines = []
    for line in markdown.splitlines():
        cleaned = line.replace("[\u00a7]", "")
        cleaned = re.sub(r"\(\s*#_?\s*\)", "", cleaned)
        lines.append(cleaned.rstrip())
    return collapse_blank_lines(lines)
