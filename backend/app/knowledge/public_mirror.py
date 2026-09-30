"""Copy only currently published evidence into a dedicated public-read database."""

from __future__ import annotations

from dataclasses import dataclass

from psycopg.types.json import Jsonb

from app.knowledge.embeddings import DIMENSIONS, GENERATION, MODEL, REVISION
from app.knowledge.keywords import indexed_text
from app.knowledge.repository import KnowledgeRepository


@dataclass(frozen=True)
class PublicSnapshot:
    generation: dict
    documents: tuple[dict, ...]
    versions: tuple[dict, ...]
    chunks: tuple[dict, ...]


def read_public_snapshot(source: KnowledgeRepository) -> PublicSnapshot:
    with source.connect() as db:
        generation = db.execute(
            "SELECT id,model,revision,dimensions FROM kb_index_generations WHERE active"
        ).fetchone()
        if generation is None:
            generation = {
                "id": GENERATION, "model": MODEL, "revision": REVISION,
                "dimensions": DIMENSIONS,
            }
        documents = db.execute(
            """SELECT d.id,d.title,d.project,d.fact_type,d.author,d.subject_relation,
                      d.active_version_id,v.source_date,v.effective_at,v.file_type,
                      v.parser_version,v.chunker_version
               FROM kb_documents d JOIN kb_versions v ON v.id=d.active_version_id
               WHERE d.deleted_at IS NULL AND d.published
                 AND d.visibility='public_answer' AND v.state='ready'
               ORDER BY d.id"""
        ).fetchall()
        version_ids = [row["active_version_id"] for row in documents]
        chunks = db.execute(
            """SELECT c.id,c.version_id,c.ordinal,c.body,c.locations,c.token_count,
                      e.model,e.revision,e.dimensions,e.index_generation,
                      e.embedding::text AS embedding
               FROM kb_chunks c JOIN kb_embeddings e ON e.chunk_id=c.id
               WHERE c.version_id=ANY(%s::text[]) AND e.index_generation=%s
               ORDER BY c.version_id,c.ordinal""",
            (version_ids, generation["id"]),
        ).fetchall()
        counts = db.execute(
            """SELECT version_id,count(*) AS total FROM kb_chunks
               WHERE version_id=ANY(%s::text[]) GROUP BY version_id""",
            (version_ids,),
        ).fetchall()
    expected = {row["version_id"]: row["total"] for row in counts}
    actual: dict[str, int] = {}
    for row in chunks:
        actual[row["version_id"]] = actual.get(row["version_id"], 0) + 1
    if any(actual.get(version_id, 0) != expected.get(version_id, 0) for version_id in version_ids):
        raise ValueError("有已发布资料缺少索引片段，取消同步。")
    return PublicSnapshot(
        generation=dict(generation),
        documents=tuple(dict(row) for row in documents),
        versions=tuple(dict(row) for row in documents),
        chunks=tuple(dict(row) for row in chunks),
    )


def initialize_public_mirror(target: KnowledgeRepository) -> None:
    target.migrate()
    with target.connect() as db:
        marker = db.execute("SELECT to_regclass('kb_public_mirror_marker') AS name").fetchone()
        if marker and marker["name"] is not None:
            if db.execute("SELECT 1 FROM kb_public_mirror_marker WHERE id=true").fetchone():
                return
        if db.execute("SELECT 1 FROM kb_documents LIMIT 1").fetchone():
            raise ValueError("目标数据库已有资料；请使用一套独立的空库作为公开镜像。")
        db.execute(
            """CREATE TABLE IF NOT EXISTS kb_public_mirror_marker
               (id boolean PRIMARY KEY CHECK (id), created_at timestamptz NOT NULL DEFAULT now())"""
        )
        db.execute("INSERT INTO kb_public_mirror_marker (id) VALUES (true) ON CONFLICT DO NOTHING")


