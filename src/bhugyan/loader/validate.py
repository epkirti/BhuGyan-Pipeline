"""Step 2 — Validate. Pure, no DB. Returns (kept, [(item, reason)])."""
from __future__ import annotations

from .schema import NormalizedItem

VALID_SUBJECTS = {
    "geography", "history", "polity", "economy", "science",
    "environment", "culture", "current_affairs",
}
QUESTION_TYPES = {"mcq", "map_tap", "map_drag"}


def validate_item(item: NormalizedItem) -> str | None:
    """Return a skip-reason string if invalid, else None."""
    if not item.body or not item.body.strip():
        return "missing body"
    if not item.place_names:
        return "no place names"
    if item.subject not in VALID_SUBJECTS:
        return f"invalid subject '{item.subject}'"
    if item.unit_type in QUESTION_TYPES:
        opts = item.payload.get("options")
        ci = item.payload.get("correct_index")
        if not opts or not isinstance(opts, list) or len(opts) < 2:
            return "question missing options"
        if ci is None or not (0 <= int(ci) < len(opts)):
            return "question missing/invalid correct_index"
    return None
