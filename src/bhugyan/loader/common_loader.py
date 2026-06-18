"""The common loader — the shared validation + loading layer all five pipelines
feed into (report §1, §3). Runs Steps 2-5 and reports each one live.

    extracted items (Step 1, done by each pipeline)
        -> Step 2 Validate
        -> Step 3 Deduplicate (pgvector)
        -> Step 4 Resolve places (rapidfuzz)
        -> Step 5 Load (transactional)
"""
from __future__ import annotations

import asyncpg

from ..observability import PipelineRun
from . import dedupe, embeddings
from .load import insert_item, invalidate_cache
from .resolve import PlaceIndex, resolve_places
from .schema import NormalizedItem
from .validate import validate_item


class CommonLoader:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def load(self, items: list[NormalizedItem], run: PipelineRun) -> dict:
        # ---- Step 2: Validate ----
        with run.step("Step 2 — Validate", total_in=len(items)) as st:
            valid: list[NormalizedItem] = []
            for it in items:
                reason = validate_item(it)
                if reason:
                    st.skip(reason)
                else:
                    valid.append(it)
                    st.ok()

        # ---- Step 3: Deduplicate (pgvector cosine similarity) ----
        with run.step("Step 3 — Deduplicate", total_in=len(valid)) as st:
            st.note(f"embedder: {'BGE-M3' if embeddings.using_real_model() else 'hash-fallback (offline)'}")
            deduped: list[tuple[NormalizedItem, list[float]]] = []
            batch_vecs: list[list[float]] = []
            for it in valid:
                vec = embeddings.embed(it.body)
                is_dup, sim = await dedupe.check_duplicate(self.conn, vec, batch_vecs)
                if is_dup:
                    st.skip(f"duplicate (sim≥{sim:.3f})")
                    continue
                deduped.append((it, vec))
                batch_vecs.append(vec)
                st.ok()

        # ---- Step 4: Resolve places (rapidfuzz) ----
        with run.step("Step 4 — Resolve places", total_in=len(deduped)) as st:
            index = await PlaceIndex.load(self.conn)
            resolvable: list[tuple[NormalizedItem, list[float], list[dict]]] = []
            for it, vec in deduped:
                resolved, unresolved = resolve_places(index, it.place_names)
                for u in unresolved:
                    st.note(f"unresolved: '{u['name']}' "
                            f"(best {u['best_match']}@{u['best_score']:.0f})")
                if not resolved:
                    st.skip("no place resolved")
                    continue
                resolvable.append((it, vec, resolved))
                st.ok()

        # ---- Step 5: Load (transactional insert + cache invalidate) ----
        loaded_ids: list[int] = []
        affected_places: set[int] = set()
        with run.step("Step 5 — Load", total_in=len(resolvable)) as st:
            for it, vec, resolved in resolvable:
                cu_id = await insert_item(self.conn, it, vec, resolved)
                loaded_ids.append(cu_id)
                affected_places.update(r["place_id"] for r in resolved)
                st.ok()
            n_inval = await invalidate_cache(list(affected_places))
            st.note(f"cache keys invalidated: {n_inval}")

        return {
            "loaded": len(loaded_ids),
            "loaded_ids": loaded_ids,
            "affected_places": len(affected_places),
        }