def public_catalog_version(source: KnowledgeRepository) -> tuple:
    """Small local change token; no remote write while the public catalog is unchanged."""
    with source.connect() as db:
        generation = db.execute(
            "SELECT id FROM kb_index_generations WHERE active"
        ).fetchone()
        rows = db.execute(
            """SELECT d.id,d.active_version_id,d.title,d.project,d.fact_type,
                      d.author,d.subject_relation
               FROM kb_documents d JOIN kb_versions v ON v.id=d.active_version_id
               WHERE d.deleted_at IS NULL AND d.published
                 AND d.visibility='public_answer' AND v.state='ready'
               ORDER BY d.id"""
        ).fetchall()
    return (generation["id"] if generation else None, *(
        tuple(row.values()) for row in rows
    ))


def sync_public_mirror(source: KnowledgeRepository, target: KnowledgeRepository) -> dict:
    if source.dsn == target.dsn:
        raise ValueError("源数据库与公开镜像不能相同。")
    snapshot = read_public_snapshot(source)
    with target.connect() as db:
        marker = db.execute("SELECT to_regclass('kb_public_mirror_marker') AS name").fetchone()
        if not marker or marker["name"] is None:
            raise ValueError("目标数据库尚未初始化为公开镜像。")
        if not db.execute("SELECT 1 FROM kb_public_mirror_marker WHERE id=true").fetchone():
            raise ValueError("目标数据库尚未初始化为公开镜像。")
        db.execute("SELECT pg_advisory_xact_lock(81003)")
        db.execute("UPDATE kb_documents SET active_version_id=NULL")
        for table in (
            "kb_events", "kb_jobs", "kb_embeddings", "kb_chunks", "kb_versions",
            "kb_documents", "kb_pending_uploads", "kb_index_generations",
        ):
            db.execute(f"DELETE FROM {table}")
        gen = snapshot.generation
        db.execute(
            """INSERT INTO kb_index_generations (id,model,revision,dimensions,active)
               VALUES (%s,%s,%s,%s,true)""",
            (gen["id"], gen["model"], gen["revision"], gen["dimensions"]),
        )
        for doc in snapshot.documents:
            db.execute(
                """INSERT INTO kb_documents
                   (id,title,project,fact_type,author,subject_relation,visibility,published)
                   VALUES (%s,%s,%s,%s,%s,%s,'public_answer',true)""",
                (doc["id"], doc["title"], doc["project"], doc["fact_type"],
                 doc["author"], doc["subject_relation"]),
            )
        for version in snapshot.versions:
            version_id = version["active_version_id"]
            db.execute(
                """INSERT INTO kb_versions
                   (id,document_id,fingerprint,content_hash,object_key,file_type,
                    source_date,effective_at,parser_version,chunker_version,state)
                   VALUES (%s,%s,%s,%s,'public-mirror',%s,%s,%s,%s,%s,'ready')""",
                (version_id, version["id"], version_id, version_id,
                 version["file_type"], version["source_date"], version["effective_at"],
                 version["parser_version"], version["chunker_version"]),
            )
        for chunk in snapshot.chunks:
            db.execute(
                """INSERT INTO kb_chunks
                   (id,version_id,ordinal,body,locations,token_count,content_hash,keywords)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,to_tsvector('simple',%s))""",
                (chunk["id"], chunk["version_id"], chunk["ordinal"], chunk["body"],
                 Jsonb(chunk["locations"]), chunk["token_count"], chunk["id"],
                 indexed_text(chunk["body"])),
            )
            db.execute(
                """INSERT INTO kb_embeddings
                   (chunk_id,model,revision,dimensions,index_generation,embedding)
                   VALUES (%s,%s,%s,%s,%s,%s::vector)""",
                (chunk["id"], chunk["model"], chunk["revision"], chunk["dimensions"],
                 chunk["index_generation"], chunk["embedding"]),
            )
        for doc in snapshot.documents:
            db.execute(
                "UPDATE kb_documents SET active_version_id=%s WHERE id=%s",
                (doc["active_version_id"], doc["id"]),
            )
    return {"documents": len(snapshot.documents), "chunks": len(snapshot.chunks)}
