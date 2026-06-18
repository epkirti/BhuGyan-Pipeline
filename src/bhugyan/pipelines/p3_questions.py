"""P3: Questions.

  - Map drills: loop the places table and auto-create map_tap questions
    (zero manual work, auto-published) — fully working.
  - MCQs: LLM generates one MCQ per published fact (pending_review) — works
    via the LLM stub offline.
  - PYQs: extract from exam PDFs with answer keys — skeleton.

Step 1 (Generate) here; Steps 2-5 are the common loader, reported live.
"""
from __future__ import annotations

from ..llm import llm
from ..loader import CommonLoader, NormalizedItem
from .base import Pipeline


class QuestionsPipeline(Pipeline):
    id = "p3"
    label = "Questions"

    async def run(self) -> dict:
        mode = self.opts.get("mode", "drills")     # drills | mcq | qbank
        run = self.new_run(meta={"mode": mode,
                                 "llm": "live (Groq)" if llm.is_live else "stub (offline)"})

        with run.step("Step 1 — Generate") as st:
            if mode == "mcq":
                items = await self._gen_mcqs(st)
            elif mode in ("qbank", "pyq", "practice"):
                items = self._gen_question_bank(st)
            else:
                items = await self._gen_map_drills(st)

        result = await CommonLoader(self.conn).load(items, run)
        return run.finish(extra=result)

    # ---- Map drills (fully working, auto-published) ----
    async def _gen_map_drills(self, st) -> list[NormalizedItem]:
        states = [r["name"] for r in await self.conn.fetch(
            "SELECT name FROM places WHERE place_type='state' ORDER BY name")]
        items: list[NormalizedItem] = []
        for i, name in enumerate(states):
            distractors = [s for s in states if s != name][:3]
            options = [name] + distractors
            items.append(NormalizedItem(
                body=f"Identify {name} on the map.",
                unit_type="map_tap",
                subject="geography",
                place_names=[name],
                exam_tags=["upsc", "ssc"],
                difficulty=1,
                depth_levels=["beginner"],
                status="published",                # auto-drills are trusted
                source_pipeline="p3",
                payload={"options": options, "correct_index": 0, "format": "map_tap"},
            ))
        st.set_in(len(items))
        st.ok(len(items))
        st.note(f"{len(states)} states -> {len(items)} map-drill questions")
        return items

    # ---- MCQs from facts (LLM, pending_review) ----
    async def _gen_mcqs(self, st) -> list[NormalizedItem]:
        facts = await self.conn.fetch(
            "SELECT id, body FROM content_units "
            "WHERE unit_type='fact' AND status='published' LIMIT 10")
        items: list[NormalizedItem] = []
        for f in facts:
            q = llm.complete_json(
                system="Generate one multiple-choice question (mcq) from the fact "
                       "as JSON with stem, options (4), correct_index, place_names.",
                user=f["body"],
            )
            items.append(NormalizedItem(
                body=q.get("stem", ""),
                unit_type="mcq",
                subject="geography",
                place_names=q.get("place_names", []),
                exam_tags=["upsc"],
                difficulty=2,
                status="pending_review",
                source_pipeline="p3",
                payload={"options": q.get("options", []),
                         "correct_index": q.get("correct_index", 0),
                         "from_fact_id": f["id"]},
            ))
        st.set_in(len(items))
        st.ok(len(items))
        st.note(f"{len(facts)} facts -> {len(items)} MCQs (pending_review)")
        return items

    # ---- Question-bank extraction (institute PDF -> tagged map MCQs) ----
    def _gen_question_bank(self, st) -> list[NormalizedItem]:
        from pathlib import Path

        from ..extract.question_bank import extract_question_bank
        from ..loader.validate import VALID_SUBJECTS

        source = self.opts.get("source")
        if not source or not Path(source).exists():
            st.note("supply a PDF: run p3 --mode qbank --source <pdf> "
                    "--exam upsc --year 2021 --paper map_based_questions")
            st.set_in(0)
            return []

        exam = self.opts.get("exam") or "upsc"
        cli_year = str(self.opts.get("year") or "").strip()
        paper = (self.opts.get("paper") or "").strip()
        qtype = (self.opts.get("qtype") or "practice").strip()   # practice | pyq
        map_only = bool(self.opts.get("map_only"))               # opt-in place filter
        chunk = int(self.opts.get("chunk") or 2)
        page_limit = int(self.opts["pages"]) if self.opts.get("pages") else None

        questions = extract_question_bank(
            source, pages_per_chunk=chunk, page_limit=page_limit,
            on_progress=lambda m: st.note(m))

        items: list[NormalizedItem] = []
        dropped_no_place = unanswered = 0
        for q in questions:
            if map_only and not q["place_names"]:   # keep map-relevant only (opt-in)
                dropped_no_place += 1
                continue
            # the question's own section year wins over the --year flag
            year = str(q.get("year") or cli_year or "").strip()
            extra = [("source_type", qtype)]
            if year:
                extra.append(("exam_year", year))
            if paper:
                extra.append(("paper", paper))
            has_answer = q["correct_index"] is not None
            if not has_answer:
                unanswered += 1
            diff = q["difficulty"]
            subject = q["subject"] if q["subject"] in VALID_SUBJECTS else "geography"
            items.append(NormalizedItem(
                body=q["stem"],
                unit_type="mcq",
                subject=subject,
                place_names=q["place_names"],
                exam_tags=[exam],
                extra_tags=extra,
                difficulty=int(diff) if isinstance(diff, (int, float))
                and 1 <= int(diff) <= 5 else None,
                place_optional=True,          # places may not be in the map yet
                # answered -> trusted; unanswered -> human fills the answer
                status="published" if has_answer else "pending_review",
                source_pipeline="p3",
                payload={
                    "options": q["options"],
                    "correct_index": q["correct_index"],   # None if no answer key
                    "answer_known": has_answer,
                    "source": "question_bank",
                    "exam": exam, "year": year, "paper": paper, "qtype": qtype,
                    "q_number": q["number"],
                    # keep the places even if they don't resolve to the map yet,
                    # so they're not lost and can be re-resolved later.
                    "place_names_raw": q["place_names"],
                },
            ))
        st.set_in(len(items))
        st.ok(len(items))
        st.note(f"{len(questions)} extracted -> {len(items)} kept "
                f"({dropped_no_place} dropped: no place); "
                f"{unanswered} without answer key (pending_review)")
        return items
