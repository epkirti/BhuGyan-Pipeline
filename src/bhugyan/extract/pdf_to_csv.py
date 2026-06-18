"""Turn a book PDF into a CSV of draft facts, ready for P2.

Flow:  PDF --(PyMuPDF)--> page text --(LLM, chapter at a time)--> fact JSON
       --> CSV in the exact column shape P2's importer expects.

The CSV is meant to be **reviewed and corrected by a human** before loading,
because LLM extraction from textbooks is imperfect (it can miss a place name,
mis-tag difficulty, or occasionally over-reach). The single most important field
is `place_names`: P2 rejects any fact with no place, so this module reports how
many rows lack one rather than silently dropping them.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from ..llm import llm

# The exact header P2's CSV importer reads (see p2_content.py:_extract_csv).
CSV_COLUMNS = [
    "body", "unit_type", "subject", "place_names", "exam_tags",
    "class_levels", "difficulty", "depth_levels", "locale",
]

_SYSTEM_PROMPT = (
    "You extract atomic, exam-relevant GEOGRAPHY facts from textbook text. "
    "Return STRICT JSON: an object with a 'facts' array. Each fact is an object "
    "with fields: body (one self-contained sentence, only facts stated in the "
    "text — never invent), subject (default 'geography'), place_names (array of "
    "the Indian places the fact is about — REQUIRED, omit the fact if it names "
    "no place), difficulty (integer 1-5), depth_levels (array, e.g. "
    "['beginner']). Do not include markdown. If the text has no usable facts, "
    "return {\"facts\": []}."
)


def _coerce_facts(raw: Any) -> list[dict]:
    """The model (or stub) may return a list, a {'facts': [...]} object, or a
    single fact dict. Normalize all three to a list of dicts."""
    if isinstance(raw, list):
        return [f for f in raw if isinstance(f, dict)]
    if isinstance(raw, dict):
        if isinstance(raw.get("facts"), list):
            return [f for f in raw["facts"] if isinstance(f, dict)]
        if "body" in raw:                       # a single fact object
            return [raw]
    return []


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.replace(";", "|").split("|") if p.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def _join(values: Iterable[str]) -> str:
    return "|".join(values)


def _chunks(doc, pages_per_chunk: int, page_limit: int | None):
    """Yield (label, text) for groups of pages, skipping empty text."""
    n = doc.page_count if page_limit is None else min(page_limit, doc.page_count)
    buf, start = [], 0
    for i in range(n):
        text = doc[i].get_text().strip()
        if not buf:
            start = i
        if text:
            buf.append(text)
        if (i - start + 1) >= pages_per_chunk or i == n - 1:
            if buf:
                yield (f"pages {start + 1}-{i + 1}", "\n\n".join(buf))
            buf = []
    return


def pdf_to_csv(
    pdf_path: str | Path,
    out_path: str | Path,
    *,
    subject: str = "geography",
    exam_tags: list[str] | None = None,
    class_levels: list[str] | None = None,
    locale: str = "en",
    pages_per_chunk: int = 2,
    page_limit: int | None = None,
    on_progress=None,
) -> dict:
    """Extract facts from `pdf_path` and write a P2-ready CSV at `out_path`.

    `exam_tags` / `class_levels` are *defaults* applied when the model does not
    provide them (a whole book is usually one class level / exam track).
    Returns a summary dict.
    """
    import fitz  # PyMuPDF

    pdf_path = Path(pdf_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    exam_tags = exam_tags or []
    class_levels = class_levels or []

    def emit(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    doc = fitz.open(pdf_path)
    rows: list[dict] = []
    no_place = 0
    chunks_done = 0

    for label, text in _chunks(doc, pages_per_chunk, page_limit):
        chunks_done += 1
        raw = llm.complete_json(system=_SYSTEM_PROMPT, user=text[:6000])
        facts = _coerce_facts(raw)
        emit(f"{label}: {len(facts)} fact(s)")
        for f in facts:
            body = str(f.get("body", "")).strip()
            if not body:
                continue
            places = _as_list(f.get("place_names"))
            if not places:
                no_place += 1
            diff = f.get("difficulty")
            rows.append({
                "body": body,
                "unit_type": str(f.get("unit_type") or "fact"),
                "subject": str(f.get("subject") or subject),
                "place_names": _join(places),
                "exam_tags": _join(_as_list(f.get("exam_tags")) or exam_tags),
                "class_levels": _join(_as_list(f.get("class_levels")) or class_levels),
                "difficulty": str(int(diff)) if isinstance(diff, (int, float)) else "",
                "depth_levels": _join(_as_list(f.get("depth_levels"))),
                "locale": str(f.get("locale") or locale),
            })

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "pdf": str(pdf_path),
        "pages_read": doc.page_count if page_limit is None
        else min(page_limit, doc.page_count),
        "chunks": chunks_done,
        "facts_written": len(rows),
        "facts_without_place": no_place,
        "csv": str(out_path),
        "llm": "live (Groq)" if llm.is_live else "stub (offline)",
    }
