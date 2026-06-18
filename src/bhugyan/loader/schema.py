"""The normalized item — the single shape every extractor produces (report §3
Step 1). The common loader only ever sees NormalizedItem; it knows nothing
about shapefiles, PDFs, RSS, or CSV."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NormalizedItem(BaseModel):
    body: str = ""                                   # the text content
    unit_type: str = "fact"                          # fact|lesson|mcq|map_tap|map_drag|current_affair
    subject: str = "geography"                       # geography|history|polity|...
    place_names: list[str] = Field(default_factory=list)  # raw strings to resolve
    exam_tags: list[str] = Field(default_factory=list)    # upsc|ssc|...
    class_levels: list[str] = Field(default_factory=list) # class_10|...
    layers: list[str] = Field(default_factory=list)       # core|extra|...
    scopes: list[str] = Field(default_factory=list)       # national|state|...
    difficulty: int | None = None                    # 1..5
    depth_levels: list[str] = Field(default_factory=list)
    locale: str = "en"
    status: str = "draft"                            # draft|pending_review|published
    source_pipeline: str | None = None               # p1..p5
    payload: dict[str, Any] = Field(default_factory=dict)  # options/correct_index, url, etc.

    def tag_pairs(self) -> list[tuple[str, str]]:
        """Flatten the tag lists into (tag_type, tag_value) rows for content_tags."""
        pairs: list[tuple[str, str]] = []
        for v in self.exam_tags:
            pairs.append(("exam", v))
        for v in self.class_levels:
            pairs.append(("class_level", v))
        for v in self.layers:
            pairs.append(("layer", v))
        for v in self.scopes:
            pairs.append(("scope", v))
        return pairs
