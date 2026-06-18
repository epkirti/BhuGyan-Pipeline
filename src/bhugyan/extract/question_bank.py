"""Extract MCQs from an institute / PYQ question-bank PDF.

These PDFs put the QUESTIONS up front and the ANSWERS in a separate section, so
a single pass can't see a question's answer. We extract in two passes and join
by (year, number):

  Pass 1 — Questions:  the LLM parses each numbered MCQ (stem, options,
           place_names, subject) from the question pages, year by year.
  Pass 2 — Answer key: a regex over the answer pages maps (year, number) ->
           option letter — handling both "Correct Option: (c)" and bare
           "1. c" solution-table formats.

Year-aware because PYQ compilations group questions by exam year and *restart*
numbering each year, so a bare number is ambiguous. Each returned question
carries the year of its section (or None for single-set books).
"""
from __future__ import annotations

import re
from pathlib import Path

from ..llm import llm

# Answer formats:  "12. Correct Option: (c)"   and   bare "12. c"  /  "12. C"
_ANS_CORRECT_OPT = re.compile(
    r"(\d{1,3})\s*\.?\s*Correct\s*Option\s*:?\s*\(?\s*([a-dA-D])\s*\)?", re.IGNORECASE)
_ANS_TABLE = re.compile(r"^\s*(\d{1,3})\s*[.\)]\s*([a-dA-D])\s*$", re.MULTILINE)

# Section headers carrying the exam year. Tolerates wording like
# "Previous Year Geography Questions 2021" and "Geography Prelims Questions UPSC
# 2020"; the (?!-) guard skips a range like "(2013-2021)" in the title.
_YEAR_Q = re.compile(
    r"Geography[^\n]{0,40}?Questions[^\n]{0,30}?(20\d\d)(?!\s*[-–])", re.IGNORECASE)
_YEAR_A = re.compile(r"Prelims\s*(20\d\d)", re.IGNORECASE)

_ANSWER_MARKERS = ("ANSWER HINTS", "ANSWER KEY", "Answers (Set", "Solutions 2013")

_SUBJECTS = (
    "geography, history, polity, economy, science, environment, culture, "
    "current_affairs, general_studies"
)

_SYSTEM_PROMPT = (
    "You extract multiple-choice questions from exam-paper text. Return STRICT "
    "JSON: an object with a 'questions' array. Each question object: number (the "
    "printed question number as an integer); stem (the full question text, "
    "INCLUDING any 'Consider the following' statements/lists, but DROP the "
    "'Select the correct answer/option using the code given below' boilerplate); "
    "options (array of the answer-choice strings WITHOUT their '(a)'/'(b)' "
    "labels); place_names (array of the geographic places/features the question "
    "is about — countries, seas, oceans, straits, rivers, mountains, lakes, "
    "deserts, cities, states, regions; [] if it concerns no specific place); "
    "subject (one of: " + _SUBJECTS + "); difficulty (integer 1-5). Extract only "
    "real numbered MCQs present in the text; never invent. If the text has no "
    "questions, return {\"questions\": []}."
)

_CHARS_PER_CHUNK = 4500


def _letter_to_index(letter: str) -> int:
    return "abcd".index(letter.lower())


def _coerce(raw) -> list[dict]:
    if isinstance(raw, list):
        return [q for q in raw if isinstance(q, dict)]
    if isinstance(raw, dict):
        if isinstance(raw.get("questions"), list):
            return [q for q in raw["questions"] if isinstance(q, dict)]
        if "stem" in raw:
            return [raw]
    return []


def _find_answer_start(pages: list[str]) -> int:
    """First page index that looks like the start of the answer/solution section.
    Either an explicit marker, or a page dense with bare 'N. x' answer lines."""
    for i, txt in enumerate(pages):
        if any(m in txt for m in _ANSWER_MARKERS):
            return i
        if len(_ANS_TABLE.findall(txt)) >= 4:      # an answer table
            return i
    return len(pages)


def _split_by_year(text: str, header_re: re.Pattern) -> list[tuple[str | None, str]]:
    """Split text into (year, block) segments at each year header."""
    marks = list(header_re.finditer(text))
    if not marks:
        return [(None, text)]
    blocks: list[tuple[str | None, str]] = []
    for idx, m in enumerate(marks):
        start = m.end()
        stop = marks[idx + 1].start() if idx + 1 < len(marks) else len(text)
        blocks.append((m.group(1), text[start:stop]))
    return blocks


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i:i + size]


def _extract_answer_key(text: str) -> dict[tuple[str | None, int], int]:
    """Map (year, number) -> answer index, across both answer formats."""
    key: dict[tuple[str | None, int], int] = {}
    for year, block in _split_by_year(text, _YEAR_A):
        for m in _ANS_CORRECT_OPT.finditer(block):
            key.setdefault((year, int(m.group(1))), _letter_to_index(m.group(2)))
        for m in _ANS_TABLE.finditer(block):
            key.setdefault((year, int(m.group(1))), _letter_to_index(m.group(2)))
    return key


def extract_question_bank(
    pdf_path,
    *,
    pages_per_chunk: int = 2,   # kept for CLI compat; char-based chunking used
    page_limit: int | None = None,
    on_progress=None,
) -> list[dict]:
    """Return question dicts: {number, year, stem, options, correct_index|None,
    place_names, subject, difficulty}."""
    import fitz  # PyMuPDF

    doc = fitz.open(Path(pdf_path))
    end = doc.page_count if page_limit is None else min(page_limit, doc.page_count)
    pages = [doc[i].get_text() for i in range(end)]
    answer_start = _find_answer_start(pages)

    def emit(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    # ---- Pass 2: answer key (regex over the answer section) ----
    answer_text = "\n".join(pages[answer_start:])
    answer_key = _extract_answer_key(answer_text)
    years = sorted({y for (y, _) in answer_key if y})
    emit(f"answer key: {len(answer_key)} answers"
         + (f" across years {', '.join(years)}" if years else "")
         + f" (from page {answer_start + 1})")

    # ---- Pass 1: questions (LLM over the question section, year by year) ----
    question_text = "\n".join(pages[:answer_start])
    questions: list[dict] = []
    for year, block in _split_by_year(question_text, _YEAR_Q):
        for chunk in _chunks(block, _CHARS_PER_CHUNK):
            if not chunk.strip():
                continue
            raw = llm.complete_json(system=_SYSTEM_PROMPT, user=chunk)
            for q in _coerce(raw):
                stem = str(q.get("stem", "")).strip()
                options = q.get("options")
                if not stem or not isinstance(options, list) or len(options) < 2:
                    continue
                num = q.get("number")
                num = int(num) if isinstance(num, (int, float)) else None
                places = q.get("place_names") or []
                if not isinstance(places, list):
                    places = [str(places)]
                places = [str(p).strip() for p in places if str(p).strip()]
                ci = answer_key.get((year, num)) if num is not None else None
                if ci is not None and ci >= len(options):
                    ci = None
                questions.append({
                    "number": num,
                    "year": year,
                    "stem": stem,
                    "options": [str(o) for o in options],
                    "correct_index": ci,
                    "place_names": places,
                    "subject": str(q.get("subject") or "geography"),
                    "difficulty": q.get("difficulty"),
                })
        emit(f"year {year or '?'}: {len(questions)} questions so far")

    return questions
