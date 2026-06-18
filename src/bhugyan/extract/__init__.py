"""PDF -> CSV fact extraction — the human-reviewable bridge into P2.

This is deliberately a *separate* step from the pipelines: it turns a book PDF
into a CSV of draft facts (via the LLM), which a human reviews/edits before
`bhugyan run p2 --source that.csv` loads it. Keeping the flaky/expensive LLM
extraction apart from the deterministic loader means the CSV can be corrected,
re-imported, and audited without re-calling the model.
"""
from .pdf_to_csv import pdf_to_csv
from .question_bank import extract_question_bank

__all__ = ["pdf_to_csv", "extract_question_bank"]
