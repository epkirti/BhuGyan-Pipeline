"""BhuGyan data pipeline — map-as-spine learning platform.

Five extraction pipelines (P1 Places, P2 Content, P3 Questions, P4 Current
Affairs, P5 Media) feed one common loader that validates, deduplicates,
resolves place names, and loads into Postgres/PostGIS/pgvector.
"""

__version__ = "0.1.0"
