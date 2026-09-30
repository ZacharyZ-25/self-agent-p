"""Keep the answer context focused on the named document and requested fact."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from app.knowledge.embeddings import EmbeddingProvider, validate_vectors
from app.knowledge.retriever import Evidence

_WORD = re.compile(r"[a-z][a-z0-9]{3,}", re.IGNORECASE)
_NAMED_CODE = re.compile(r"\b[a-z]{2,}[a-z0-9]*-\d+[a-z0-9]*\b", re.IGNORECASE)
_GENERIC_LABELS = {
    "baseline", "current", "document", "external", "fixture", "injection",
    "paper", "planning", "private", "project", "report", "study", "test",
    "update", "version",
}
_OVERVIEW = re.compile(
    r"介绍|概述|tell me about|give me an overview|\bvorstellen\b|\büberblick\b",
    re.IGNORECASE,
)
_NUMERIC_ALTERNATIVE = re.compile(r"还是|\bor\b|\boder\b", re.IGNORECASE)
_COUNT_QUESTION = re.compile(r"多少|几次|\bhow many\b|\bwie viele\b", re.IGNORECASE)
_DATE = re.compile(r"\b20\d{2}-\d{1,2}-\d{1,2}\b")
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_MIN_ASPECT_SIMILARITY = 0.18


def _mentions(text: str, token: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(token)}s?(?![a-z0-9])", text, re.I))


def _catalog_subjects(catalog: Sequence[tuple[str, str]]) -> set[str]:
    subjects: set[str] = set()
    for document_id, title in catalog:
        id_parts = re.split(r"[-_]", document_id)
        candidates = [*id_parts, *(_WORD.findall(title)[:1])]
        subjects.update(
            token.casefold()
            for token in candidates
            if len(token) >= 4 and token.casefold() not in _GENERIC_LABELS
        )
    return subjects


def _cosine(left: list[float], right: list[float]) -> float:
    norm = math.sqrt(sum(value * value for value in left))
    norm *= math.sqrt(sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right, strict=True)) / norm if norm else 0.0


def select_answer_evidence(
    query: str,
    evidence: Sequence[Evidence],
    provider: EmbeddingProvider,
    catalog: Sequence[tuple[str, str]],
    *,
    history: Sequence[str] = (),
) -> tuple[Evidence, ...]:
    """Filter unrelated results; an empty result means the answer must abstain."""
    selected = tuple(evidence)
    if not selected:
        return selected

    requested_codes = {match.casefold() for match in _NAMED_CODE.findall(query)}
    if requested_codes and not all(
        any(
            code in f"{item.document_id} {item.title} {item.body}".casefold()
            for item in selected
        )
        for code in requested_codes
    ):
        return ()

    subject_text = "\n".join((*history[-2:], query))
    subjects = {
        token for token in _catalog_subjects(catalog) if _mentions(subject_text, token)
    }
    if subjects:
        selected = tuple(
            item for item in selected
            if any(
                _mentions(item.document_id, token)
                or _mentions(item.title, token)
                or (item.fact_type != "external_reference" and _mentions(item.body, token))
                for token in subjects
            )
        )
    if (
        not selected
        or _OVERVIEW.search(query)
        or (_NUMERIC_ALTERNATIVE.search(query) and len(set(re.findall(r"\d+", query))) >= 2)
    ):
        return selected

    aspect = query
    for token in subjects:
        aspect = re.sub(
            rf"(?<![a-z0-9]){re.escape(token)}s?(?![a-z0-9])", "", aspect, flags=re.I
        )
    aspect = aspect.strip(" ?？.,，。!！")
    if len(aspect) < 4:
        return selected
    try:
        query_vector = provider.embed_query(aspect)
        body_vectors = provider.embed_documents([item.body for item in selected])
        validate_vectors([query_vector, *body_vectors], len(selected) + 1, provider.dimensions)
    except Exception:
        return selected
    ranked = []
    for item, vector in zip(selected, body_vectors, strict=True):
        similarity = _cosine(query_vector, vector)
        count_bonus = 0.0
        if _COUNT_QUESTION.search(query):
            numbers = _NUMBER.findall(_DATE.sub("", item.body))
            if len(numbers) >= 2:
                count_bonus = 0.16
        if similarity + count_bonus < _MIN_ASPECT_SIMILARITY:
            continue
        ranked.append((similarity + count_bonus, item))
    return tuple(item for _, item in sorted(ranked, key=lambda pair: -pair[0]))
