from __future__ import annotations

import json
import logging
import threading
import time
from typing import TYPE_CHECKING

from app.knowledge.chunker import chunk
from app.knowledge.parsers import IngestionError, parse
from app.knowledge.repository import KnowledgeRepository

if TYPE_CHECKING:
    from app.knowledge.indexer import KnowledgeIndexer

log = logging.getLogger(__name__)


def process_one(repository: KnowledgeRepository, job_id: str | None = None) -> dict | None:
    job = repository.claim(job_id)
    if job is None:
        return None
    stop = threading.Event()

    def keep_lease() -> None:
        while not stop.wait(max(1, repository.settings.lease_seconds / 3)):
            try:
                if not repository.heartbeat(job["id"], job["lease_token"]):
                    return
            except Exception as exc:
                log.error(
                    "Knowledge heartbeat failed: job=%s type=%s", job["id"], type(exc).__name__
                )

    heartbeat = threading.Thread(target=keep_lease, daemon=True)
    heartbeat.start()
    try:
        blocks = job["parsed_blocks"]
        if blocks is None:
            data = repository.store.get(job["object_key"], repository.settings.max_file_bytes)
            blocks = parse(data, job["file_type"], repository.settings)
            repository.save_blocks(job, blocks)
        if isinstance(blocks, str):
            blocks = json.loads(blocks)
        chunks = chunk(blocks, repository.settings.chunk_tokens, repository.settings.overlap_tokens)
        if not chunks:
            raise IngestionError("EMPTY_CHUNKS", review=True)
        repository.save_chunks(job, chunks)
        return {
            "job_id": job["id"],
            "version_id": job["version_id"],
            "stage": "extracted",
            "chunks": len(chunks),
        }
    except IngestionError as exc:
        repository.fail(job, exc.code, review=exc.review)
        return {
            "job_id": job["id"],
            "version_id": job["version_id"],
            "stage": "needs_review" if exc.review else "retry_scheduled",
            "error": exc.code,
        }
    except (OSError, ValueError) as exc:
        repository.fail(job, type(exc).__name__)
        return {
            "job_id": job["id"],
            "version_id": job["version_id"],
            "stage": "retry_scheduled",
            "error": type(exc).__name__,
        }
    except Exception as exc:
        log.error("Knowledge job failed: job=%s type=%s", job["id"], type(exc).__name__)
        repository.fail(job, type(exc).__name__)
        return {
            "job_id": job["id"],
            "version_id": job["version_id"],
            "stage": "retry_scheduled",
            "error": type(exc).__name__,
        }
    finally:
        stop.set()
        heartbeat.join(timeout=1)


def run_forever(
    repository: KnowledgeRepository,
    poll_seconds: float = 2,
    indexer: KnowledgeIndexer | None = None,
) -> None:
    while True:
        extracted = process_one(repository)
        indexed = None
        purged = False
        if indexer is not None:
            try:
                indexed = indexer.index_pending()
            except Exception as exc:
                log.error("Knowledge indexing failed: type=%s", type(exc).__name__)
        try:
            purged = repository.purge_one_deleted()
            purged = repository.purge_one_expired_upload() or purged
        except Exception as exc:
            log.error("Knowledge cleanup failed: type=%s", type(exc).__name__)
        if extracted is None and indexed is None and not purged:
            time.sleep(poll_seconds)
