"""Async Postgres access via asyncpg, plus a tiny migration runner."""
from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from .config import PROJECT_ROOT, settings

MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def _dsn() -> str:
    # asyncpg wants postgresql:// (not postgresql+asyncpg://)
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


async def connect() -> asyncpg.Connection:
    return await asyncpg.connect(_dsn())


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(_dsn(), min_size=1, max_size=8)


async def run_migrations() -> list[str]:
    """Apply every .sql file in migrations/ in lexical order (idempotent SQL)."""
    applied: list[str] = []
    conn = await connect()
    try:
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            await conn.execute(sql_file.read_text(encoding="utf-8"))
            applied.append(sql_file.name)
    finally:
        await conn.close()
    return applied


async def ping() -> bool:
    try:
        conn = await connect()
    except Exception:
        return False
    try:
        return (await conn.fetchval("SELECT 1")) == 1
    finally:
        await conn.close()


if __name__ == "__main__":
    print("Applied:", asyncio.run(run_migrations()))
