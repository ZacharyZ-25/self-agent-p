"""Async, public-only boundary between chat requests and the synchronous knowledge index."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.knowledge.retriever import Evidence, KnowledgeRetriever

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeResult:
    evidence: tuple[Evidence, ...]
    status: str
    generation: str | None


class KnowledgeAccess(Protocol):
    async def prepare(self, query: str, history: tuple[str, ...] = ()) -> KnowledgeResult: ...

    async def public_source(self, chunk_id: str) -> Evidence | None: ...


class UnavailableKnowledgeAccess:
    async def prepare(self, query: str, history: tuple[str, ...] = ()) -> KnowledgeResult:
        return KnowledgeResult((), "unavailable", None)

    async def public_source(self, chunk_id: str) -> Evidence | None:
        return None


class LocalKnowledgeAccess:
    def __init__(
        self, retriever: KnowledgeRetriever, *, timeout_seconds: float = 2, max_concurrency: int = 4
    ):
        self.retriever = retriever
        self.timeout_seconds = timeout_seconds
        self._slots = asyncio.Semaphore(max_concurrency)

    async def prepare(self, query: str, history: tuple[str, ...] = ()) -> KnowledgeResult:
        search_text = "\n".join((*history[-2:], query)) if history else query

        def search() -> KnowledgeResult:
            from app.knowledge.evidence_selection import select_answer_evidence

            found = self.retriever.retrieve(search_text)
            allowed = self.retriever.visible_public_ids(
                tuple(item.source_id for item in found.evidence)
            )
            evidence = tuple(item for item in found.evidence if item.source_id in allowed)
            if evidence:
                with self.retriever.repository.connect() as db:
                    catalog = tuple(
                        (row["id"], row["title"])
                        for row in db.execute("SELECT id,title FROM kb_documents").fetchall()
                    )
                evidence = select_answer_evidence(
                    query, evidence, self.retriever.provider, catalog, history=history
                )
            status = found.status
            if status == "embedding_unavailable":
                status = "unavailable"
            elif not evidence and status in ("ok", "keyword_only"):
                status = "no_match"
            return KnowledgeResult(evidence, status, self.retriever.provider.generation)

        try:
            async with self._slots:
                return await asyncio.wait_for(
                    asyncio.to_thread(search), timeout=self.timeout_seconds
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Knowledge preparation unavailable: type=%s", type(exc).__name__)
            return KnowledgeResult((), "unavailable", None)

    async def public_source(self, chunk_id: str) -> Evidence | None:
        try:
            async with self._slots:
                return await asyncio.wait_for(
                    asyncio.to_thread(self.retriever.public_source, chunk_id),
                    timeout=self.timeout_seconds,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Knowledge source unavailable: type=%s", type(exc).__name__)
            return None

    async def prepare_preview(
        self, query: str, history: tuple[str, ...] = ()
    ) -> KnowledgeResult:
        def search() -> KnowledgeResult:
            from app.knowledge.evidence_selection import select_answer_evidence

            search_text = "\n".join((*history[-2:], query)) if history else query
            found = self.retriever.retrieve(search_text, owner_preview=True)
            evidence = found.evidence
            if evidence:
                with self.retriever.repository.connect() as db:
                    catalog = tuple(
                        (row["id"], row["title"])
                        for row in db.execute("SELECT id,title FROM kb_documents").fetchall()
                    )
                evidence = select_answer_evidence(
                    query, evidence, self.retriever.provider, catalog, history=history
                )
            status = "unavailable" if found.status == "embedding_unavailable" else found.status
            if not evidence and status in ("ok", "keyword_only"):
                status = "no_match"
            return KnowledgeResult(evidence, status, self.retriever.provider.generation)

        try:
            async with self._slots:
                return await asyncio.wait_for(
                    asyncio.to_thread(search), timeout=self.timeout_seconds
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Knowledge preview unavailable: type=%s", type(exc).__name__)
            return KnowledgeResult((), "unavailable", None)

    async def owner_source(self, chunk_id: str) -> Evidence | None:
        try:
            async with self._slots:
                return await asyncio.wait_for(
                    asyncio.to_thread(self.retriever.public_source, chunk_id, owner_preview=True),
                    timeout=self.timeout_seconds,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Knowledge owner source unavailable: type=%s", type(exc).__name__)
            return None
