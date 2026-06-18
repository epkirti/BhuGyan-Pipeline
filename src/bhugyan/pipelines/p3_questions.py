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
        mode = self.opts.get("mode", "drills")     # drills | mcq | pyq
        run = self.new_run(meta={"mode": mode,
                                 "llm": "live (Groq)" if llm.is_live else "stub (offline)"})

        with run.step("Step 1 — Generate") as st:
            if mode == "mcq":
                items = await self._gen_mcqs(st)
            elif mode == "pyq":
                items = self._gen_pyqs(st)
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

    # ---- PYQ extraction (skeleton) ----
    def _gen_pyqs(self, st) -> list[NormalizedItem]:
        st.note("PYQ extraction skeleton: PyMuPDF reads exam PDF, LLM extracts "
                "Q + options + answer key. Supply --source <pdf>.")
        st.set_in(0)
        return []
