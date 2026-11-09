"""Fibo Assistant: text -> vector (embedding) for manual search.

E5Embedder runs intfloat/multilingual-e5-small (Russian + Kazakh + English) with onnxruntime:
  1. tokenize (the model's own tokenizer.json), max 512 tokens;
  2. run the ONNX model -> one vector per token;
  3. mean over the real tokens (padding ignored) -> one 384-number vector per text;
  4. L2-normalise, so cosine similarity = dot product.
e5 was trained with prefixes: manual chunks are embedded as "passage: …", questions as "query: …".
We use the official int8 ONNX export (118 MB) instead of sentence-transformers + PyTorch, which
would need ~1 GB of disk for the same model (docs/decisions.md). The files are downloaded once from
Hugging Face into data/models/ (or at Docker build time) and loaded once per process.

HashEmbedder is a deterministic offline stand-in for tests (FIBO_EMBEDDING_BACKEND=hash): each word
stem is hashed into one of 512 slots. It only measures word overlap, which is enough to test the
indexing and retrieval code without downloading a model.
"""

import hashlib
import logging
import re
import threading
from pathlib import Path
from typing import Protocol

import numpy as np

from app.core.config import settings
from app.core.errors import ModelUnavailableError

logger = logging.getLogger("fibo.assistant.embeddings")

TOKENIZER_FILE = "onnx/tokenizer.json"
MAX_TOKENS = 512
BATCH_SIZE = 16


class Embedder(Protocol):
    def embed_passages(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def _normalise(vectors: np.ndarray) -> np.ndarray:
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)


class E5Embedder:
    def __init__(self, model_dir: Path) -> None:
        import onnxruntime  # imported here so the hash backend (tests) never needs them
        from tokenizers import Tokenizer

        self.tokenizer = Tokenizer.from_file(str(model_dir / TOKENIZER_FILE))
        self.tokenizer.enable_truncation(MAX_TOKENS)
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id("<pad>"), pad_token="<pad>")
        self.session = onnxruntime.InferenceSession(
            str(model_dir / settings.embedding_model_file), providers=["CPUExecutionProvider"]
        )
        self.input_names = {item.name for item in self.session.get_inputs()}

    def _embed(self, texts: list[str]) -> np.ndarray:
        vectors = []
        for start in range(0, len(texts), BATCH_SIZE):
            encodings = self.tokenizer.encode_batch(texts[start : start + BATCH_SIZE])
            ids = np.array([e.ids for e in encodings], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.input_names:
                feeds["token_type_ids"] = np.zeros_like(ids)
            hidden = self.session.run(None, feeds)[0]  # (batch, tokens, 384)
            summed = (hidden * mask[..., None]).sum(axis=1)
            vectors.append(summed / np.maximum(mask.sum(axis=1, keepdims=True), 1))
        return _normalise(np.vstack(vectors))

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embed([f"passage: {t}" for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([f"query: {text}"])[0]


class HashEmbedder:
    dimensions = 512

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimensions)
        for word in re.findall(r"\w+", text.lower().replace("ё", "е")):
            stem = word[:6]  # crude stemming: "подшипника" and "подшипники" share a slot
            vector[int(hashlib.md5(stem.encode()).hexdigest(), 16) % self.dimensions] += 1
        return vector

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return _normalise(np.array([self._vector(t) for t in texts]))

    def embed_query(self, text: str) -> np.ndarray:
        return _normalise(np.array([self._vector(text)]))[0]


def model_dir() -> Path:
    return settings.models_dir / settings.embedding_model_repo.replace("/", "__")


def download_model() -> Path:
    """Fetch the ONNX model + tokenizer from Hugging Face once (≈135 MB)."""
    from huggingface_hub import hf_hub_download

    target = model_dir()
    for filename in (settings.embedding_model_file, TOKENIZER_FILE):
        if not (target / filename).exists():
            logger.info("downloading embedding model file", extra={"file": filename})
            hf_hub_download(settings.embedding_model_repo, filename, local_dir=target)
    return target


_embedder: Embedder | None = None
_lock = threading.Lock()  # indexing runs in worker threads; load the model only once


def get_embedder() -> Embedder:
    """The process-wide embedder (lazy singleton). CPU work: call its methods via asyncio.to_thread."""
    global _embedder
    with _lock:
        if _embedder is None:
            if settings.embedding_backend == "hash":
                _embedder = HashEmbedder()
            else:
                try:
                    _embedder = E5Embedder(download_model())
                except Exception as exc:  # converted: no network on first use, broken file, ...
                    raise ModelUnavailableError(
                        "Embedding model is not available",
                        details={"model": settings.embedding_model_repo, "reason": type(exc).__name__},
                    ) from exc
        return _embedder


if __name__ == "__main__":  # python -m app.modules.assistant.embeddings  (pre-download, e.g. in Docker)
    print(f"model files in {download_model()}")
