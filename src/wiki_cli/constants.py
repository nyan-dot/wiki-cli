from __future__ import annotations

INDEX_MARKER_START = "<!-- SOURCES:START -->"
INDEX_MARKER_END = "<!-- SOURCES:END -->"
ALLOWED_STATUSES = {"seed", "expanded", "bridge", "needs-review"}
SECTION_TYPES = {
    "sources": "source",
    "concepts": "concept",
    "people": "person",
    "questions": "question",
}
