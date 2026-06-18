"""P4: Current Affairs — daily RSS ingestion (the morning retention hook).

Cron at 6 AM IST: feedparser fetches RSS, trafilatura extracts the full article,
the LLM filters for map-relevance and extracts a 1-2 sentence fact + place names.
Never auto-published (status='pending_review'), per the report.

Network-dependent; degrades to a skeleton note if feeds can't be reached.
Step 1 (Fetch + filter) here; Steps 2-5 are the common loader, reported live.
"""
from __future__ import annotations

from ..llm import llm
from ..loader import CommonLoader, NormalizedItem
from .base import Pipeline

DEFAULT_FEEDS = [
    "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",   # PIB
    "https://www.thehindu.com/news/national/feeder/default.rss",
]
MAX_PER_FEED = 5


class CurrentAffairsPipeline(Pipeline):
    id = "p4"
    label = "Current Affairs"

    async def run(self) -> dict:
        feeds = self.opts.get("feeds") or DEFAULT_FEEDS
        run = self.new_run(meta={"feeds": len(feeds),
                                 "llm": "live (Groq)" if llm.is_live else "stub (offline)",
                                 "autopublish": "no (human review)"})

        with run.step("Step 1 — Fetch RSS + LLM filter") as st:
            items = self._fetch_and_filter(feeds, st)

        result = await CommonLoader(self.conn).load(items, run)
        return run.finish(extra=result)

    def _fetch_and_filter(self, feeds: list[str], st) -> list[NormalizedItem]:
        try:
            import feedparser
            import trafilatura
        except Exception:
            st.note("feedparser/trafilatura not installed — skeleton path")
            st.set_in(0)
            return []

        items: list[NormalizedItem] = []
        total_entries = 0
        for url in feeds:
            try:
                parsed = feedparser.parse(url)
            except Exception as e:
                st.note(f"feed failed: {url} ({e})")
                continue
            entries = parsed.entries[:MAX_PER_FEED]
            total_entries += len(entries)
            for entry in entries:
                link = getattr(entry, "link", None)
                article = ""
                if link:
                    try:
                        downloaded = trafilatura.fetch_url(link)
                        article = trafilatura.extract(downloaded) or ""
                    except Exception:
                        article = ""
                text = article or getattr(entry, "summary", "") or getattr(entry, "title", "")
                if not text:
                    st.skip("empty article")
                    continue
                verdict = llm.complete_json(
                    system="You filter news for map-relevance. Return JSON with "
                           "map_relevant (bool), fact (1-2 sentences), place_names.",
                    user=text[:4000],
                )
                if not verdict.get("map_relevant"):
                    st.skip("not map-relevant")
                    continue
                items.append(NormalizedItem(
                    body=verdict.get("fact", "")[:500],
                    unit_type="current_affair",
                    subject="current_affairs",
                    place_names=verdict.get("place_names", []),
                    exam_tags=["upsc"],
                    status="pending_review",       # CA always needs human review
                    source_pipeline="p4",
                    payload={"source_url": link, "title": getattr(entry, "title", "")},
                ))
        st.set_in(total_entries)
        st.ok(len(items))
        st.note(f"{total_entries} entries -> {len(items)} map-relevant (pending_review)")
        return items
