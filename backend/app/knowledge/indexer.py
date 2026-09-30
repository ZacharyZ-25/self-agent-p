"""Build complete version indexes before making a version current."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from app.knowledge.embeddings import EmbeddingProvider, validate_vectors
from app.knowledge.keywords import indexed_text
from app.knowledge.repository import KnowledgeRepository


def vector_literal(values: Iterable[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


class KnowledgeIndexer:
    def __init__(self, repository: KnowledgeRepository, provider: EmbeddingProvider):
        self.repository, self.provider = repository, provider

    def ensure_generation(self, *, active: bool = True) -> None:
        with self.repository.connect() as db:
            row = db.execute(
                "SELECT * FROM kb_index_generations WHERE id=%s FOR UPDATE",
                (self.provider.generation,),
            ).fetchone()
            if row:
                if (row["model"], row["revision"], row["dimensions"]) != (
                    self.provider.model,
                    self.provider.revision,
                    self.provider.dimensions,
                ):
                    raise ValueError("INDEX_GENERATION_MODEL_MISMATCH")
            else:
                current = db.execute("SELECT id FROM kb_index_generations WHERE active").fetchone()
                db.execute(
                    """INSERT INTO kb_index_generations
                    (id,model,revision,dimensions,active) VALUES (%s,%s,%s,%s,%s)""",
                    (
                        self.provider.generation,
                        self.provider.model,
                        self.provider.revision,
                        self.provider.dimensions,
                        active and current is None,
                    ),
                )

    def index_version(self, version_id: str) -> dict:
        self.ensure_generation()
        with self.repository.connect() as db:
            version = db.execute(
                """SELECT v.id,v.state,v.document_id,
                v.auto_activate,v.auto_publish,d.title,d.project
                FROM kb_versions v JOIN kb_documents d ON d.id=v.document_id
                WHERE v.id=%s AND d.deleted_at IS NULL""",
                (version_id,),
            ).fetchone()
            if not version or version["state"] not in ("awaiting_embedding", "ready"):
                raise ValueError("VERSION_NOT_EXTRACTED")
            chunks = db.execute(
                """SELECT id,body FROM kb_chunks WHERE version_id=%s
                ORDER BY ordinal""",
                (version_id,),
            ).fetchall()
        if not chunks:
            raise ValueError("EMPTY_CHUNKS")
        texts = [f"{version['title']} {version['project'] or ''}\n{c['body']}" for c in chunks]
        vectors = self.provider.embed_documents(texts)
        validate_vectors(vectors, len(chunks), self.provider.dimensions)
        with self.repository.connect() as db:
            locked = db.execute(
                """SELECT v.state,d.deleted_at FROM kb_versions v
                JOIN kb_documents d ON d.id=v.document_id WHERE v.id=%s FOR UPDATE OF v,d""",
                (version_id,),
            ).fetchone()
            if (
                not locked
                or locked["deleted_at"]
                or locked["state"] not in ("awaiting_embedding", "ready")
            ):
                raise ValueError("VERSION_CHANGED_DURING_EMBEDDING")
            ids = [
                r["id"]
                for r in db.execute(
                    "SELECT id FROM kb_chunks WHERE version_id=%s ORDER BY ordinal", (version_id,)
                ).fetchall()
            ]
            if ids != [c["id"] for c in chunks]:
                raise ValueError("CHUNKS_CHANGED_DURING_EMBEDDING")
            for chunk, embedding in zip(chunks, vectors, strict=True):
                db.execute(
                    """UPDATE kb_chunks SET keywords=to_tsvector('simple',%s)
                    WHERE id=%s""",
                    (indexed_text(chunk["body"]), chunk["id"]),
                )
                db.execute(
                    """INSERT INTO kb_embeddings
                    (chunk_id,model,revision,dimensions,index_generation,embedding)
                    VALUES (%s,%s,%s,%s,%s,%s::vector)
                    ON CONFLICT (chunk_id,index_generation) DO UPDATE SET
                    embedding=EXCLUDED.embedding,model=EXCLUDED.model,
                    revision=EXCLUDED.revision,dimensions=EXCLUDED.dimensions""",
                    (
                        chunk["id"],
                        self.provider.model,
                        self.provider.revision,
                        self.provider.dimensions,
                        self.provider.generation,
                        vector_literal(embedding),
                    ),
                )
            db.execute("UPDATE kb_versions SET state='ready' WHERE id=%s", (version_id,))
            db.execute(
                """UPDATE kb_jobs SET stage='ready',lease_token=NULL,lease_until=NULL
                WHERE version_id=%s""",
                (version_id,),
            )
            db.execute(
                """INSERT INTO kb_events (document_id,version_id,action,actor)
                VALUES (%s,%s,'indexed','indexer')""",
                (version["document_id"], version_id),
            )
        if version["auto_activate"]:
            self.activate_version(version_id, publish=version["auto_publish"], actor="admin-worker")
        return {
            "version_id": version_id,
            "chunks": len(chunks),
            "generation": self.provider.generation,
            "state": "ready",
            "activated": version["auto_activate"],
        }

    def index_pending(self) -> dict | None:
        with self.repository.connect() as db:
            job = db.execute("""SELECT j.id,j.version_id FROM kb_jobs j
                JOIN kb_versions v ON v.id=j.version_id
                JOIN kb_documents d ON d.id=v.document_id
                WHERE (j.stage='extracted' OR
                       (j.stage='embedding' AND j.lease_until<now()))
                  AND j.available_at<=now()
                  AND j.attempts<j.max_attempts AND d.deleted_at IS NULL
                ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1""").fetchone()
            if not job:
                return None
            db.execute(
                """UPDATE kb_jobs SET stage='embedding',attempts=attempts+1,
                lease_until=now()+interval '10 minutes' WHERE id=%s""",
                (job["id"],),
            )
        try:
            return self.index_version(job["version_id"])
        except Exception as exc:
            with self.repository.connect() as db:
                row = db.execute(
                    "SELECT attempts,max_attempts FROM kb_jobs WHERE id=%s FOR UPDATE", (job["id"],)
                ).fetchone()
                stage = "failed" if row["attempts"] >= row["max_attempts"] else "extracted"
                db.execute(
                    """UPDATE kb_jobs SET stage=%s,error_code=%s,lease_until=NULL,
                    available_at=now()+(%s * interval '1 second') WHERE id=%s""",
                    (
                        stage,
                        type(exc).__name__,
                        min(
                            60, self.repository.settings.retry_seconds * 2 ** (row["attempts"] - 1)
                        ),
                        job["id"],
                    ),
                )
                if stage == "failed":
                    db.execute(
                        "UPDATE kb_versions SET state='failed' WHERE id=%s", (job["version_id"],)
                    )
            raise

    def activate_version(
        self, version_id: str, *, publish: bool = False, actor: str = "local-cli"
    ) -> None:
        with self.repository.connect() as db:
            row = db.execute(
                """SELECT v.*,d.active_version_id,d.visibility,d.deleted_at
                FROM kb_versions v JOIN kb_documents d ON d.id=v.document_id
                WHERE v.id=%s FOR UPDATE OF v,d""",
                (version_id,),
            ).fetchone()
            if not row or row["deleted_at"] or row["state"] != "ready":
                raise ValueError("VERSION_NOT_READY")
            generation = db.execute("SELECT id FROM kb_index_generations WHERE active").fetchone()
            if not generation or generation["id"] != self.provider.generation:
                raise ValueError("INDEX_GENERATION_NOT_ACTIVE")
            if row["effective_at"] > date.today():
                raise ValueError("VERSION_NOT_YET_EFFECTIVE")
            active = row["active_version_id"]
            if active and active != version_id:
                if row["replaces"] != active:
                    raise ValueError("REPLACEMENT_MUST_TARGET_CURRENT_VERSION")
                current = db.execute(
                    "SELECT effective_at FROM kb_versions WHERE id=%s", (active,)
                ).fetchone()
                if row["effective_at"] < current["effective_at"]:
                    raise ValueError("ARCHIVE_CANNOT_REPLACE_CURRENT_VERSION")
            elif not active and row["replaces"]:
                raise ValueError("REPLACEMENT_WITHOUT_CURRENT_VERSION")
            count = db.execute(
                "SELECT count(*) AS n FROM kb_chunks WHERE version_id=%s", (version_id,)
            ).fetchone()["n"]
            indexed = db.execute(
                """SELECT count(*) AS n FROM kb_embeddings e
                JOIN kb_chunks c ON c.id=e.chunk_id
                WHERE c.version_id=%s AND e.index_generation=%s""",
                (version_id, self.provider.generation),
            ).fetchone()["n"]
            if not count or indexed != count:
                raise ValueError("INCOMPLETE_INDEX")
            if publish and row["visibility"] != "public_answer":
                raise ValueError("PRIVATE_DOCUMENT_CANNOT_BE_PUBLISHED")
            db.execute(
                """UPDATE kb_documents SET active_version_id=%s,
                published=CASE WHEN %s THEN true ELSE published END WHERE id=%s""",
                (version_id, publish, row["document_id"]),
            )
            db.execute(
                """INSERT INTO kb_events (document_id,version_id,action,actor)
                VALUES (%s,%s,%s,%s)""",
                (row["document_id"], version_id, "published" if publish else "activated", actor),
            )

    def set_published(self, document_id: str, published: bool, actor: str = "local-cli") -> None:
        with self.repository.connect() as db:
            row = db.execute(
                "SELECT * FROM kb_documents WHERE id=%s FOR UPDATE", (document_id,)
            ).fetchone()
            if not row or row["deleted_at"]:
                raise ValueError("DOCUMENT_NOT_FOUND")
            if published and row["active_version_id"] is None:
                raise ValueError("DOCUMENT_NOT_PUBLISHABLE")
            db.execute(
                """UPDATE kb_documents SET published=%s,
                visibility=CASE WHEN %s THEN 'public_answer' ELSE visibility END
                WHERE id=%s""",
                (published, published, document_id),
            )
            db.execute(
                """INSERT INTO kb_events (document_id,version_id,action,actor)
                VALUES (%s,%s,%s,%s)""",
                (
                    document_id,
                    row["active_version_id"],
                    "published" if published else "unpublished",
                    actor,
                ),
            )

    def delete_document(self, document_id: str, actor: str = "local-cli") -> None:
        with self.repository.connect() as db:
            row = db.execute(
                "SELECT active_version_id FROM kb_documents WHERE id=%s FOR UPDATE", (document_id,)
            ).fetchone()
            if not row:
                raise ValueError("DOCUMENT_NOT_FOUND")
            db.execute(
                """UPDATE kb_documents SET published=false,active_version_id=NULL,
                deleted_at=now() WHERE id=%s""",
                (document_id,),
            )
            db.execute(
                """INSERT INTO kb_events (document_id,version_id,action,actor)
                VALUES (%s,%s,'deleted',%s)""",
                (document_id, row["active_version_id"], actor),
            )

    def activate_generation(self) -> None:
        """Switch only when every current version is fully indexed in this generation."""
        with self.repository.connect() as db:
            missing = db.execute(
                """SELECT d.id FROM kb_documents d
                JOIN kb_chunks c ON c.version_id=d.active_version_id
                LEFT JOIN kb_embeddings e ON e.chunk_id=c.id AND e.index_generation=%s
                WHERE d.deleted_at IS NULL AND e.chunk_id IS NULL LIMIT 1""",
                (self.provider.generation,),
            ).fetchone()
            if missing:
                raise ValueError("GENERATION_INCOMPLETE")
            db.execute("UPDATE kb_index_generations SET active=false WHERE active")
            db.execute(
                "UPDATE kb_index_generations SET active=true WHERE id=%s",
                (self.provider.generation,),
            )
