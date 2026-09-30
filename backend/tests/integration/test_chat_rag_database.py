"""Opt-in chat check against the local PostgreSQL-compatible knowledge index."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.knowledge.embeddings import LocalMultilingualEmbeddings
from app.knowledge.indexer import KnowledgeIndexer
from app.knowledge.repository import KnowledgeRepository, Upload
from app.knowledge.settings import KnowledgeSettings
from app.knowledge.storage import LocalStore
from app.knowledge.worker import process_one
from app.main import create_app
from app.models.common import TokenUsage
from app.services.provider import ProviderDelta, ProviderDone, ProviderEvent, ProviderResult


class CitingProvider:
    async def complete(self, messages: Sequence[dict[str, str]], user_id: str) -> ProviderResult:
        return ProviderResult("Atlas 每分钟 42 件。[S1]", "fixture-provider", TokenUsage(), "stop")

    async def stream(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> AsyncIterator[ProviderEvent]:
        yield ProviderDelta("Atlas 每分钟 42 件。[S1]")
        yield ProviderDone("stop")


@pytest.mark.skipif(
    os.environ.get("RUN_KB_INTEGRATION") != "1"
    or urlparse(os.environ.get("DATABASE_URL", "")).hostname != "127.0.0.1",
    reason="Opt-in local KB database test",
)
def test_chat_uses_published_index_and_rechecks_source_after_withdrawal(tmp_path) -> None:
    dsn = os.environ["DATABASE_URL"]
    kb_settings = KnowledgeSettings(DATABASE_URL=dsn, object_dir=tmp_path / "objects")
    repository = KnowledgeRepository(kb_settings, LocalStore(kb_settings.object_dir))
    repository.migrate()
    indexer = KnowledgeIndexer(repository, LocalMultilingualEmbeddings())
    document_id = f"chat-rag-{uuid4().hex}"
    submitted = repository.submit(
        Upload(
            document_id=document_id,
            title="Fictional Atlas report",
            project="Atlas",
            fact_type="project",
            author="Fictional Atlas Team",
            subject_relation="fictional_owner",
            visibility="public_answer",
            source_date="2026-09-01",
            effective_at="2026-09-01",
            data=b"Atlas throughput is 42 pieces per minute. Code ATLAS-42.",
            suffix=".txt",
        )
    )
    assert process_one(repository, submitted["job_id"])["stage"] == "extracted"
    indexer.index_version(submitted["version_id"])
    indexer.activate_version(submitted["version_id"], publish=True)

    app = create_app(
        Settings(app_env="test", rag_enabled=True, database_url=dsn),
        provider=CitingProvider(),
    )
    question = "ATLAS-42 throughput?"
    with TestClient(app) as client:
        answer = client.post("/api/v1/chat", json={"message": question})
        assert answer.status_code == 200
        body = answer.json()
        assert body["knowledge_status"] == "ok"
        assert body["sources"][0]["version_id"] == submitted["version_id"]
        source_url = body["sources"][0]["url"]
        assert client.get(source_url).status_code == 200

        indexer.set_published(document_id, False)
        assert client.get(source_url).status_code == 404
        withdrawn_answer = client.post("/api/v1/chat", json={"message": question})
        assert withdrawn_answer.status_code == 200
        assert withdrawn_answer.json()["sources"] == []
        assert "42" not in withdrawn_answer.json()["reply"]
