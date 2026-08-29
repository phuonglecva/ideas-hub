import asyncio
from functools import lru_cache
from typing import Any

import numpy as np

from ideas_hub.config import get_settings


@lru_cache
def _model() -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Local embeddings are not installed. Install Ideas Hub with the local-ai extra: "
            "pip install '.[local-ai]'"
        ) from exc
    return SentenceTransformer(get_settings().embedding_model)


async def embed_text(text: str) -> list[float]:
    def _embed() -> list[float]:
        vector = _model().encode(text, normalize_embeddings=True)
        arr = np.asarray(vector, dtype=np.float32)
        if arr.shape[0] != 1024:
            raise ValueError(f"Embedding model must return 1024 dims, got {arr.shape[0]}")
        return arr.tolist()

    return await asyncio.to_thread(_embed)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    av = np.asarray(a, dtype=np.float32)
    bv = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(av) * np.linalg.norm(bv))
    return float(np.dot(av, bv) / denom) if denom else 0.0
