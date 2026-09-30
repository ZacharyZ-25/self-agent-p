"""Opt-in local owner workflow using the real knowledge database and index."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.knowledge.embeddings import LocalMultilingualEmbeddings
from app.knowledge.indexer import KnowledgeIndexer
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.settings import KnowledgeSettings
from app.knowledge.storage import LocalStore
from app.knowledge.worker import process_one
from app.main import create_app
from app.models.common import TokenUsage
from app.services.provider import ProviderDelta, ProviderDone, ProviderEvent, ProviderResult

ORIGIN = "http://testserver"
BASE = "/api/v1/admin/kb"


class CitingProvider:
    async def complete(self, messages: Sequence[dict[str, str]], user_id: str) -> ProviderResult:
        return ProviderResult("根据资料回答。[S1]", "fixture-provider", TokenUsage(), "stop")

    async def stream(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> AsyncIterator[ProviderEvent]:
        yield ProviderDelta("根据资料回答。[S1]")
        yield ProviderDone("stop")


def test_admin_page_disabled_by_default_and_password_mode_is_local_only() -> None:
    with TestClient(create_app(Settings(app_env="test"), provider=CitingProvider())) as client:
        assert client.get("/admin/kb").status_code == 404
        assert client.get(f"{BASE}/session").status_code == 404
    with pytest.raises(ValueError, match="KB_ADMIN_ENABLED is local-only"):
        Settings(
            app_env="production",
            rag_enabled=True,
            database_url="postgresql://localhost/example",
            kb_admin_enabled=True,
            kb_admin_password="local-test-password",
        )


@pytest.mark.skipif(
    os.environ.get("RUN_KB_INTEGRATION") != "1"
    or urlparse(os.environ.get("DATABASE_URL", "")).hostname != "127.0.0.1",
    reason="Opt-in local KB database test",
)
def test_owner_upload_preview_publish_replace_withdraw_and_delete(tmp_path, monkeypatch) -> None:
    dsn = os.environ["DATABASE_URL"]
    monkeypatch.setenv("KB_OBJECT_DIR", str(tmp_path / "objects"))
    kb_settings = KnowledgeSettings(DATABASE_URL=dsn, object_dir=tmp_path / "objects")
    repository = KnowledgeRepository(kb_settings, LocalStore(kb_settings.object_dir))
    repository.migrate()
    indexer = KnowledgeIndexer(repository, LocalMultilingualEmbeddings())
    app = create_app(
        Settings(
            app_env="test",
            rag_enabled=True,
            database_url=dsn,
            kb_admin_enabled=True,
            kb_admin_password="local-test-password",
        ),
        provider=CitingProvider(),
    )

    with TestClient(app) as client:
        assert client.get("/admin/kb").status_code == 200
        assert client.get(f"{BASE}/documents").status_code == 401
        assert (
            client.post(f"{BASE}/login", json={"password": "local-test-password"}).status_code
            == 403
        )
        login = client.post(
            f"{BASE}/login",
            headers={"Origin": ORIGIN},
            json={"password": "local-test-password"},
        )
        assert login.status_code == 200
        assert "httponly" in login.headers["set-cookie"].lower()
        csrf = login.json()["csrf_token"]
        write = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
        invalid_csrf_payload = {
            "title": "Unsubmitted",
            "author": "Owner",
            "source_date": "2026-09-01",
            "effective_at": "2026-09-01",
            "text": "This should not be submitted.",
        }
        assert (
            client.post(
                f"{BASE}/documents", json=invalid_csrf_payload, headers={"Origin": ORIGIN}
            ).status_code
            == 403
        )

        first = client.post(
            f"{BASE}/documents",
            headers=write,
            json={
                "title": "Atlas local report",
                "project": "Atlas",
                "author": "Owner",
                "fact_type": "project",
                "subject_relation": "owner",
                "visibility": "private_preview",
                "source_date": "2026-09-01",
                "effective_at": "2026-09-01",
                "text": "Atlas v1 throughput is 32 pieces per minute. ATLAS-V1.",
            },
        )
        assert first.status_code == 202, first.text
        first_data = first.json()
        document_id = first_data["document_id"]
        assert process_one(repository, first_data["job_id"])["stage"] == "extracted"
        assert indexer.index_pending()["activated"] is True
        listing = client.get(f"{BASE}/documents").json()
        own = next(item for item in listing if item["id"] == document_id)
        assert own["active_version_id"] == first_data["version_id"]
        assert own["published"] is False
        chunks = client.get(
            f"{BASE}/documents/{document_id}/versions/{first_data['version_id']}/chunks"
        )
        assert chunks.status_code == 200
        assert "ATLAS-V1" in chunks.text
        preview = client.post(
            f"{BASE}/preview", headers=write, json={"message": "ATLAS-V1 throughput?"}
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["sources"][0]["document_id"] == document_id
        assert preview.json()["sources"][0]["url"].startswith(f"{BASE}/sources/")
        private_source_url = preview.json()["sources"][0]["url"]
        assert client.get(private_source_url).status_code == 200
        public_before = client.post("/api/v1/chat", json={"message": "ATLAS-V1 throughput?"})
        assert all(
            source["document_id"] != document_id for source in public_before.json()["sources"]
        )

        assert (
            client.post(f"{BASE}/documents/{document_id}/publish", headers=write).status_code == 200
        )
        public_after = client.post("/api/v1/chat", json={"message": "ATLAS-V1 throughput?"})
        assert public_after.json()["sources"][0]["document_id"] == document_id

        replacement = client.post(
            f"{BASE}/documents/{document_id}/versions",
            headers=write,
            json={
                "source_date": "2026-09-02",
                "effective_at": "2026-09-02",
                "text": "Atlas v2 throughput is 42 pieces per minute. ATLAS-V2.",
            },
        )
        assert replacement.status_code == 202, replacement.text
        second_data = replacement.json()
        assert process_one(repository, second_data["job_id"])["stage"] == "extracted"
        assert indexer.index_pending()["activated"] is True
        current = client.post("/api/v1/chat", json={"message": "ATLAS-V2 throughput?"})
        assert "ATLAS-V2" in current.json()["sources"][0]["snippet"]
        assert current.json()["sources"][0]["version_id"] == second_data["version_id"]
        assert client.get(private_source_url).status_code == 404

        pending_replacement = client.post(
            f"{BASE}/documents/{document_id}/versions",
            headers=write,
            json={
                "source_date": "2026-09-03",
                "effective_at": "2026-09-03",
                "text": "Atlas v3 is ready but should remain withdrawn. ATLAS-V3.",
            },
        )
        assert pending_replacement.status_code == 202
        assert (
            client.post(f"{BASE}/documents/{document_id}/unpublish", headers=write).status_code
            == 200
        )
        assert process_one(repository, pending_replacement.json()["job_id"])["stage"] == "extracted"
        assert indexer.index_pending()["activated"] is True
        after_withdrawal = client.get(f"{BASE}/documents").json()
        assert (
            next(item for item in after_withdrawal if item["id"] == document_id)["published"]
            is False
        )
        withdrawn = client.post("/api/v1/chat", json={"message": "ATLAS-V2 throughput?"})
        assert all(source["document_id"] != document_id for source in withdrawn.json()["sources"])
        assert client.delete(f"{BASE}/documents/{document_id}", headers=write).status_code == 202
        assert repository.purge_one_deleted() is True
        assert repository.chunks(second_data["version_id"]) == []
        assert repository.chunks(pending_replacement.json()["version_id"]) == []
        assert client.get(private_source_url).status_code == 404


@pytest.mark.skipif(
    os.environ.get("RUN_KB_INTEGRATION") != "1"
    or urlparse(os.environ.get("DATABASE_URL", "")).hostname != "127.0.0.1",
    reason="Opt-in local KB database test",
)
def test_owner_file_upload_intent_and_session_controls(tmp_path, monkeypatch) -> None:
    dsn = os.environ["DATABASE_URL"]
    monkeypatch.setenv("KB_OBJECT_DIR", str(tmp_path / "objects"))
    kb_settings = KnowledgeSettings(DATABASE_URL=dsn, object_dir=tmp_path / "objects")
    repository = KnowledgeRepository(kb_settings, LocalStore(kb_settings.object_dir))
    repository.migrate()
    app = create_app(
        Settings(
            app_env="test",
            rag_enabled=True,
            database_url=dsn,
            kb_admin_enabled=True,
            kb_admin_password="local-test-password",
        ),
        provider=CitingProvider(),
    )
    with TestClient(app) as client:
        login = client.post(
            f"{BASE}/login", headers={"Origin": ORIGIN}, json={"password": "local-test-password"}
        )
        write = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        content = b"Atlas uploaded file says ATLAS-UPLOAD-51.\n"
        intent = client.post(
            f"{BASE}/uploads", headers=write, json={"filename": "atlas.md", "size": len(content)}
        )
        assert intent.status_code == 201
        upload = client.put(intent.json()["upload_url"], headers=write, content=content)
        assert upload.status_code == 204, upload.text
        created = client.post(
            f"{BASE}/documents",
            headers=write,
            json={
                "title": "Uploaded Atlas",
                "author": "Owner",
                "visibility": "public_answer",
                "source_date": "2026-09-01",
                "effective_at": "2026-09-01",
                "upload_id": intent.json()["upload_id"],
            },
        )
        assert created.status_code == 202, created.text
        assert process_one(repository, created.json()["job_id"])["stage"] == "extracted"
        indexed = KnowledgeIndexer(repository, LocalMultilingualEmbeddings()).index_pending()
        assert indexed and indexed["activated"]
        assert client.post("/api/v1/chat", json={"message": "ATLAS-UPLOAD-51?"}).json()["sources"]
        queued = client.post(
            f"{BASE}/documents",
            headers=write,
            json={
                "title": "Delete before worker",
                "author": "Owner",
                "source_date": "2026-09-01",
                "effective_at": "2026-09-01",
                "text": "This text must never be indexed.",
            },
        )
        assert queued.status_code == 202
        assert (
            client.delete(
                f"{BASE}/documents/{queued.json()['document_id']}", headers=write
            ).status_code
            == 202
        )
        assert process_one(repository, queued.json()["job_id"]) is None
        assert repository.purge_one_deleted() is True
        assert client.delete(
            f"{BASE}/documents/{created.json()['document_id']}", headers=write
        ).status_code == 202
        logout = client.post(f"{BASE}/logout", headers=write)
        assert logout.status_code == 200
        assert client.get(f"{BASE}/documents").status_code == 401
