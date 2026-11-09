"""Fibo Assistant: the Chroma vector store (persistent, in data/chroma/).

Two collections, cosine distance, vectors supplied by our own embedder (Chroma's built-in
embedding function is not used):
  manuals     chunks of uploaded PDF manuals, filtered by machine_id; metadata page for citations
  profile_kb  short symptom -> cause -> action notes per industry profile, filtered by profile
Telemetry is switched off. One client per process (lazy singleton).
"""

import logging
import threading

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings

logger = logging.getLogger("fibo.assistant.chroma")
_client = None
_lock = threading.Lock()


def client():
    global _client
    with _lock:
        if _client is None:
            settings.chroma_dir.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(
                path=str(settings.chroma_dir), settings=ChromaSettings(anonymized_telemetry=False)
            )
        return _client


def _collection(name: str):
    return client().get_or_create_collection(name, embedding_function=None, metadata={"hnsw:space": "cosine"})


def manuals_collection():
    return _collection("manuals")


def kb_collection():
    return _collection("profile_kb")


def reachable() -> bool:
    try:
        client().heartbeat()
    except Exception:  # reported by /health as "error" and logged
        logger.exception("chroma is not reachable")
        return False
    return True
