-- BhuGyan schema — Step 0: extensions
-- Postgres + PostGIS + pgvector + pg_trgm (see report §4 Requirements).

CREATE EXTENSION IF NOT EXISTS postgis;     -- geometry, spatial queries (P1 edges)
CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector — semantic dedup (Step 3)
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- trigram support for fuzzy text
