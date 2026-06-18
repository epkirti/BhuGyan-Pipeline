"""Unit tests that don't need a database — validation, resolution, embeddings."""
from bhugyan.loader.embeddings import embed, _hash_embed
from bhugyan.loader.dedupe import cosine
from bhugyan.loader.resolve import PlaceIndex, resolve_places
from bhugyan.loader.schema import NormalizedItem
from bhugyan.loader.validate import validate_item


def test_validate_requires_body_and_place():
    assert validate_item(NormalizedItem(body="", place_names=["X"])) == "missing body"
    assert validate_item(NormalizedItem(body="hi", place_names=[])) == "no place names"
    assert validate_item(NormalizedItem(body="hi", place_names=["Ganga"])) is None


def test_validate_question_needs_options():
    q = NormalizedItem(body="Q?", unit_type="mcq", place_names=["India"],
                       payload={"options": ["a", "b"], "correct_index": 0})
    assert validate_item(q) is None
    bad = NormalizedItem(body="Q?", unit_type="mcq", place_names=["India"],
                         payload={"options": ["a"], "correct_index": 0})
    assert validate_item(bad) == "question missing options"


def test_identical_text_is_near_duplicate():
    a, b = embed("the ganga flows through india"), embed("the ganga flows through india")
    assert cosine(a, b) > 0.99


def test_hash_embed_is_unit_norm():
    v = _hash_embed("hello world", 1024)
    assert abs(sum(x * x for x in v) - 1.0) < 1e-6


class _Rec(dict):
    def __getitem__(self, k):
        return super().__getitem__(k)


def test_resolve_fuzzy_match():
    rows = [_Rec(id=1, name="Maharashtra", name_hi="महाराष्ट्र"),
            _Rec(id=2, name="Ganga", name_hi="गंगा")]
    idx = PlaceIndex(rows)
    resolved, unresolved = resolve_places(idx, ["Maharastra", "Ganga"])  # typo
    assert {r["place_id"] for r in resolved} == {1, 2}
    assert resolved[0]["relevance"] == 1.0   # first mention is primary
    assert resolved[1]["relevance"] == 0.5
    assert unresolved == []
