"""Text embeddings for semantic dedup (Step 3).

Prefers BGE-M3 via sentence-transformers when installed. If it is not present
(or the model can't be loaded), falls back to a *deterministic hash-based*
embedder so the dedup step still runs offline — identical text yields identical
vectors, so exact-duplicate detection keeps working even without the real model.
"""
from __future__ import annotations

import hashlib
import math

from ..config import settings

_model = None
_tried_load = False


def _load_real_model():
    global _model, _tried_load
    if _tried_load:
        return _model
    _tried_load = True
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(settings.embedding_model)
    except Exception:
        _model = None
    return _model


def _hash_embed(text: str, dim: int) -> list[float]:
    """Deterministic pseudo-embedding from token hashes; L2-normalized.

    Not semantically meaningful across paraphrases, but stable and unit-norm so
    cosine similarity of identical / near-identical strings is ~1.0.
    """
    vec = [0.0] * dim
    tokens = text.lower().split() or [text.lower()]
    for tok in tokens:
        h = hashlib.sha256(tok.encode("utf-8")).digest()
        for i in range(0, len(h), 4):
            idx = int.from_bytes(h[i:i + 4], "big") % dim
            vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> list[float]:
    model = _load_real_model()
    if model is not None:
        v = model.encode(text, normalize_embeddings=True)
        return [float(x) for x in v]
    return _hash_embed(text, settings.embedding_dim)


def using_real_model() -> bool:
    return _load_real_model() is not None
