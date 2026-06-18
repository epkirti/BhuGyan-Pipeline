-- BhuGyan schema — indexes for the loader's hot paths.

-- Spatial indexes (PostGIS edge generation: ST_Touches / ST_Intersects).
CREATE INDEX IF NOT EXISTS idx_places_geom     ON places USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_places_centroid ON places USING GIST (centroid);
CREATE INDEX IF NOT EXISTS idx_places_type     ON places (place_type);
CREATE INDEX IF NOT EXISTS idx_places_parent   ON places (parent_id);

-- Fuzzy place-name resolution (Step 4, rapidfuzz pre-filter via trigram).
CREATE INDEX IF NOT EXISTS idx_places_name_trgm
    ON places USING GIN (name gin_trgm_ops);

-- Semantic dedup (Step 3): cosine distance ANN over content embeddings.
-- ivfflat needs ANALYZE + data to be effective; fine for dev scale.
CREATE INDEX IF NOT EXISTS idx_content_embedding
    ON content_units USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_content_status   ON content_units (status);
CREATE INDEX IF NOT EXISTS idx_content_type     ON content_units (unit_type);
CREATE INDEX IF NOT EXISTS idx_place_content_pl ON place_content (place_id);
CREATE INDEX IF NOT EXISTS idx_content_tags_val ON content_tags (tag_type, tag_value);
