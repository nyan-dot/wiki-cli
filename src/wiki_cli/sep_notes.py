from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from .utils import normalize_inline


SEP_LEADING_NOTE_BACKLINK_RE = re.compile(r"^\[(?P<label>\d+\.)\]\([^)]+\)\s*")


@dataclass
class SepFootnoteBlock:
    number: int
    note_id: str
    body_lines: list[str]


class SepNotesParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.note_html_by_id: dict[str, str] = {}
        self._captured_note_id: str | None = None
        self._captured_parts: list[str] | None = None
        self._div_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if self._captured_parts is None:
            if tag == "div":
                note_id = attr_map.get("id", "").strip()
                if note_id.startswith("note-"):
                    self._captured_note_id = note_id
                    self._captured_parts = []
                    self._div_depth = 1
            return

        if tag == "div":
            self._div_depth += 1
        self._captured_parts.append(serialize_starttag(tag, attrs))

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if self._captured_parts is None:
            return
        self._captured_parts.append(serialize_startendtag(tag, attrs))

    def handle_endtag(self, tag: str) -> None:
        if self._captured_parts is None:
            return

        if tag == "div":
            self._div_depth -= 1
            if self._div_depth == 0:
                if self._captured_note_id is not None:
                    self.note_html_by_id[self._captured_note_id] = "".join(
                        self._captured_parts
                    )
                self._captured_note_id = None
                self._captured_parts = None
                return

        self._captured_parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._captured_parts is None:
            return
        self._captured_parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if self._captured_parts is None:
            return
        self._captured_parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._captured_parts is None:
            return
        self._captured_parts.append(f"&#{name};")


def serialize_starttag(tag: str, attrs: list[tuple[str, str | None]]) -> str:
    if not attrs:
        return f"<{tag}>"
    serialized_attrs = " ".join(
        f'{key}="{html.escape(value or "", quote=True)}"' for key, value in attrs
    )
    return f"<{tag} {serialized_attrs}>"


def serialize_startendtag(tag: str, attrs: list[tuple[str, str | None]]) -> str:
    if not attrs:
        return f"<{tag} />"
    serialized_attrs = " ".join(
        f'{key}="{html.escape(value or "", quote=True)}"' for key, value in attrs
    )
    return f"<{tag} {serialized_attrs} />"


def footnote_number_from_note_id(note_id: str) -> int | None:
    match = re.fullmatch(r"note-(\d+)", note_id)
    if match is None:
        return None
    return int(match.group(1))


def strip_sep_note_backlink(markdown: str) -> str:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        lines[index] = SEP_LEADING_NOTE_BACKLINK_RE.sub("", line).strip()
        break
    return "\n".join(lines)


def render_sep_footnotes(footnotes: list[SepFootnoteBlock]) -> list[str]:
    rendered: list[str] = []
    for footnote in footnotes:
        rendered.extend(render_sep_footnote(footnote))
    return rendered


def render_sep_footnote(footnote: SepFootnoteBlock) -> list[str]:
    if len(footnote.body_lines) == 1:
        return [f"[^{footnote.number}]: {footnote.body_lines[0].strip()}"]

    formatted = [f"[^{footnote.number}]:"]
    for line in footnote.body_lines:
        if not line.strip():
            formatted.append("")
        else:
            formatted.append(f"    {line}")
    return formatted


def format_sep_note_cross_reference(label: str, note_number: int) -> str:
    stripped = normalize_inline(label)
    lowered = stripped.lower()
    if stripped in {str(note_number), f"{note_number}."}:
        return f"[^{note_number}]"
    if lowered in {f"note {note_number}", f"note {note_number}."}:
        return f"note [^{note_number}]"
    if lowered in {f"notes {note_number}", f"notes {note_number}."}:
        return f"notes [^{note_number}]"
    return f"{stripped} [^{note_number}]"


def trim_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)

    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1

    return lines[start:end]
