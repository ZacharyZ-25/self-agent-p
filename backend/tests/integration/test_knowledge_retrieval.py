"""Real database checks for indexing and visibility transitions."""
from __future__ import annotations

import os
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from app.knowledge.embeddings import LocalMultilingualEmbeddings
from app.knowledge.indexer import KnowledgeIndexer
from app.knowledge.repository import KnowledgeRepository, Upload
from app.knowledge.retriever import KnowledgeRetriever
from app.knowledge.settings import KnowledgeSettings
from app.knowledge.storage import LocalStore
from app.knowledge.worker import process_one


@pytest.fixture
def kb(tmp_path):
    dsn = os.environ.get("DATABASE_URL", "")
    if os.getenv("RUN_KB_INTEGRATION") != "1" or urlparse(dsn).hostname != "127.0.0.1":
        pytest.skip("Opt-in local KB database test")
    settings = KnowledgeSettings(object_dir=tmp_path / "objects")
    repository = KnowledgeRepository(settings, LocalStore(settings.object_dir))
    repository.migrate()
    provider = LocalMultilingualEmbeddings()
    return repository, KnowledgeIndexer(repository, provider), KnowledgeRetriever(
        repository, provider
    )


def test_index_activation_replacement_and_visibility(kb):
    repository, indexer, retriever = kb
    prefix = uuid4().hex
    public_id, private_id = f"{prefix}-public", f"{prefix}-private"

    def submit(document_id, body, *, replaces=None, visibility="public_answer"):
        result = repository.submit(Upload(
            document_id=document_id, title="Fictional test", project="Test",
            fact_type="project", author="Fictional Tester",
            subject_relation="fictional_owner", visibility=visibility,
            source_date="2026-09-01", effective_at="2026-09-18" if replaces else "2026-09-01",
            data=body.encode(), suffix=".txt", replaces=replaces,
        ))
        assert process_one(repository, result["job_id"])["stage"] == "extracted"
        return result["version_id"]

    old = submit(public_id, "Test stage: simulation. Code OLD-271.")
    with pytest.raises(ValueError, match="VERSION_NOT_READY"):
        indexer.activate_version(old, publish=True)
    indexer.index_version(old)
    indexer.activate_version(old, publish=True)
    private = submit(private_id, "Private planning code SECRET-419.",
                     visibility="private_preview")
    indexer.index_version(private)
    indexer.activate_version(private)
    public = retriever.retrieve("SECRET-419")
    assert all(e.document_id != private_id for e in public.evidence)
    assert all(e.document_id != private_id for e in retriever.retrieve(
        "SECRET-419", use_vector=False
    ).evidence)
    assert any(e.document_id == private_id for e in retriever.retrieve(
        "SECRET-419", owner_preview=True
    ).evidence)

    new = submit(public_id, "Test stage: validation. Code NEW-824.", replaces=old)
    indexer.index_version(new)
    assert any(e.version_id == old for e in retriever.retrieve("OLD-271").evidence)
    indexer.activate_version(new, publish=True)
    assert all(e.version_id != old for e in retriever.retrieve("OLD-271").evidence)
    indexer.set_published(public_id, False)
    assert all(e.document_id != public_id for e in retriever.retrieve("NEW-824").evidence)
    indexer.delete_document(public_id)
    assert all(e.document_id != public_id for e in retriever.retrieve(
        "NEW-824", owner_preview=True
    ).evidence)
