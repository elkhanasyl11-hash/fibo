"""Optional local multilingual E5 embedding adapter."""

from pathlib import Path
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray


class TextEmbedder(Protocol):
    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> NDArray[np.float32]: ...


class MultilingualE5Small:
    model_name = "intfloat/multilingual-e5-small"

    def __init__(self, cache_dir: Path) -> None:
        from sentence_transformers import SentenceTransformer

        cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = SentenceTransformer(
            self.model_name,
            cache_folder=str(cache_dir),
            device="cpu",
        )

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            [f"passage: {text}" for text in texts],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return cast(list[list[float]], np.asarray(vectors, dtype=np.float32).tolist())

    def embed_query(self, text: str) -> NDArray[np.float32]:
        vector = self._model.encode(
            f"query: {text}",
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vector, dtype=np.float32).reshape(-1)
