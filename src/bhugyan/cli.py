"""BhuGyan pipeline CLI.

    python -m bhugyan migrate                 # apply SQL migrations
    python -m bhugyan status                  # DB connectivity + row counts
    python -m bhugyan run p1 [--source PATH]  # Places (open geodata)
    python -m bhugyan run p2 [--mode csv|pdf] [--source PATH]
    python -m bhugyan run p3 [--mode drills|mcq|pyq]
    python -m bhugyan run p4                  # Current Affairs (RSS)
    python -m bhugyan run p5 [--out DIR]      # Media (tiles/images/packs)
    python -m bhugyan all                     # p1..p5 in build order
"""
from __future__ import annotations

import asyncio
import sys

import typer

# Windows consoles default to cp1252 and choke on ✓/✗/box glyphs.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from . import db
from .config import settings
from .pipelines import REGISTRY

app = typer.Typer(add_completion=False, help="BhuGyan data pipeline runner.")


@app.command()
def migrate():
    """Apply all SQL migrations (idempotent)."""
    applied = asyncio.run(db.run_migrations())
    typer.echo("Applied migrations: " + ", ".join(applied))


@app.command()
def status():
    """Check DB connectivity and show row counts."""
    asyncio.run(_status())


async def _status():
    if not await db.ping():
        typer.secho(f"✗ cannot reach DB at {settings.database_url}", fg="red")
        typer.echo("  Start it with:  docker compose up -d db")
        raise typer.Exit(1)
    conn = await db.connect()
    try:
        typer.secho("✓ DB reachable", fg="green")
        for tbl in ("places", "place_edges", "content_units",
                    "place_content", "content_tags"):
            try:
                n = await conn.fetchval(f"SELECT count(*) FROM {tbl}")
                typer.echo(f"  {tbl:<16} {n}")
            except Exception:
                typer.echo(f"  {tbl:<16} (missing — run `migrate`)")
    finally:
        await conn.close()


@app.command()
def run(
    pipeline: str = typer.Argument(..., help="p1|p2|p3|p4|p5"),
    source: str = typer.Option(None, help="input file (geojson/csv/pdf)"),
    mode: str = typer.Option(None, help="pipeline-specific mode"),
    out: str = typer.Option(None, help="output dir (p5)"),
    exam: str = typer.Option(None, help="exam tag, e.g. 'upsc' (p3 --mode qbank)"),
    year: str = typer.Option(None, help="exam year, e.g. '2021' (p3 --mode qbank)"),
    paper: str = typer.Option(None, help="paper id, e.g. 'map_based_questions' (p3 --mode qbank)"),
    qtype: str = typer.Option(None, help="question type: practice|pyq (p3 --mode qbank)"),
    map_only: bool = typer.Option(False, "--map-only", help="keep only questions about a place (p3 --mode qbank)"),
    chunk: int = typer.Option(None, help="pages per LLM call (PDF modes)"),
    pages: int = typer.Option(None, help="limit to first N pages (PDF modes)"),
):
    """Run one pipeline with live step-by-step visibility."""
    asyncio.run(_run_one(pipeline.lower(), source=source, mode=mode, out=out,
                         exam=exam, year=year, paper=paper, qtype=qtype,
                         map_only=map_only or None, chunk=chunk, pages=pages))


async def _run_one(pid: str, **opts):
    if pid not in REGISTRY:
        typer.secho(f"unknown pipeline '{pid}' (choose from {list(REGISTRY)})", fg="red")
        raise typer.Exit(1)
    opts = {k: v for k, v in opts.items() if v is not None}
    conn = await db.connect()
    try:
        pipe = REGISTRY[pid](conn, **opts)
        await pipe.run()
    finally:
        await conn.close()


@app.command()
def extract(
    source: str = typer.Option(..., help="input book PDF"),
    out: str = typer.Option("data/extracted/content.csv", help="output CSV path"),
    subject: str = typer.Option("geography", help="default subject"),
    exam: str = typer.Option(None, help="default exam tag(s), e.g. 'upsc|ssc'"),
    class_level: str = typer.Option(None, help="default class level, e.g. 'class_11'"),
    locale: str = typer.Option("en", help="default locale"),
    chunk: int = typer.Option(2, help="pages per LLM call"),
    pages: int = typer.Option(None, help="limit to first N pages (cheap test run)"),
):
    """Extract draft facts from a book PDF into a P2-ready CSV (review before loading)."""
    from .extract import pdf_to_csv

    def _split(v):
        return [p.strip() for p in v.replace(";", "|").split("|") if p.strip()] if v else []

    typer.secho(f"Extracting facts from {source} …", fg="cyan")
    summary = pdf_to_csv(
        source, out,
        subject=subject,
        exam_tags=_split(exam),
        class_levels=_split(class_level),
        locale=locale,
        pages_per_chunk=chunk,
        page_limit=pages,
        on_progress=lambda m: typer.echo(f"  · {m}"),
    )
    typer.secho(
        f"✓ {summary['facts_written']} facts -> {summary['csv']}  "
        f"(LLM: {summary['llm']})", fg="green")
    if summary["facts_without_place"]:
        typer.secho(
            f"  ⚠ {summary['facts_without_place']} fact(s) have NO place_names — "
            f"P2 will reject these; add places during review.", fg="yellow")
    typer.echo(f"  Review the CSV, then:  python -m bhugyan run p2 --source {out}")


@app.command()
def all():
    """Run P1..P5 in the report's build order."""
    asyncio.run(_run_all())


async def _run_all():
    conn = await db.connect()
    try:
        for pid in ("p1", "p2", "p3", "p5"):   # p4 needs network; run explicitly
            await REGISTRY[pid](conn).run()
    finally:
        await conn.close()


if __name__ == "__main__":
    app()
