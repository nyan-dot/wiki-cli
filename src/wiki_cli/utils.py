from __future__ import annotations

import html
import os
import re
from pathlib import Path


def normalize_inline(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "sep-entry"


def markdown_heading_anchor(value: str) -> str:
    value = html.unescape(value).strip().lower()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-") or "section"


def title_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def write_text(path: Path, content: str, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists. Use --force to overwrite it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def relative_markdown_path(from_path: Path, to_path: Path) -> str:
    return Path(os.path.relpath(to_path, start=from_path.parent)).as_posix()


def yaml_list(values: list[str]) -> str:
    if not values:
        return "  - Unknown"
    return "\n".join(f'  - "{escape_quotes(value)}"' for value in values)


def escape_quotes(value: str) -> str:
    return value.replace('"', '\\"')


def parse_frontmatter(text: str) -> dict[str, object]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("Missing YAML frontmatter opening delimiter.")

    frontmatter: dict[str, object] = {}
    current_list_key: str | None = None

    for line in lines[1:]:
        if line.strip() == "---":
            return frontmatter

        key_match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if key_match:
            key = key_match.group(1)
            raw_value = key_match.group(2).strip()
            if raw_value:
                frontmatter[key] = strip_yaml_string(raw_value)
                current_list_key = None
            else:
                frontmatter[key] = []
                current_list_key = key
            continue

        list_match = re.match(r"^\s*-\s*(.*)$", line)
        if list_match and current_list_key:
            values = frontmatter.setdefault(current_list_key, [])
            if isinstance(values, list):
                values.append(strip_yaml_string(list_match.group(1).strip()))
            continue

        current_list_key = None

    raise ValueError("Missing YAML frontmatter closing delimiter.")


def strip_yaml_string(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def frontmatter_list(frontmatter: dict[str, object], key: str) -> list[str]:
    value = frontmatter.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def normalize_tag(tag: str) -> str:
    normalized = tag.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-")
