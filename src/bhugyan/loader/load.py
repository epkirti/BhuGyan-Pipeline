"""Step 5 — Load. One transaction per item:
INSERT content_unit -> place_content links -> content_tags
-> content_translation (if locale != en) -> invalidate Redis cache.
"""
from __future__ import annotations

import json

import asyncpg

from .dedupe import _to_pgvector
from .schema import NormalizedItem


async def insert_item(conn: asyncpg.Connection, item: NormalizedItem,
                      embedding: list[float], resolved: list[dict]) -> int:
    """Insert one fully-resolved item inside a transaction. Returns content_unit id."""
    async with conn.transaction():
        cu_id = await conn.fetchval(
            """
            INSERT INTO content_units
                (body, unit_type, subject, difficulty, depth_levels, locale,
                 status, source_pipeline, payload, embedding)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::vector)
            RETURNING id
            """,
            item.body, item.unit_type, item.subject, item.difficulty,
            item.depth_levels, "en" if item.locale != "en" else item.locale,
            item.status, item.source_pipeline, json.dumps(item.payload),
            _to_pgvector(embedding),
        )

        for r in resolved:
            await conn.execute(
                "INSERT INTO place_content (content_unit_id, place_id, relevance) "
                "VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
                cu_id, r["place_id"], r["relevance"],
            )

        for tag_type, tag_value in item.tag_pairs():
            await conn.execute(
                "INSERT INTO content_tags (content_unit_id, tag_type, tag_value) "
                "VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
                cu_id, tag_type, tag_value,
            )

        if item.locale != "en":
            await conn.execute(
                "INSERT INTO content_translation (content_unit_id, locale, body) "
                "VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
                cu_id, item.locale, item.body,
            )

    return cu_id


async def invalidate_cache(place_ids: list[int]) -> int:
    """Invalidate Redis place-content cache. No-op if Redis unavailable."""
    if not place_ids:
        return 0
    try:
        import redis.asyncio as aioredis

        from ..config import settings

        r = aioredis.from_url(settings.redis_url)
        keys = [f"place:{pid}:content" for pid in place_ids]
        await r.delete(*keys)
        await r.aclose()
        return len(keys)
    except Exception:
        return 0
