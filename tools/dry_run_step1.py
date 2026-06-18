"""Dry-run Step 1 (Extract/Normalize) for each pipeline — NO DB, NO network.

Purpose: confirm that each pipeline's *input format* (the bundled samples) maps
cleanly onto the **standard output format** before testing the full pipeline:
  - P2/P3/P4  -> NormalizedItem  (the shape the common loader consumes)
  - P1        -> place records   (slug/name/geom rows)
  - P5        -> media files     (no NormalizedItem)

It reuses the real extractor code where possible, then runs the real Step-2
`validate_item` gate so you can see, per item, whether it is loader-ready.

    python tools/dry_run_step1.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows consoles default to cp1252 and choke on Devanagari / box glyphs.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Make `src/` importable when run straight from the repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bhugyan.loader.schema import NormalizedItem          # noqa: E402
from bhugyan.loader.validate import validate_item         # noqa: E402
from bhugyan.observability.reporter import StepReport      # noqa: E402

BAR = "=" * 70


def _show_item(i: int, item: NormalizedItem) -> None:
    reason = validate_item(item)
    verdict = "OK (loader-ready)" if reason is None else f"WOULD SKIP -> {reason}"
    print(f"\n  [{i}] {verdict}")
    print("      " + json.dumps(item.model_dump(), ensure_ascii=False))


def dry_run_p2_csv() -> None:
    print(f"\n{BAR}\nP2 Content — input: CSV  ->  output: NormalizedItem\n{BAR}")
    from bhugyan.pipelines.p2_content import ContentPipeline, DEFAULT_CSV

    pipe = ContentPipeline(conn=None)        # _extract_csv never touches the DB
    st = StepReport(name="Step 1 — Extract")
    items = pipe._extract_csv(st)

    print(f"source: {DEFAULT_CSV}")
    print(f"rows extracted -> {len(items)} NormalizedItem(s)")
    for i, item in enumerate(items, 1):
        _show_item(i, item)

    ready = sum(1 for it in items if validate_item(it) is None)
    print(f"\n  => {ready}/{len(items)} would pass Step 2 (Validate)")


def dry_run_p1_geojson() -> None:
    print(f"\n{BAR}\nP1 Places — input: GeoJSON  ->  output: place records\n{BAR}")
    try:
        import geopandas as gpd
    except Exception as e:                   # geopandas optional in this env
        print(f"  (skipped — geopandas not importable: {type(e).__name__}: {e})")
        return

    from bhugyan.pipelines.p1_places import DEFAULT_SOURCE, _clean, slugify

    gdf = gpd.read_file(DEFAULT_SOURCE)
    if gdf.crs is not None and str(gdf.crs).upper() not in ("EPSG:4326",):
        gdf = gdf.to_crs(4326)

    print(f"source: {DEFAULT_SOURCE}")
    print(f"features read -> {len(gdf)}   geom types: {sorted(gdf.geom_type.unique())}")

    records, skipped = [], 0
    for _, row in gdf.iterrows():
        name = _clean(row.get("name"))
        geom = row.geometry
        if not name or geom is None or geom.is_empty:
            skipped += 1
            continue
        records.append({
            "slug": slugify(name),
            "name": name,
            "name_hi": _clean(row.get("name_hi")),
            "place_type": _clean(row.get("place_type")) or "place",
            "parent_slug": _clean(row.get("parent_slug")),
            "source": _clean(row.get("source")),
            "wkt": geom.wkt[:60] + ("…" if len(geom.wkt) > 60 else ""),
        })

    print(f"normalized -> {len(records)} place record(s), {skipped} skipped")
    for i, rec in enumerate(records, 1):
        print(f"\n  [{i}] {json.dumps(rec, ensure_ascii=False)}")


def note_db_pipelines() -> None:
    print(f"\n{BAR}\nNot dry-runnable from samples (need DB / network)\n{BAR}")
    print("  P3 Questions       — input is the DB (places/facts), not a file.")
    print("  P4 Current Affairs — input is live RSS feeds (network required).")
    print("  P5 Media           — reads PostGIS geometry, emits files (no NormalizedItem).")
    print("  Verify these in the full-run pass once Postgres is up.")


if __name__ == "__main__":
    dry_run_p2_csv()
    dry_run_p1_geojson()
    note_db_pipelines()
    print()
