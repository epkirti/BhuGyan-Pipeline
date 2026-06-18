"""Step 2 — Validate. Pure, no DB. Returns (kept, [(item, reason)])."""
from __future__ import annotations

from .schema import NormalizedItem

VALID_SUBJECTS = {
    "geography", "history", "polity", "economy", "science",
    "environment", "culture", "current_affairs",
    "general_studies",          # catch-all for cross-subject PYQs
}
QUESTION_TYPES = {"mcq", "map_tap", "map_drag"}


def validate_item(item: NormalizedItem) -> str | None:
    """Return a skip-reason string if invalid, else None."""
    if not item.body or not item.body.strip():
        return "missing body"
    # Place-first by default; PYQs (place_optional) may load without a place.
    if not item.place_names and not item.place_optional:
        return "no place names"
    if item.subject not in VALID_SUBJECTS:
        return f"invalid subject '{item.subject}'"
    if item.unit_type in QUESTION_TYPES:
        opts = item.payload.get("options")
        ci = item.payload.get("correct_index")
        if not opts or not isinstance(opts, list) or len(opts) < 2:
            return "question missing options"
        if ci is None:
            # An unanswered question is allowed only if flagged for human review
            # (PYQs without a detectable answer key) — never auto-published.
            if item.status != "pending_review":
                return "question missing correct_index"
        elif not (0 <= int(ci) < len(opts)):
            return "question invalid correct_index"
    return None
