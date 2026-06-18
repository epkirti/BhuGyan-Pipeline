# PostGIS + pgvector in one image for local development.
# Mirrors the Supabase prod target (which has PostGIS, pgvector, pg_trgm).
FROM postgis/postgis:16-3.4

# pgvector — build from the postgresql-16-pgvector package (Debian bookworm).
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
