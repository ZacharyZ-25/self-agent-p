"""Real local Postgres-compatible ingestion tests; opt in with RUN_KB_INTEGRATION=1."""
from __future__ import annotations

import io
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from pypdf import PdfWriter

from app.knowledge.parsers import parse
from app.knowledge.repository import KnowledgeRepository, Upload
from app.knowledge.settings import KnowledgeSettings
from app.knowledge.storage import LocalStore
from app.knowledge.worker import process_one

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "evals/phase8/documents"


@pytest.fixture
def repository(tmp_path):
    dsn = os.environ.get("DATABASE_URL", "")
    if os.getenv("RUN_KB_INTEGRATION") != "1" or urlparse(dsn).hostname != "127.0.0.1":
        pytest.skip("Opt-in local KB database test")
    settings = KnowledgeSettings(object_dir=tmp_path / "objects", retry_seconds=0,
                                 lease_seconds=5, max_attempts=3)
    repo = KnowledgeRepository(settings, LocalStore(settings.object_dir))
    repo.migrate()
    repo.migrate()
    return repo


def upload(filename, document_id, *, replaces=None, visibility="public_answer", data=None):
    path = FIXTURES / filename
    return Upload(document_id=document_id, title=path.stem, project="Test project",
                  fact_type="project", author="Fictional Tester",
                  subject_relation="fictional_owner", visibility=visibility,
                  source_date="2026-09-01", effective_at="2026-09-15" if replaces else "2026-09-01",
                  data=path.read_bytes() if data is None else data, suffix=path.suffix,
                  replaces=replaces)


def test_four_formats_idempotency_and_locations(repository):
    prefix = uuid4().hex
    atlas = f"{prefix}-atlas"
    first = repository.submit(upload("atlas-v1.md", atlas))
    assert repository.submit(upload("atlas-v1.md", atlas)) == {**first, "reused": True}
    assert process_one(repository)["stage"] == "extracted"
    assert repository.job(first["job_id"])["stage"] == "extracted"
    assert any("32 次成功" in c["body"] and
               any(loc.get("line_start") == 8 for loc in c["locations"])
               for c in repository.chunks(first["version_id"]))
    second = repository.submit(upload("atlas-v2.docx", atlas, replaces=first["version_id"]))
    assert process_one(repository)["stage"] == "extracted"
    assert any("46 successes" in c["body"] and
               any(loc.get("table") == 1 and loc.get("row") == 2 for loc in c["locations"])
               for c in repository.chunks(second["version_id"]))
    for name, marker, location in [
        ("private-v1.txt", "AMBER-731", "line_start"),
        ("paper-v1.pdf", "EchoGrip", "page"),
    ]:
        item = repository.submit(upload(name, f"{prefix}-{name}"))
        assert process_one(repository)["stage"] == "extracted"
        chunks = repository.chunks(item["version_id"])
        assert any(marker in c["body"] for c in chunks)
        assert any(location in loc for c in chunks for loc in c["locations"])
    assert {loc.get("page") for c in repository.chunks(item["version_id"])
            for loc in c["locations"]} == {1, 2}
    # Extraction is intentionally not a publication or retrieval-ready state.
    with repository.connect() as db:
        row = db.execute("SELECT published,active_version_id FROM kb_documents WHERE id=%s",
                         (atlas,)).fetchone()
        assert not row["published"] and row["active_version_id"] is None


def test_retry_and_expired_lease_resume(repository):
    prefix = uuid4().hex
    pending = repository.submit(upload("beacon-v1.md", f"{prefix}-missing"))
    with repository.connect() as db:
        key = db.execute("SELECT object_key FROM kb_versions WHERE id=%s",
                         (pending["version_id"],)).fetchone()["object_key"]
    data = repository.store.get(key, repository.settings.max_file_bytes)
    repository.store.delete(key)
    assert process_one(repository)["stage"] == "retry_scheduled"
    assert repository.job(pending["job_id"])["stage"] == "queued"
    repository.store.put(key, data)
    assert process_one(repository)["stage"] == "extracted"

    paused = repository.submit(upload("atlas-v1.md", f"{prefix}-paused"))
    claim = repository.claim()
    assert claim["id"] == paused["job_id"]
    blocks = parse(repository.store.get(claim["object_key"], repository.settings.max_file_bytes),
                   claim["file_type"], repository.settings)
    repository.save_blocks(claim, blocks)
    with repository.connect() as db:
        db.execute("UPDATE kb_jobs SET lease_until=now()-interval '1 second' WHERE id=%s",
                   (claim["id"],))
    assert process_one(repository)["stage"] == "extracted"
    assert len(repository.chunks(paused["version_id"])) > 0


def test_scanned_pdf_requires_review_and_can_be_retried(repository):
    pdf = PdfWriter()
    pdf.add_blank_page(width=600, height=800)
    buf = io.BytesIO()
    pdf.write(buf)
    item = repository.submit(upload("paper-v1.pdf", f"{uuid4().hex}-blank", data=buf.getvalue()))
    assert process_one(repository) == {"job_id": item["job_id"],
                                       "version_id": item["version_id"],
                                       "stage": "needs_review", "error": "NEEDS_OCR"}
    repository.retry(item["job_id"])
    assert repository.job(item["job_id"])["stage"] == "queued"
    assert process_one(repository)["stage"] == "needs_review"
