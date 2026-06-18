"""Step 3 — Deduplicate via pgvector cosine similarity.

Each item's body is embedded and compared against (a) already-loaded
content_units in the DB and (b) items accepted earlier in this same batch.
If max cosine similarity >= threshold, the item is a duplicate and skipped.
"""
from __future__ import annotations

import asyncpg

from ..config import settings
from . import embeddings


def _to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def cosine(a: list[float], b: list[float]) -> float:
    # vectors are unit-norm from embed(); dot == cosine similarity
    return sum(x * y for x, y in zip(a, b))


async def nearest_existing(conn: asyncpg.Connection, vec: list[float]) -> float:
    """Highest cosine similarity vs anything already in content_units (0 if empty)."""
    row = await conn.fetchrow(
        "SELECT 1 - (embedding <=> $1::vector) AS sim "
        "FROM content_units WHERE embedding IS NOT NULL "
        "ORDER BY embedding <=> $1::vector LIMIT 1",
        _to_pgvector(vec),
    )
    return float(row["sim"]) if row and row["sim"] is not None else 0.0


async def check_duplicate(conn: asyncpg.Connection, vec: list[float],
                          batch_vecs: list[list[float]]) -> tuple[bool, float]:
    """Return (is_duplicate, max_similarity) against DB + this batch."""
    threshold = settings.dedupe_similarity_threshold
    sim_db = await nearest_existing(conn, vec)
    sim_batch = max((cosine(vec, bv) for bv in batch_vecs), default=0.0)
    sim = max(sim_db, sim_batch)
    return sim >= threshold, sim
