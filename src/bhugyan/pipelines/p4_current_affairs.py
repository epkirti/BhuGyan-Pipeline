"""P4: Current Affairs — daily multi-source RSS ingestion (the morning retention hook).

feedparser fetches RSS from five sources, trafilatura extracts the full article, and the
LLM strictly filters for map-relevance, distilling a 1-2 sentence fact + place names.
Never auto-published (status='pending_review'), per the report.

Network-dependent; degrades to a skeleton note if feeds/libs can't be reached.
Step 1 (fetch + filter) lives here; Steps 2-5 are the common loader, reported live.
"""
from __future__ import annotations

import re

from ..llm import llm
from ..loader import CommonLoader, NormalizedItem
from .base import Pipeline

# Five sources. Down To Earth's own RSS is defunct, so it's routed via Google News'
# site-scoped search; PIB returns nothing without a browser User-Agent (set below).
DEFAULT_FEEDS = [
    {"source": "Google News", "url": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"},
    {"source": "The Hindu", "url": "https://www.thehindu.com/news/national/feeder/default.rss"},
    {"source": "Indian Express", "url": "https://indianexpress.com/section/india/feed/"},
    {"source": "Down To Earth", "url": "https://news.google.com/rss/search?q=site:downtoearth.org.in+when:7d&hl=en-IN&gl=IN&ceid=IN:en"},
    {"source": "PIB", "url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"},
]
MAX_PER_FEED = 6

# Some feeds (notably PIB) reject requests without a browser User-Agent.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_TAG_RE = re.compile(r"<[^>]+>")

# Strict filter: most news is NOT about a place — reject those, keep only stories where a
# specific place is the subject. The word "filter" also keeps the offline LLM stub on its
# current-affairs branch (see llm/client.py).
FILTER_SYSTEM = (
    "You filter news for an India-focused, map-based learning app. KEEP an article only if "
    "it is ABOUT a specific place in India — a concrete event, change, or situation happening "
    "AT a city, town, district, river, landmark, or local area. The place must be the SUBJECT, "
    "not merely mentioned.\n\n"
    "REJECT (map_relevant=false) even when a place name appears, if the story is: exam results, "
    "admissions, or routine administrative announcements; party politics, leadership/merger "
    "news, agency probes, or court procedure (unless fundamentally about a specific local "
    "place); whole-state or national policy/surveys/statistics with no specific local site; "
    "markets, sports, opinion, entertainment, or celebrity news.\n"
    "Prefer specific places (city/town/district/landmark/river) over a whole state; if the ONLY "
    "place is an entire state and the story is administrative or political, REJECT.\n\n"
    "Examples:\n"
    "KEEP — 'A fire at a nightclub in Arpora, Goa killed 25 people.'\n"
    "KEEP — 'IMD issued an orange alert for Ernakulam and Thrissur districts.'\n"
    "REJECT — 'Andhra Pradesh announced Intermediate exam results.'\n"
    "REJECT — 'A TMC faction sought to merge with another party.'\n\n"
    "Return ONLY a JSON object with keys: map_relevant (bool), confidence (0-1), "
    "fact (1-2 sentences anchored to the place; empty if not relevant), "
    "place_names (array, most specific first; empty if not relevant)."
)


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", s or "")).strip()


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

    def _fetch_and_filter(self, feeds: list[dict], st) -> list[NormalizedItem]:
        try:
            import feedparser
            import trafilatura
        except Exception:
            st.note("feedparser/trafilatura not installed — skeleton path")
            st.set_in(0)
            return []

        limit = int(self.opts.get("limit", MAX_PER_FEED))
        items: list[NormalizedItem] = []
        total_entries = 0
        for feed in feeds:
            source, url = feed["source"], feed["url"]
            try:
                parsed = feedparser.parse(url, agent=_UA)
            except Exception as e:
                st.note(f"feed failed: {source} ({e})")
                continue
            entries = parsed.entries[:limit]
            total_entries += len(entries)
            st.note(f"{source}: {len(entries)} entries")
            for entry in entries:
                link = getattr(entry, "link", None)
                title = _strip(getattr(entry, "title", ""))
                # Full text -> RSS summary -> title, so there's always something to judge.
                article = ""
                if link:
                    try:
                        article = trafilatura.extract(trafilatura.fetch_url(link)) or ""
                    except Exception:
                        article = ""
                text = article or _strip(getattr(entry, "summary", "")) or title
                if not text:
                    st.skip("empty article")
                    continue
                verdict = llm.complete_json(
                    system=FILTER_SYSTEM,
                    user=f"Article title: {title}\n\nArticle text:\n{text[:6000]}",
                )
                if not verdict.get("map_relevant") or not (verdict.get("fact") or "").strip():
                    st.skip("not map-relevant")
                    continue
                items.append(NormalizedItem(
                    body=verdict["fact"].strip()[:500],
                    unit_type="current_affair",
                    subject="current_affairs",
                    place_names=[p for p in verdict.get("place_names", []) if isinstance(p, str)],
                    exam_tags=["upsc"],
                    status="pending_review",       # CA always needs human review
                    source_pipeline="p4",
                    payload={"source": source,
                             "source_url": link,
                             "title": getattr(entry, "title", ""),
                             "confidence": verdict.get("confidence")},
                ))
        st.set_in(total_entries)
        st.ok(len(items))
        st.note(f"{total_entries} entries -> {len(items)} map-relevant (pending_review)")
        return items
