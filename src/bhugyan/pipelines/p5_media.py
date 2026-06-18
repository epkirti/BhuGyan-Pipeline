"""P5: Media — derived assets from PostGIS geometry.

  - PMTiles via Tippecanoe (external binary; skeleton if not installed).
  - Highlight PNGs via Matplotlib + GeoPandas — fully working.
  - Offline ZIP packs bundling tiles + images — fully working.

Does not use the common loader (it emits files, not content_units).
Autopublished, per the report.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from ..config import PROJECT_ROOT
from .base import Pipeline

OUTPUT_DIR = PROJECT_ROOT / "output" / "media"


class MediaPipeline(Pipeline):
    id = "p5"
    label = "Media"

    async def run(self) -> dict:
        out = Path(self.opts.get("out") or OUTPUT_DIR)
        out.mkdir(parents=True, exist_ok=True)
        run = self.new_run(meta={"output": str(out), "autopublish": "yes (automated)"})

        # ---- Step 1: Export geometry from PostGIS ----
        with run.step("Step 1 — Export geometry (PostGIS -> GeoJSON)") as st:
            rows = await self.conn.fetch(
                "SELECT slug, name, place_type, ST_AsGeoJSON(geom) AS gj FROM places")
            features = [{
                "type": "Feature",
                "properties": {"slug": r["slug"], "name": r["name"],
                               "place_type": r["place_type"]},
                "geometry": json.loads(r["gj"]) if r["gj"] else None,
            } for r in rows if r["gj"]]
            geojson = {"type": "FeatureCollection", "features": features}
            gj_path = out / "places.geojson"
            gj_path.write_text(json.dumps(geojson), encoding="utf-8")
            st.set_in(len(rows))
            st.ok(len(features))
            st.note(f"exported {len(features)} features -> {gj_path.name}")

        # ---- Step 2: PMTiles via Tippecanoe ----
        with run.step("Step 2 — Generate PMTiles (Tippecanoe)") as st:
            pmtiles = out / "places.pmtiles"
            if shutil.which("tippecanoe"):
                subprocess.run(
                    ["tippecanoe", "-o", str(pmtiles), "--force",
                     "-zg", "--drop-densest-as-needed", str(gj_path)],
                    check=True,
                )
                st.ok()
                st.note(f"PMTiles written -> {pmtiles.name}")
            else:
                st.skip("tippecanoe not installed")
                st.note("install tippecanoe to emit PMTiles (served via HTTP range)")

        # ---- Step 3: Highlight PNGs (Matplotlib + GeoPandas) ----
        with run.step("Step 3 — Render highlight PNGs") as st:
            img_dir = out / "highlights"
            img_dir.mkdir(exist_ok=True)
            try:
                import geopandas as gpd
                import matplotlib

                matplotlib.use("Agg")
                import matplotlib.pyplot as plt

                gdf = gpd.read_file(gj_path)
                targets = gdf[gdf["place_type"].isin(["state", "country"])]
                for _, feat in targets.iterrows():
                    fig, ax = plt.subplots(figsize=(4, 4))
                    gdf.plot(ax=ax, color="#e8e8e8", edgecolor="white")
                    gpd.GeoDataFrame([feat], crs=gdf.crs).plot(
                        ax=ax, color="#ff6b35", edgecolor="black")
                    ax.set_axis_off()
                    fig.savefig(img_dir / f"{feat['slug']}.png", dpi=80,
                                bbox_inches="tight")
                    plt.close(fig)
                    st.ok()
                st.note(f"rendered {st.passed} highlight PNGs -> {img_dir.name}/")
            except Exception as e:
                st.skip(f"render unavailable ({type(e).__name__})")
                st.note("needs matplotlib + geopandas installed")

        # ---- Step 4: Offline ZIP pack ----
        with run.step("Step 4 — Build offline ZIP pack") as st:
            pack = out / "offline_pack.zip"
            with zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in out.rglob("*"):
                    if p.is_file() and p != pack:
                        zf.write(p, p.relative_to(out))
            size_kb = pack.stat().st_size / 1024
            st.ok()
            st.note(f"offline pack -> {pack.name} ({size_kb:.0f} KB)")

        return run.finish(extra={"output_dir": str(out)})
