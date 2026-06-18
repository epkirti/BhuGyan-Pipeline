"""Groq LLM client with a deterministic offline STUB fallback.

Real calls go to Groq (Llama 3.3 70B) with structured-JSON prompts when
GROQ_API_KEY is set. With no key, a stub returns plausible structured output so
the pipelines (P2 fact drafting, P3 MCQ gen, P4 CA filtering) are fully runnable
offline. Per the report, LLM output is NEVER auto-published — callers set
status='pending_review'/'draft'.
"""
from __future__ import annotations

import json
import re

from ..config import settings


class LLMClient:
    def __init__(self):
        self._groq = None

    def _get_groq(self):
        if self._groq is None and settings.has_llm:
            from groq import Groq

            self._groq = Groq(api_key=settings.groq_api_key)
        return self._groq

    @property
    def is_live(self) -> bool:
        return settings.has_llm

    def complete_json(self, system: str, user: str) -> dict | list:
        """Return parsed JSON from the model (or stub)."""
        if not settings.has_llm:
            return self._stub(system, user)
        client = self._get_groq()
        resp = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(resp.choices[0].message.content)

    # ---- offline stub ----
    def _stub(self, system: str, user: str) -> dict | list:
        s = system.lower()
        if "current affair" in s or "map-relevance" in s or "filter" in s:
            # P4: CA filter -> relevance + extracted fact + places
            places = self._guess_places(user)
            return {
                "map_relevant": bool(places),
                "fact": (user.strip()[:140] + "…") if user else "",
                "place_names": places or ["India"],
                "subject": "current_affairs",
            }
        if "multiple choice" in s or "mcq" in s or "question" in s:
            # P3: MCQ from a fact
            return {
                "stem": "[STUB] Which place does this fact relate to?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct_index": 0,
                "place_names": self._guess_places(user) or ["India"],
            }
        # P2: draft facts from chapter text -> list of fact dicts
        return [
            {
                "body": "[STUB FACT] " + (user.strip()[:120] if user else "sample fact"),
                "subject": "geography",
                "place_names": self._guess_places(user) or ["India"],
                "difficulty": 2,
            }
        ]

    @staticmethod
    def _guess_places(text: str) -> list[str]:
        """Very rough capitalized-token grab so the stub yields resolvable names."""
        known = ["India", "Maharashtra", "Ganga", "Himalaya", "Gujarat",
                 "Rajasthan", "Karnataka", "Delhi", "Mumbai"]
        found = [k for k in known if re.search(rf"\b{k}\b", text, re.I)]
        return found


llm = LLMClient()
