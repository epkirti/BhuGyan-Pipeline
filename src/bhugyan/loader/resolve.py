"""Step 4 — Resolve place names to place_ids via rapidfuzz fuzzy matching.

The first mentioned place gets relevance=1.0 (primary); the rest get 0.5.
Names that don't clear the score cutoff are returned as unresolved (logged for
manual review, never silently dropped).
"""
from __future__ import annotations

import asyncpg
from rapidfuzz import fuzz, process

from ..config import settings


class PlaceIndex:
    """In-memory name -> place_id index, loaded once per run."""

    def __init__(self, rows: list[asyncpg.Record]):
        # map of candidate string -> place_id (include name and name_hi)
        self.choices: dict[str, int] = {}
        for r in rows:
            self.choices[r["name"]] = r["id"]
            if r["name_hi"]:
                self.choices[r["name_hi"]] = r["id"]
        self._keys = list(self.choices.keys())

    @classmethod
    async def load(cls, conn: asyncpg.Connection) -> "PlaceIndex":
        rows = await conn.fetch("SELECT id, name, name_hi FROM places")
        return cls(rows)

    def match(self, name: str) -> tuple[int | None, float, str | None]:
        """Return (place_id|None, score, matched_name|None)."""
        if not self._keys:
            return None, 0.0, None
        best = process.extractOne(name, self._keys, scorer=fuzz.WRatio)
        if best is None:
            return None, 0.0, None
        matched_name, score, _ = best
        if score >= settings.place_resolve_score_cutoff:
            return self.choices[matched_name], float(score), matched_name
        return None, float(score), matched_name


def resolve_places(index: PlaceIndex, place_names: list[str]):
    """Return (resolved, unresolved).

    resolved: list of {place_id, relevance, name, matched, score}
    unresolved: list of {name, best_score, best_match}
    """
    resolved: list[dict] = []
    unresolved: list[dict] = []
    seen_ids: set[int] = set()
    for i, name in enumerate(place_names):
        pid, score, matched = index.match(name)
        if pid is None:
            unresolved.append({"name": name, "best_score": score, "best_match": matched})
            continue
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        resolved.append({
            "place_id": pid,
            "relevance": 1.0 if i == 0 else 0.5,
            "name": name,
            "matched": matched,
            "score": score,
        })
    return resolved, unresolved
