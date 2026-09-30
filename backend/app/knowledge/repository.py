from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from app.knowledge.chunker import CHUNKER_VERSION
from app.knowledge.parsers import PARSER_VERSION, SUPPORTED
from app.knowledge.settings import KnowledgeSettings
from app.knowledge.storage import ObjectStore, object_key


@dataclass(frozen=True)
class Upload:
    document_id: str
    title: str
    project: str | None
    fact_type: str
    author: str
    subject_relation: str
    visibility: str
    source_date: str
    effective_at: str
    data: bytes
    suffix: str
    replaces: str | None = None
    actor: str = "local-cli"
    auto_activate: bool = False
    auto_publish: bool = False


class KnowledgeRepository:
    def __init__(self, settings: KnowledgeSettings, store: ObjectStore):
        self.settings, self.store = settings, store
        self.dsn = settings.database_url.get_secret_value()

    def connect(self):
        options = {"cursor_factory": psycopg.ClientCursor} if self.settings.pglite_compat else {}
        return psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=10, **options)

    def migrate(self) -> None:
        with self.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(81001)")
            db.execute("CREATE TABLE IF NOT EXISTS kb_schema_migrations (version text PRIMARY KEY)")
            for version, filename in (
                ("001", "001_ingestion.sql"),
                ("002", "002_retrieval.sql"),
                ("003", "003_embedding_jobs.sql"),
                ("004", "004_admin.sql"),
            ):
                applied = db.execute(
                    "SELECT 1 FROM kb_schema_migrations WHERE version=%s", (version,)
                ).fetchone()
                if applied:
                    continue
                sql = resources.files("app.knowledge.migrations").joinpath(filename).read_text()
                db.execute(sql)
                db.execute("INSERT INTO kb_schema_migrations (version) VALUES (%s)", (version,))

    def submit(self, upload: Upload) -> dict:
        if not upload.document_id or len(upload.document_id) > 128:
            raise ValueError("document_id must contain 1-128 characters")
        if not upload.title.strip() or len(upload.title) > 240:
            raise ValueError("title must contain 1-240 characters")
        if upload.suffix not in SUPPORTED:
            raise ValueError("Only .md, .txt, .pdf, .docx are supported")
        if len(upload.data) > self.settings.max_file_bytes:
            raise ValueError("FILE_TOO_LARGE")
        from datetime import date

        date.fromisoformat(upload.source_date)
        date.fromisoformat(upload.effective_at)
        content_hash = hashlib.sha256(upload.data).hexdigest()
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "document": upload.document_id,
                    "content": content_hash,
                    "type": upload.suffix,
                    "source_date": upload.source_date,
                    "effective_at": upload.effective_at,
                    "replaces": upload.replaces,
                    "parser": PARSER_VERSION,
                    "chunker": CHUNKER_VERSION,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        with self.connect() as db:
            db.execute(
                """INSERT INTO kb_documents
                (id,title,project,fact_type,author,subject_relation,visibility)
                VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (
                    upload.document_id,
                    upload.title,
                    upload.project,
                    upload.fact_type,
                    upload.author,
                    upload.subject_relation,
                    upload.visibility,
                ),
            )
            doc = db.execute(
                "SELECT * FROM kb_documents WHERE id=%s FOR UPDATE", (upload.document_id,)
            ).fetchone()
            if doc["deleted_at"]:
                raise ValueError("DOCUMENT_DELETED")
            for key in ("project", "fact_type", "author", "subject_relation", "visibility"):
                if doc[key] != getattr(upload, key):
                    raise ValueError(f"Document metadata differs: {key}")
            existing = db.execute(
                """SELECT v.id AS version_id,j.id AS job_id,j.stage
                FROM kb_versions v JOIN kb_jobs j ON j.version_id=v.id
                WHERE v.document_id=%s AND v.fingerprint=%s""",
                (upload.document_id, fingerprint),
            ).fetchone()
            if existing:
                return {**existing, "document_id": upload.document_id, "reused": True}
            if upload.replaces:
                previous = db.execute(
                    """SELECT id FROM kb_versions
                    WHERE id=%s AND document_id=%s""",
                    (upload.replaces, upload.document_id),
                ).fetchone()
                if not previous:
                    raise ValueError("Replacement must belong to this document")
            version_id, job_id, key = uuid4().hex, uuid4().hex, object_key(upload.suffix)
            self.store.put(key, upload.data)
            db.execute(
                """INSERT INTO kb_versions
                (id,document_id,fingerprint,content_hash,object_key,file_type,source_date,
                 effective_at,replaces,parser_version,chunker_version,
                 auto_activate,auto_publish)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    version_id,
                    upload.document_id,
                    fingerprint,
                    content_hash,
                    key,
                    upload.suffix,
                    upload.source_date,
                    upload.effective_at,
                    upload.replaces,
                    PARSER_VERSION,
                    CHUNKER_VERSION,
                    upload.auto_activate,
                    upload.auto_publish,
                ),
            )
            db.execute(
                """INSERT INTO kb_jobs (id,version_id,max_attempts,pipeline_version)
                VALUES (%s,%s,%s,%s)""",
                (
                    job_id,
                    version_id,
                    self.settings.max_attempts,
                    f"{PARSER_VERSION}/{CHUNKER_VERSION}",
                ),
            )
            db.execute(
                """INSERT INTO kb_events (document_id,version_id,action,actor)
                VALUES (%s,%s,'submitted',%s)""",
                (upload.document_id, version_id, upload.actor),
            )
            return {
                "document_id": upload.document_id,
                "version_id": version_id,
                "job_id": job_id,
                "stage": "queued",
                "reused": False,
            }

    def claim(self, job_id: str | None = None) -> dict | None:
        with self.connect() as db:
            job = db.execute(
                """SELECT j.*, v.object_key, v.file_type, v.parsed_blocks,
                       v.document_id
                FROM kb_jobs j JOIN kb_versions v ON v.id=j.version_id
                JOIN kb_documents d ON d.id=v.document_id
                WHERE j.stage IN ('queued','parsing','chunking')
                  AND d.deleted_at IS NULL
                  AND j.attempts<j.max_attempts AND j.available_at<=now()
                  AND (j.lease_until IS NULL OR j.lease_until<now())
                  AND (%s::text IS NULL OR j.id=%s)
                ORDER BY j.available_at,j.created_at
                FOR UPDATE OF j SKIP LOCKED LIMIT 1""",
                (job_id, job_id),
            ).fetchone()
            if not job:
                return None
            token = uuid4().hex
            stage = "chunking" if job["parsed_blocks"] is not None else "parsing"
            db.execute(
                """UPDATE kb_jobs SET lease_token=%s,
                lease_until=now()+(%s * interval '1 second'), heartbeat_at=now(),
                attempts=attempts+1,stage=%s,error_code=NULL WHERE id=%s""",
                (token, self.settings.lease_seconds, stage, job["id"]),
            )
            db.execute("UPDATE kb_versions SET state=%s WHERE id=%s", (stage, job["version_id"]))
            return {**job, "lease_token": token, "stage": stage}

    def heartbeat(self, job_id: str, token: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                """UPDATE kb_jobs SET heartbeat_at=now(),
                lease_until=now()+(%s * interval '1 second')
                WHERE id=%s AND lease_token=%s AND lease_until>now()
                RETURNING id""",
                (self.settings.lease_seconds, job_id, token),
            ).fetchone()
            return bool(row)

    def save_blocks(self, job: dict, blocks: list[dict]) -> None:
        with self.connect() as db:
            lease = db.execute(
                """SELECT j.id FROM kb_jobs j JOIN kb_versions v ON v.id=j.version_id
                JOIN kb_documents d ON d.id=v.document_id
                WHERE j.id=%s AND j.lease_token=%s AND j.lease_until>now()
                  AND d.deleted_at IS NULL FOR UPDATE OF j,d""",
                (job["id"], job["lease_token"]),
            ).fetchone()
            if not lease:
                raise RuntimeError("JOB_LEASE_LOST")
            db.execute(
                "UPDATE kb_versions SET parsed_blocks=%s,state='chunking' WHERE id=%s",
                (json.dumps(blocks, ensure_ascii=False), job["version_id"]),
            )
            db.execute("UPDATE kb_jobs SET stage='chunking' WHERE id=%s", (job["id"],))

    def save_chunks(self, job: dict, chunks: list[dict]) -> None:
        with self.connect() as db:
            lease = db.execute(
                """SELECT j.id FROM kb_jobs j JOIN kb_versions v ON v.id=j.version_id
                JOIN kb_documents d ON d.id=v.document_id
                WHERE j.id=%s AND j.lease_token=%s AND j.lease_until>now()
                  AND d.deleted_at IS NULL FOR UPDATE OF j,d""",
                (job["id"], job["lease_token"]),
            ).fetchone()
            if not lease:
                raise RuntimeError("JOB_LEASE_LOST")
            db.execute("DELETE FROM kb_chunks WHERE version_id=%s", (job["version_id"],))
            for n, part in enumerate(chunks):
                db.execute(
                    """INSERT INTO kb_chunks
                    (id,version_id,ordinal,body,locations,token_count,content_hash,keywords)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,to_tsvector('simple',%s))""",
                    (
                        uuid4().hex,
                        job["version_id"],
                        n,
                        part["body"],
                        json.dumps(part["locations"], ensure_ascii=False),
                        part["token_count"],
                        part["content_hash"],
                        part["body"],
                    ),
                )
            db.execute(
                """UPDATE kb_versions SET parsed_blocks=NULL,state='awaiting_embedding'
                WHERE id=%s""",
                (job["version_id"],),
            )
            db.execute(
                """UPDATE kb_jobs SET stage='extracted',lease_token=NULL,
                lease_until=NULL,heartbeat_at=NULL WHERE id=%s""",
                (job["id"],),
            )
            db.execute(
                """INSERT INTO kb_events (document_id,version_id,action,actor,details)
                VALUES (%s,%s,'extracted','worker',%s)""",
                (job["document_id"], job["version_id"], json.dumps({"chunks": len(chunks)})),
            )

    def fail(self, job: dict, code: str, *, review: bool = False) -> None:
        with self.connect() as db:
            row = db.execute(
                """SELECT attempts,max_attempts FROM kb_jobs
                WHERE id=%s AND lease_token=%s FOR UPDATE""",
                (job["id"], job["lease_token"]),
            ).fetchone()
            if not row:
                return
            stage = (
                "needs_review"
                if review
                else ("failed" if row["attempts"] >= row["max_attempts"] else "queued")
            )
            delay = min(60, self.settings.retry_seconds * 2 ** max(0, row["attempts"] - 1))
            db.execute(
                """UPDATE kb_jobs SET stage=%s,error_code=%s,lease_token=NULL,
                lease_until=NULL,heartbeat_at=NULL,
                available_at=now()+(%s * interval '1 second') WHERE id=%s""",
                (stage, code, delay, job["id"]),
            )
            db.execute("UPDATE kb_versions SET state=%s WHERE id=%s", (stage, job["version_id"]))

    def retry(self, job_id: str) -> None:
        with self.connect() as db:
            row = db.execute(
                """UPDATE kb_jobs SET stage='queued', attempts=0,
                available_at=now(),error_code=NULL WHERE id=%s
                AND stage IN ('failed','needs_review') RETURNING version_id""",
                (job_id,),
            ).fetchone()
            if not row:
                raise ValueError("Job is not failed or needs_review")
            db.execute("UPDATE kb_versions SET state='queued' WHERE id=%s", (row["version_id"],))

    def job(self, job_id: str) -> dict | None:
        with self.connect() as db:
            return db.execute(
                """SELECT id,version_id,stage,attempts,max_attempts,
                error_code,available_at,lease_until FROM kb_jobs WHERE id=%s""",
                (job_id,),
            ).fetchone()

    def chunks(self, version_id: str) -> list[dict]:
        with self.connect() as db:
            return db.execute(
                """SELECT ordinal,body,locations,token_count FROM kb_chunks
                WHERE version_id=%s ORDER BY ordinal""",
                (version_id,),
            ).fetchall()

    def version_belongs_to(self, document_id: str, version_id: str) -> bool:
        with self.connect() as db:
            return bool(
                db.execute(
                    """SELECT 1 FROM kb_versions v
                JOIN kb_documents d ON d.id=v.document_id
                WHERE d.id=%s AND v.id=%s AND d.deleted_at IS NULL""",
                    (document_id, version_id),
                ).fetchone()
            )

    def list_documents(self) -> list[dict]:
        with self.connect() as db:
            return db.execute("""SELECT d.id,d.title,d.visibility,d.published,
                v.id AS version_id,v.state,j.id AS job_id,j.stage AS job_stage
                FROM kb_documents d JOIN kb_versions v ON v.document_id=d.id
                JOIN kb_jobs j ON j.version_id=v.id WHERE d.deleted_at IS NULL
                ORDER BY d.id,v.created_at""").fetchall()

    def admin_documents(self) -> list[dict]:
        with self.connect() as db:
            return db.execute("""SELECT d.id,d.title,d.project,d.fact_type,d.author,
                d.subject_relation,d.visibility,d.published,d.active_version_id,
                latest.id AS latest_version_id,latest.state AS latest_state,
                latest.effective_at,latest.source_date,j.id AS job_id,
                j.stage AS job_stage,j.error_code
                FROM kb_documents d
                LEFT JOIN LATERAL (
                    SELECT v.* FROM kb_versions v WHERE v.document_id=d.id
                    ORDER BY v.created_at DESC,v.id DESC LIMIT 1
                ) latest ON true
                LEFT JOIN kb_jobs j ON j.version_id=latest.id
                WHERE d.deleted_at IS NULL ORDER BY d.created_at DESC,d.id""").fetchall()

    def admin_document(self, document_id: str) -> dict | None:
        with self.connect() as db:
            return db.execute(
                """SELECT id,title,project,fact_type,author,
                subject_relation,visibility,published,active_version_id
                FROM kb_documents WHERE id=%s AND deleted_at IS NULL""",
                (document_id,),
            ).fetchone()

    def create_upload_intent(self, session_id: str, suffix: str, size: int) -> str:
        if suffix not in SUPPORTED or not 0 < size <= self.settings.max_file_bytes:
            raise ValueError("INVALID_UPLOAD")
        upload_id, key = uuid4().hex, object_key(suffix)
        with self.connect() as db:
            db.execute(
                """INSERT INTO kb_pending_uploads
                (id,session_id,object_key,suffix,declared_size,expires_at)
                VALUES (%s,%s,%s,%s,%s,now()+interval '15 minutes')""",
                (upload_id, session_id, key, suffix, size),
            )
        return upload_id

    def save_pending_upload(self, upload_id: str, session_id: str, data: bytes) -> None:
        with self.connect() as db:
            row = db.execute(
                """SELECT object_key,declared_size FROM kb_pending_uploads
                WHERE id=%s AND session_id=%s AND consumed_at IS NULL
                  AND uploaded_size IS NULL AND expires_at>now() FOR UPDATE""",
                (upload_id, session_id),
            ).fetchone()
            if not row or len(data) != row["declared_size"]:
                raise ValueError("UPLOAD_NOT_AVAILABLE")
            self.store.put(row["object_key"], data)
            db.execute(
                "UPDATE kb_pending_uploads SET uploaded_size=%s WHERE id=%s", (len(data), upload_id)
            )

    def pending_upload(self, upload_id: str, session_id: str) -> tuple[bytes, str]:
        with self.connect() as db:
            row = db.execute(
                """SELECT object_key,suffix FROM kb_pending_uploads
                WHERE id=%s AND session_id=%s AND consumed_at IS NULL
                  AND uploaded_size=declared_size AND expires_at>now()""",
                (upload_id, session_id),
            ).fetchone()
        if not row:
            raise ValueError("UPLOAD_NOT_AVAILABLE")
        return self.store.get(row["object_key"], self.settings.max_file_bytes), row["suffix"]

    def consume_pending_upload(self, upload_id: str, session_id: str) -> None:
        with self.connect() as db:
            row = db.execute(
                """UPDATE kb_pending_uploads SET consumed_at=now()
                WHERE id=%s AND session_id=%s AND consumed_at IS NULL
                RETURNING object_key""",
                (upload_id, session_id),
            ).fetchone()
        if row:
            self.store.delete(row["object_key"])

    def purge_one_deleted(self) -> bool:
        with self.connect() as db:
            row = db.execute("""SELECT id FROM kb_documents
                WHERE deleted_at IS NOT NULL AND purged_at IS NULL
                ORDER BY deleted_at FOR UPDATE SKIP LOCKED LIMIT 1""").fetchone()
            if not row:
                return False
            versions = db.execute(
                "SELECT id,object_key FROM kb_versions WHERE document_id=%s", (row["id"],)
            ).fetchall()
            for version in versions:
                self.store.delete(version["object_key"])
            db.execute(
                """DELETE FROM kb_chunks WHERE version_id IN
                (SELECT id FROM kb_versions WHERE document_id=%s)""",
                (row["id"],),
            )
            db.execute(
                "UPDATE kb_versions SET parsed_blocks=NULL WHERE document_id=%s", (row["id"],)
            )
            db.execute("UPDATE kb_documents SET purged_at=now() WHERE id=%s", (row["id"],))
            return True

    def purge_one_expired_upload(self) -> bool:
        with self.connect() as db:
            row = db.execute("""SELECT id,object_key FROM kb_pending_uploads
                WHERE consumed_at IS NOT NULL OR expires_at<now()
                ORDER BY expires_at FOR UPDATE SKIP LOCKED LIMIT 1""").fetchone()
            if not row:
                return False
            self.store.delete(row["object_key"])
            db.execute("DELETE FROM kb_pending_uploads WHERE id=%s", (row["id"],))
            return True
