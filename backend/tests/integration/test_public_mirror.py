"""Public mirror sync against two isolated local databases."""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.knowledge.embeddings import LocalMultilingualEmbeddings
from app.knowledge.indexer import KnowledgeIndexer
from app.knowledge.public_mirror import (
    initialize_public_mirror,
    public_catalog_version,
    sync_public_mirror,
)
from app.knowledge.repository import KnowledgeRepository, Upload
from app.knowledge.retriever import KnowledgeRetriever
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
    urlparse(os.environ.get("DATABASE_URL", "")).hostname != "127.0.0.1"
    or not (
        (
            os.environ.get("RUN_KB_MIRROR_INTEGRATION") == "1"
            and urlparse(os.environ.get("PUBLIC_KB_DATABASE_URL", "")).hostname == "127.0.0.1"
        )
        or (
            os.environ.get("RUN_KB_NEON_SMOKE") == "1"
            and urlparse(os.environ.get("PUBLIC_KB_DATABASE_URL", "")).hostname
            not in (None, "127.0.0.1")
        )
    ),
    reason="Opt-in public mirror test with a disposable source and target",
)
def test_public_mirror_syncs_only_published_current_evidence(tmp_path, monkeypatch) -> None:
    remote_target = os.environ.get("RUN_KB_NEON_SMOKE") == "1"
    source_settings = KnowledgeSettings(
        DATABASE_URL=os.environ["DATABASE_URL"],
        pglite_compat=True,
        object_dir=tmp_path / "source-objects",
    )
    target_settings = KnowledgeSettings(
        DATABASE_URL=os.environ["PUBLIC_KB_DATABASE_URL"],
        pglite_compat=not remote_target,
        object_dir=tmp_path / "target-objects",
    )
    source = KnowledgeRepository(source_settings, LocalStore(source_settings.object_dir))
    target = KnowledgeRepository(target_settings, LocalStore(target_settings.object_dir))
    source.migrate()
    initialize_public_mirror(target)
    embeddings = LocalMultilingualEmbeddings()
    indexer = KnowledgeIndexer(source, embeddings)
    ids = {}
    for visibility, code in (("private_preview", "SECRET-91"), ("public_answer", "ATLAS-42")):
        document_id = uuid4().hex
        submitted = source.submit(
            Upload(
                document_id=document_id,
                title=f"Fictional {code} report",
                project="Atlas",
                fact_type="project",
                author="Fictional team",
                subject_relation="fictional_owner",
                visibility=visibility,
                source_date="2026-09-01",
                effective_at="2026-09-01",
                data=f"{code} throughput is 42 pieces per minute.".encode(),
                suffix=".txt",
            )
        )
        assert process_one(source, submitted["job_id"])["stage"] == "extracted"
        indexer.index_version(submitted["version_id"])
        indexer.activate_version(
            submitted["version_id"], publish=visibility == "public_answer"
        )
        ids[visibility] = document_id

    published_catalog = public_catalog_version(source)
    assert sync_public_mirror(source, target) == {"documents": 1, "chunks": 1}
    initialize_public_mirror(target)
    with target.connect() as db:
        docs = db.execute("SELECT id,visibility,published FROM kb_documents").fetchall()
        assert [row["id"] for row in docs] == [ids["public_answer"]]
        assert docs[0]["published"] is True
        object_key = db.execute("SELECT object_key FROM kb_versions").fetchone()["object_key"]
        assert object_key == "public-mirror"
    found = KnowledgeRetriever(target, embeddings).retrieve("ATLAS-42 throughput?")
    assert found.evidence and found.evidence[0].document_id == ids["public_answer"]
    assert "SECRET-91" not in " ".join(item.body for item in found.evidence)

    monkeypatch.setenv("KB_PGLITE_COMPAT", "false" if remote_target else "true")
    persona = tmp_path / "fictional-persona"
    shutil.copytree(Path(__file__).resolve().parents[3] / "persona.example", persona)
    manifest = yaml.safe_load((persona / "manifest.yaml").read_text(encoding="utf-8"))
    manifest["approved"] = True  # test-only approval; shipped example remains unapproved
    (persona / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    app = create_app(
        Settings(
            app_env="production", rag_enabled=True,
            database_url=os.environ["PUBLIC_KB_DATABASE_URL"],
            persona_dir=persona,
            cors_origins="https://your-site.example",
            rag_timeout_seconds=8 if remote_target else 2,
        ),
        provider=CitingProvider(),
    )
    with TestClient(app) as client:
        answer = client.post("/api/v1/chat", json={"message": "ATLAS-42 throughput?"})
        assert answer.status_code == 200
        assert answer.json()["knowledge_status"] == "ok"
        assert answer.json()["sources"][0]["version_id"] == found.evidence[0].version_id
        citation = client.get(f"/api/v1/knowledge/sources/{found.evidence[0].source_id}")
        assert citation.status_code == 200
        assert citation.json()["title"] == "Fictional ATLAS-42 report"

    indexer.set_published(ids["public_answer"], False)
    assert public_catalog_version(source) != published_catalog
    assert sync_public_mirror(source, target) == {"documents": 0, "chunks": 0}
    with target.connect() as db:
        assert db.execute("SELECT count(*) AS total FROM kb_documents").fetchone()["total"] == 0
    with TestClient(app) as client:
        withdrawn_source = client.get(
            f"/api/v1/knowledge/sources/{found.evidence[0].source_id}"
        )
        assert withdrawn_source.status_code == 404
        withdrawn = client.post("/api/v1/chat", json={"message": "ATLAS-42 throughput?"})
        assert withdrawn.status_code == 200
        assert withdrawn.json()["sources"] == []
