"""P2: Content — CSV import (fully working) + NCERT PDF extraction (skeleton).

CSV rows import directly through the common loader. PDF chapters are extracted
with PyMuPDF and drafted into facts by the LLM (Groq) — AI-drafted content is
never auto-published (status='pending_review'), per the report.

Step 1 (Extract) lives here; Steps 2-5 are the common loader, reported live.
"""
from __future__ import annotations

import csv
from pathlib import Path

from ..config import PROJECT_ROOT
from ..llm import llm
from ..loader import CommonLoader, NormalizedItem
from .base import Pipeline

DEFAULT_CSV = PROJECT_ROOT / "data" / "sample" / "content.csv"


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in value.replace(";", "|").split("|") if p.strip()]


class ContentPipeline(Pipeline):
    id = "p2"
    label = "Content"

    async def run(self) -> dict:
        mode = self.opts.get("mode", "csv")        # csv | pdf
        run = self.new_run(meta={"mode": mode,
                                 "llm": "live (Groq)" if llm.is_live else "stub (offline)"})

        with run.step("Step 1 — Extract") as st:
            if mode == "pdf":
                items = self._extract_pdf(st)
            else:
                items = self._extract_csv(st)

        result = await CommonLoader(self.conn).load(items, run)
        return run.finish(extra=result)

    # ---- CSV (fully working) ----
    def _extract_csv(self, st) -> list[NormalizedItem]:
        path = Path(self.opts.get("source") or DEFAULT_CSV)
        items: list[NormalizedItem] = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                items.append(NormalizedItem(
                    body=row.get("body", ""),
                    unit_type=row.get("unit_type") or "fact",
                    subject=row.get("subject") or "geography",
                    place_names=_split(row.get("place_names")),
                    exam_tags=_split(row.get("exam_tags")),
                    class_levels=_split(row.get("class_levels")),
                    difficulty=int(row["difficulty"]) if row.get("difficulty") else None,
                    depth_levels=_split(row.get("depth_levels")),
                    locale=row.get("locale") or "en",
                    status="published",           # manual CSV is trusted -> publish
                    source_pipeline="p2",
                ))
        st.set_in(len(items))
        st.ok(len(items))
        st.note(f"CSV rows read: {len(items)} from {path.name}")
        return items

    # ---- PDF (skeleton: PyMuPDF chapters -> Groq draft facts) ----
    def _extract_pdf(self, st) -> list[NormalizedItem]:
        path = Path(self.opts.get("source") or "")
        if not path.exists():
            st.note("no PDF supplied — skeleton path (set --source <pdf>)")
            st.set_in(0)
            return []
        import fitz  # PyMuPDF

        doc = fitz.open(path)
        items: list[NormalizedItem] = []
        for page in doc:
            text = page.get_text().strip()
            if not text:
                continue
            # LLM drafts facts from chapter text (structured JSON).
            drafts = llm.complete_json(
                system="You draft atomic geography facts as JSON list with "
                       "fields body, subject, place_names, difficulty.",
                user=text[:4000],
            )
            for d in (drafts if isinstance(drafts, list) else [drafts]):
                items.append(NormalizedItem(
                    body=d.get("body", ""),
                    subject=d.get("subject", "geography"),
                    place_names=d.get("place_names", []),
                    difficulty=d.get("difficulty"),
                    status="pending_review",       # AI-drafted -> human review
                    source_pipeline="p2",
                ))
        st.set_in(len(items))
        st.ok(len(items))
        st.note(f"{doc.page_count} pages -> {len(items)} draft facts (pending_review)")
        return items
