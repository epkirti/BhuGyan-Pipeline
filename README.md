# BhuGyan — Data Pipeline

Place-first learning content pipeline. **Five extraction pipelines** feed **one
common loader** that validates, deduplicates (pgvector), resolves place names
(rapidfuzz) and loads into Postgres/PostGIS/pgvector. Every step is **visible
live** in the console and persisted to `run_logs/`.

```
P1 Places ─┐
P2 Content ─┤
P3 Questions┤──►  COMMON LOADER  ──►  Postgres / PostGIS / pgvector
P4 Current ─┤      Step 2 Validate
P5 Media ───┘      Step 3 Deduplicate (pgvector cosine ≥ 0.95)
                   Step 4 Resolve places (rapidfuzz ≥ 85)
                   Step 5 Load (1 txn: content_unit + links + tags + cache bust)
```
(P1 and P5 write geometry/media directly; P2/P3/P4 flow through the loader.)

## What's built

| Component | Status |
|---|---|
| Docker DB (PostGIS + pgvector + pg_trgm) + migrations | ✅ |
| Step-visibility reporter (`observability/reporter.py`) | ✅ |
| Common loader (validate / dedupe / resolve / load) | ✅ |
| Embeddings (BGE-M3, hash-fallback offline) | ✅ |
| LLM client (Groq, deterministic stub offline) | ✅ |
| **P1 Places** — GeoPandas + PostGIS edges | ✅ fully functional |
| **P2 Content** — CSV import | ✅ fully functional · PDF path = skeleton |
| **P3 Questions** — auto map-drills + MCQ-from-fact | ✅ functional · PYQ = skeleton |
| **P4 Current Affairs** — RSS + trafilatura + LLM filter | ✅ functional (needs network) |
| **P5 Media** — geometry export, highlight PNGs, ZIP packs | ✅ functional · PMTiles needs `tippecanoe` |

## Quick start

```bash
# 1. Database (PostGIS + pgvector). Builds db/Dockerfile.
docker compose up -d db

# 2. Python deps (a virtualenv is recommended)
python -m venv .venv && .venv\Scripts\activate      # PowerShell: .venv\Scripts\Activate.ps1
pip install -e .

# 3. Config
copy .env.example .env

# 4. Schema
python -m bhugyan migrate
python -m bhugyan status

# 5. Run pipelines (each prints its steps live)
python -m bhugyan run p1                # load sample places + generate edges
python -m bhugyan run p2                # import sample content CSV through the loader
python -m bhugyan run p3                # auto-generate map-drill questions
python -m bhugyan run p3 --mode mcq     # LLM MCQs from loaded facts (stub offline)
python -m bhugyan run p5                # render media from geometry
python -m bhugyan run p4                # current affairs (needs network)

python -m bhugyan all                   # p1,p2,p3,p5 in order
```

## How "visibility at each step" works

Each pipeline opens a `PipelineRun` and wraps every stage in `run.step(...)`.
The reporter prints, per step: **input → output counts, items skipped and the
reason histogram, free-form notes, and wall time**, then a final summary table.
The same data is written to `run_logs/<pipeline>_run.json`.

Example (P2 content import):

```
╭──────── Pipeline P2: Content ────────╮
│ mode: csv                            │
│ llm: stub (offline)                  │
╰──────────────────────────────────────╯
▶ Step 1 — Extract            6 ok          0.01s
▶ Step 2 — Validate  (6 in)   5 ok, 1 skipped
     · skipped: no place names ×1
▶ Step 3 — Deduplicate (5 in) 4 ok, 1 skipped
     · skipped: duplicate (sim≥0.999) ×1
▶ Step 4 — Resolve places     4 ok
▶ Step 5 — Load               4 ok
```

## Config knobs (`.env`)
- `DATABASE_URL`, `REDIS_URL`
- `GROQ_API_KEY` — set to use real Llama 3.3 70B; empty = offline stub
- `DEDUPE_SIMILARITY_THRESHOLD` (0.95), `PLACE_RESOLVE_SCORE_CUTOFF` (85)

## Real data sources (drop-in for the samples)
- **P1**: Natural Earth / Census shapefiles → `run p1 --source path/to.shp`
- **P2**: Google-Sheet CSV export or NCERT PDF → `run p2 --mode pdf --source x.pdf`
- **P4**: edit `DEFAULT_FEEDS` in `p4_current_affairs.py` (PIB, The Hindu, IE)
```
