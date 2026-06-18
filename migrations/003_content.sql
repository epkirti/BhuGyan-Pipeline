-- BhuGyan schema — Content model (shared by P2 Content, P3 Questions, P4 CA)
-- Place-first: every content_unit links to >=1 place via place_content.
-- Authored once, reused across exams/depths/languages via content_tags + joins.

CREATE TABLE IF NOT EXISTS content_units (
    id             BIGSERIAL PRIMARY KEY,
    body           TEXT NOT NULL,                -- the fact / lesson / question stem
    unit_type      TEXT NOT NULL,                -- fact|lesson|mcq|map_tap|map_drag|current_affair
    subject        TEXT NOT NULL,                -- geography|history|polity|...
    difficulty     SMALLINT,                     -- 1..5
    depth_levels   TEXT[] NOT NULL DEFAULT '{}', -- e.g. {beginner,intermediate}
    locale         TEXT NOT NULL DEFAULT 'en',
    status         TEXT NOT NULL DEFAULT 'draft',-- draft|pending_review|published
    source_pipeline TEXT,                        -- p1..p5
    payload        JSONB NOT NULL DEFAULT '{}',  -- question options/correct_index, CA url, etc.
    embedding      vector(1024),                 -- BGE-M3 (or fallback) — Step 3 dedup
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Link content -> places. relevance: 1.0 primary (first mention), 0.5 secondary.
CREATE TABLE IF NOT EXISTS place_content (
    content_unit_id BIGINT NOT NULL REFERENCES content_units(id) ON DELETE CASCADE,
    place_id        BIGINT NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    relevance       REAL NOT NULL DEFAULT 0.5,
    PRIMARY KEY (content_unit_id, place_id)
);

-- One row per exam / class_level / layer / scope tag. Reuse without duplication.
CREATE TABLE IF NOT EXISTS content_tags (
    content_unit_id BIGINT NOT NULL REFERENCES content_units(id) ON DELETE CASCADE,
    tag_type        TEXT NOT NULL,               -- exam|class_level|layer|scope
    tag_value       TEXT NOT NULL,               -- upsc|ssc|class_10|core|...
    PRIMARY KEY (content_unit_id, tag_type, tag_value)
);

-- Non-English bodies live here (Step 5 inserts for locale != en).
CREATE TABLE IF NOT EXISTS content_translation (
    content_unit_id BIGINT NOT NULL REFERENCES content_units(id) ON DELETE CASCADE,
    locale          TEXT NOT NULL,
    body            TEXT NOT NULL,
    PRIMARY KEY (content_unit_id, locale)
);
