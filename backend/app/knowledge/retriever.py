"""Permission-filtered vector and lexical retrieval with reciprocal-rank fusion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.knowledge.embeddings import EmbeddingProvider, validate_vectors
from app.knowledge.indexer import vector_literal
from app.knowledge.keywords import tsquery
from app.knowledge.repository import KnowledgeRepository


@dataclass(frozen=True)
class Evidence:
    source_id: str
    document_id: str
    version_id: str
    title: str
    body: str
    locations: list[dict]
    token_count: int
    score: float
    channels: tuple[str, ...]
    fact_type: str
    author: str
    subject_relation: str
    effective_at: date


@dataclass(frozen=True)
class Retrieval:
    evidence: tuple[Evidence, ...]
    vector_ids: tuple[str, ...]
    keyword_ids: tuple[str, ...]
    status: str


class KnowledgeRetriever:
    def __init__(
        self,
        repository: KnowledgeRepository,
        provider: EmbeddingProvider,
        *,
        top_k: int = 5,
        token_budget: int = 3000,
        max_per_document: int = 3,
    ):
        self.repository, self.provider = repository, provider
        self.top_k, self.token_budget = top_k, token_budget
        self.max_per_document = max_per_document

    def retrieve(
        self,
        query: str,
        *,
        owner_preview: bool = False,
        history: tuple[str, ...] = (),
        as_of: date | None = None,
        use_vector: bool = True,
    ) -> Retrieval:
        if owner_preview not in (True, False):
            raise ValueError("owner_preview must be a server-owned boolean")
        if not query.strip():
            return Retrieval((), (), (), "empty_query")
        history = history if as_of is not None else ()
        filters = (as_of, list(history), as_of, owner_preview)
        query_vec = None
        if use_vector:
            try:
                query_vec = self.provider.embed_query(query)
                validate_vectors([query_vec], 1, self.provider.dimensions)
            except Exception:
                query_vec = None
        with self.repository.connect() as db:
            active = db.execute("SELECT * FROM kb_index_generations WHERE active").fetchone()
            if not active or (
                active["id"],
                active["model"],
                active["revision"],
                active["dimensions"],
            ) != (
                self.provider.generation,
                self.provider.model,
                self.provider.revision,
                self.provider.dimensions,
            ):
                raise ValueError("ACTIVE_INDEX_MODEL_MISMATCH")
            vector_rows = []
            if query_vec is not None:
                # The visibility predicate is inside this SQL branch, before LIMIT.
                vector_rows = db.execute(
                    """SELECT c.id,c.version_id,d.id AS document_id,
                    d.title,d.fact_type,d.author,d.subject_relation,v.effective_at,
                    c.body,c.locations,c.token_count,
                    e.embedding <=> %s::vector AS distance
                    FROM kb_chunks c JOIN kb_versions v ON v.id=c.version_id
                    JOIN kb_documents d ON d.id=v.document_id
                    JOIN kb_embeddings e ON e.chunk_id=c.id
                    WHERE e.index_generation=%s AND d.deleted_at IS NULL
                      AND v.state='ready'
                      AND ((d.active_version_id=v.id AND
                            (%s::date IS NULL OR v.effective_at<=%s::date)) OR (
                          %s::date IS NOT NULL AND v.id=ANY(%s::text[])
                          AND v.effective_at<=%s::date))
                      AND (%s OR (d.published AND d.visibility='public_answer'))
                    ORDER BY distance,c.id LIMIT 20""",
                    (vector_literal(query_vec), active["id"], as_of, as_of, *filters),
                ).fetchall()
            lexical = tsquery(query)
            keyword_rows = []
            if lexical:
                keyword_rows = db.execute(
                    """SELECT c.id,c.version_id,d.id AS document_id,
                    d.title,d.fact_type,d.author,d.subject_relation,v.effective_at,
                    c.body,c.locations,c.token_count,
                    ts_rank(c.keywords,to_tsquery('simple',%s)) AS rank
                    FROM kb_chunks c JOIN kb_versions v ON v.id=c.version_id
                    JOIN kb_documents d ON d.id=v.document_id
                    WHERE d.deleted_at IS NULL AND v.state='ready'
                      AND ((d.active_version_id=v.id AND
                            (%s::date IS NULL OR v.effective_at<=%s::date)) OR (
                          %s::date IS NOT NULL AND v.id=ANY(%s::text[])
                          AND v.effective_at<=%s::date))
                      AND (%s OR (d.published AND d.visibility='public_answer'))
                      AND c.keywords @@ to_tsquery('simple',%s)
                    ORDER BY rank DESC,c.id LIMIT 20""",
                    (lexical, as_of, as_of, *filters, lexical),
                ).fetchall()
        scores: dict[str, float] = {}
        rows: dict[str, dict] = {}
        channels: dict[str, set[str]] = {}
        for channel, matches in (("vector", vector_rows), ("keyword", keyword_rows)):
            for rank, row in enumerate(matches, 1):
                key = row["id"]
                rows[key] = row
                scores[key] = scores.get(key, 0.0) + 1 / (60 + rank)
                channels.setdefault(key, set()).add(channel)
        candidates = [
            Evidence(
                source_id=key,
                document_id=rows[key]["document_id"],
                version_id=rows[key]["version_id"],
                title=rows[key]["title"],
                body=rows[key]["body"],
                locations=rows[key]["locations"],
                token_count=rows[key]["token_count"],
                score=scores[key],
                channels=tuple(sorted(channels[key])),
                fact_type=rows[key]["fact_type"],
                author=rows[key]["author"],
                subject_relation=rows[key]["subject_relation"],
                effective_at=rows[key]["effective_at"],
            )
            for key in sorted(rows, key=lambda k: (-scores[k], k))
        ]
        if query_vec is not None and candidates:
            from app.knowledge.evidence_selection import select_answer_evidence

            with self.repository.connect() as db:
                catalog = tuple(
                    (row["id"], row["title"])
                    for row in db.execute("SELECT id,title FROM kb_documents").fetchall()
                )
            candidates = list(select_answer_evidence(query, candidates, self.provider, catalog))
        result: list[Evidence] = []
        per_document: dict[str, int] = {}
        used_tokens = 0
        for item in candidates:
            if per_document.get(item.document_id, 0) >= self.max_per_document:
                continue
            if used_tokens + item.token_count > self.token_budget:
                continue
            result.append(item)
            per_document[item.document_id] = per_document.get(item.document_id, 0) + 1
            used_tokens += item.token_count
            if len(result) >= self.top_k:
                break
        status = (
            ("keyword_only" if query_vec is None else "ok")
            if result
            else ("embedding_unavailable" if query_vec is None else "no_match")
        )
        return Retrieval(
            tuple(result),
            tuple(r["id"] for r in vector_rows),
            tuple(r["id"] for r in keyword_rows),
            status,
        )

    def visible_public_ids(self, ids: tuple[str, ...]) -> set[str]:
        if not ids:
            return set()
        with self.repository.connect() as db:
            rows = db.execute(
                """SELECT c.id FROM kb_chunks c
                JOIN kb_versions v ON v.id=c.version_id
                JOIN kb_documents d ON d.id=v.document_id
                JOIN kb_embeddings e ON e.chunk_id=c.id
                JOIN kb_index_generations g ON g.id=e.index_generation AND g.active
                WHERE c.id=ANY(%s::text[]) AND d.deleted_at IS NULL
                  AND d.published AND d.visibility='public_answer'
                  AND d.active_version_id=v.id AND v.state='ready'""",
                (list(ids),),
            ).fetchall()
        return {row["id"] for row in rows}

    def public_source(self, chunk_id: str, *, owner_preview: bool = False) -> Evidence | None:
        with self.repository.connect() as db:
            row = db.execute(
                """SELECT c.id,c.version_id,d.id AS document_id,
                d.title,d.fact_type,d.author,d.subject_relation,v.effective_at,
                c.body,c.locations,c.token_count FROM kb_chunks c
                JOIN kb_versions v ON v.id=c.version_id
                JOIN kb_documents d ON d.id=v.document_id
                JOIN kb_embeddings e ON e.chunk_id=c.id
                JOIN kb_index_generations g ON g.id=e.index_generation AND g.active
                WHERE c.id=%s AND d.deleted_at IS NULL
                  AND (%s OR (d.published AND d.visibility='public_answer'))
                  AND d.active_version_id=v.id AND v.state='ready'
                LIMIT 1""",
                (chunk_id, owner_preview),
            ).fetchone()
        if not row:
            return None
        return Evidence(
            source_id=row["id"],
            document_id=row["document_id"],
            version_id=row["version_id"],
            title=row["title"],
            body=row["body"],
            locations=row["locations"],
            token_count=row["token_count"],
            score=0,
            channels=(),
            fact_type=row["fact_type"],
            author=row["author"],
            subject_relation=row["subject_relation"],
            effective_at=row["effective_at"],
        )
