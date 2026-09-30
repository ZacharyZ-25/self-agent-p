"""Independent embedding interface; the local multilingual model is opt-in."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "fastembed-0.7.4-mean-pooling"
DIMENSIONS = 384
GENERATION = "multilingual-minilm-l12-v1"


class EmbeddingProvider(Protocol):
    model: str
    revision: str
    dimensions: int
    generation: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class LocalMultilingualEmbeddings:
    model = MODEL
    revision = REVISION
    dimensions = DIMENSIONS
    generation = GENERATION

    def __init__(self, cache_dir: Path | None = None):
        from fastembed import TextEmbedding

        if cache_dir is None:
            cache_dir = Path(os.environ.get(
                "KB_MODEL_CACHE_DIR",
                Path(__file__).resolve().parents[3] / "knowledge-data/model-cache",
            ))
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = TextEmbedding(model_name=MODEL, cache_dir=str(cache_dir))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(self._model.query_embed(text)).tolist()


def validate_vectors(vectors: list[list[float]], count: int, dimensions: int) -> None:
    if len(vectors) != count or any(len(v) != dimensions for v in vectors):
        raise ValueError("EMBEDDING_DIMENSION_MISMATCH")
