"""Deterministic lexical retrieval with a small cross-language machine glossary."""

import re

import numpy as np

from fibo_ai.rag.ingest import ManualChunk
from fibo_ai.schemas.rag import ManualFragment

CONCEPTS: dict[str, tuple[str, ...]] = {
    "lubrication": (
        "смаз",
        "масл",
        "майлау",
        "май",
        "lubric",
        "oil",
        "润滑",
        "油位",
    ),
    "spindle": ("шпиндел", "spindle", "主轴"),
    "bearing": ("подшипник", "bearing", "轴承"),
    "smoke": ("дым", "түтін", "smoke", "烟"),
    "spark": ("искр", "ұшқын", "spark", "火花"),
    "temperature": ("температур", "перегрев", "қыз", "temperature", "过热"),
    "level": ("уров", "деңгей", "level", "位"),
    "leak": ("теч", "утеч", "ағып", "leak", "泄漏"),
}

TOKEN_RE = re.compile(r"[a-z0-9а-яёәғқңөұүһі]+", re.IGNORECASE)


def _concept_terms(text: str) -> set[str]:
    folded = text.casefold().replace("ё", "е")
    tokens = set(TOKEN_RE.findall(folded))
    for concept, variants in CONCEPTS.items():
        if any(variant in folded for variant in variants):
            tokens.add(concept)
    return tokens


def retrieve_chunks(
    chunks: list[ManualChunk],
    query: str,
    top_k: int = 5,
    query_embedding: list[float] | None = None,
) -> list[ManualFragment]:
    query_terms = _concept_terms(query)
    if not query_terms:
        return []
    ranked: list[tuple[float, ManualChunk]] = []
    for chunk in chunks:
        terms = _concept_terms(f"{chunk.section} {chunk.text}")
        common = query_terms & terms
        lexical_score = len(common) / max(1, len(query_terms))
        if common:
            section_terms = _concept_terms(chunk.section)
            if query_terms & section_terms:
                lexical_score = min(1.0, lexical_score + 0.1)
        if query_embedding and chunk.embedding:
            left = np.asarray(query_embedding, dtype=np.float32)
            right = np.asarray(chunk.embedding, dtype=np.float32)
            semantic = float(np.dot(left, right) / max(1e-12, np.linalg.norm(left) * np.linalg.norm(right)))
            semantic_score = max(0.0, min(1.0, (semantic + 1.0) / 2.0))
            score = 0.75 * semantic_score + 0.25 * lexical_score
        else:
            score = lexical_score
        if score <= 0.0:
            continue
        ranked.append((score, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1].page, item[1].manual_id))
    return [
        ManualFragment(
            page=chunk.page,
            section=chunk.section,
            snippet=chunk.text[:1200],
            score=round(score, 4),
        )
        for score, chunk in ranked[: max(1, min(top_k, 10))]
    ]
