"""P1: Places — the spine. Loads place nodes from open geodata and generates
the graph edges (borders / contains / flows_to) via PostGIS spatial queries.

Source: any file GeoPandas can read (.geojson, .shp, ...). Defaults to the
bundled sample so the pipeline is runnable out of the box. Autopublished
(trusted open data), per the report.

Steps (all reported live):
  1. Read source            (GeoPandas)
  2. Normalize places       (slug, names, hierarchy, geometry -> WKT)
  3. Load places            (upsert into places, wire parent_id)
  4. Generate graph edges   (ST_Contains / ST_Touches / ST_Intersects)
  5. Enrich Hindi names     (count name_hi coverage)
"""
from __future__ import annotations

import re
from pathlib import Path

from ..config import PROJECT_ROOT
from .base import Pipeline

DEFAULT_SOURCE = PROJECT_ROOT / "data" / "sample" / "places.geojson"


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "place"


def _clean(value):
    """GeoPandas turns JSON null into float NaN; coerce that back to None."""
    import pandas as pd

    if value is None:
        return None
    try:
        if isinstance(value, float) and pd.isna(value):
            return None
    except Exception:
        pass
    return value


class PlacesPipeline(Pipeline):
    id = "p1"
    label = "Places"

    async def run(self) -> dict:
        source = Path(self.opts.get("source") or DEFAULT_SOURCE)
        run = self.new_run(meta={"source": str(source), "autopublish": "yes (trusted open data)"})

        # ---- Step 1: Read source ----
        with run.step("Step 1 — Read source (GeoPandas)") as st:
            import geopandas as gpd

            gdf = gpd.read_file(source)
            if gdf.crs is not None and str(gdf.crs).upper() not in ("EPSG:4326",):
                gdf = gdf.to_crs(4326)
            st.set_in(len(gdf))
            st.ok(len(gdf))
            st.note(f"geometry types: {sorted(gdf.geom_type.unique())}")

        # ---- Step 2: Normalize ----
        with run.step("Step 2 — Normalize places", total_in=len(gdf)) as st:
            records = []
            for _, row in gdf.iterrows():
                name = _clean(row.get("name"))
                geom = row.geometry
                if not name or geom is None or geom.is_empty:
                    st.skip("missing name/geometry")
                    continue
                records.append({
                    "slug": slugify(name),
                    "name": name,
                    "name_hi": _clean(row.get("name_hi")),
                    "place_type": _clean(row.get("place_type")) or "place",
                    "parent_slug": _clean(row.get("parent_slug")),
                    "source": _clean(row.get("source")),
                    "wkt": geom.wkt,
                })
                st.ok()

        # ---- Step 3: Load places ----
        with run.step("Step 3 — Load places", total_in=len(records)) as st:
            for rec in records:
                await self.conn.execute(
                    """
                    INSERT INTO places (slug, name, name_hi, place_type, source, geom, centroid)
                    VALUES ($1,$2,$3,$4,$5,
                            ST_SetSRID(ST_GeomFromText($6),4326),
                            ST_Centroid(ST_SetSRID(ST_GeomFromText($6),4326)))
                    ON CONFLICT (slug) DO UPDATE SET
                        name=EXCLUDED.name, name_hi=EXCLUDED.name_hi,
                        place_type=EXCLUDED.place_type, source=EXCLUDED.source,
                        geom=EXCLUDED.geom, centroid=EXCLUDED.centroid
                    """,
                    rec["slug"], rec["name"], rec["name_hi"], rec["place_type"],
                    rec["source"], rec["wkt"],
                )
                st.ok()
            # wire hierarchy now that all rows exist
            wired = 0
            for rec in records:
                if rec["parent_slug"]:
                    res = await self.conn.execute(
                        "UPDATE places SET parent_id=(SELECT id FROM places WHERE slug=$1) "
                        "WHERE slug=$2",
                        rec["parent_slug"], rec["slug"],
                    )
                    wired += 1
            st.note(f"hierarchy edges wired: {wired}")

        # ---- Step 4: Generate graph edges (PostGIS) ----
        with run.step("Step 4 — Generate graph edges (PostGIS)") as st:
            contains = await self.conn.execute(
                """
                INSERT INTO place_edges (source_place_id, target_place_id, edge_type)
                SELECT a.id, b.id, 'contains'
                FROM places a JOIN places b ON a.id <> b.id
                WHERE a.place_type IN ('country','state')
                  AND b.place_type IN ('state','district','city')
                  AND ST_Contains(a.geom, b.geom)
                ON CONFLICT DO NOTHING
                """
            )
            borders = await self.conn.execute(
                """
                INSERT INTO place_edges (source_place_id, target_place_id, edge_type)
                SELECT a.id, b.id, 'borders'
                FROM places a JOIN places b ON a.id <> b.id
                WHERE a.place_type='state' AND b.place_type='state'
                  AND ST_Touches(a.geom, b.geom)
                ON CONFLICT DO NOTHING
                """
            )
            flows = await self.conn.execute(
                """
                INSERT INTO place_edges (source_place_id, target_place_id, edge_type)
                SELECT r.id, s.id, 'flows_to'
                FROM places r JOIN places s ON r.id <> s.id
                WHERE r.place_type='river' AND s.place_type IN ('state')
                  AND ST_Intersects(r.geom, s.geom)
                ON CONFLICT DO NOTHING
                """
            )
            total_edges = await self.conn.fetchval("SELECT count(*) FROM place_edges")
            st.ok(total_edges)
            st.note(f"contains: {self._n(contains)}  borders: {self._n(borders)}  "
                    f"flows_to: {self._n(flows)}  (total in DB: {total_edges})")

        # ---- Step 5: Enrich Hindi names ----
        with run.step("Step 5 — Enrich Hindi names") as st:
            total = await self.conn.fetchval("SELECT count(*) FROM places")
            with_hi = await self.conn.fetchval(
                "SELECT count(*) FROM places WHERE name_hi IS NOT NULL")
            st.set_in(total)
            st.ok(with_hi)
            st.note(f"Hindi coverage: {with_hi}/{total} "
                    f"(missing names would be fetched from Wikidata)")

        n_places = await self.conn.fetchval("SELECT count(*) FROM places")
        n_edges = await self.conn.fetchval("SELECT count(*) FROM place_edges")
        return run.finish(extra={"places_in_db": n_places, "edges_in_db": n_edges})

    @staticmethod
    def _n(execute_result) -> str:
        # asyncpg execute() returns e.g. "INSERT 0 3"
        if isinstance(execute_result, str):
            parts = execute_result.split()
            return parts[-1] if parts else "?"
        return str(execute_result)
