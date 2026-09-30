"""Migrate reviewed Persona 1 facts into a private local knowledge base."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import time

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.knowledge.embeddings import LocalMultilingualEmbeddings  # noqa: E402
from app.knowledge.indexer import KnowledgeIndexer  # noqa: E402
from app.knowledge.persona_migration import prepare_migration  # noqa: E402
from app.knowledge.repository import KnowledgeRepository, Upload  # noqa: E402
from app.knowledge.settings import KnowledgeSettings  # noqa: E402
from app.knowledge.storage import make_store  # noqa: E402
from app.knowledge.worker import process_one  # noqa: E402
from app.services.persona_service import PersonaService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    migration = prepare_migration(args.persona_dir, config)
    original = args.backup_dir / "original"
    if not original.exists():
        shutil.copytree(args.persona_dir, original)
    candidate = args.backup_dir / "core-candidate"
    candidate.mkdir(exist_ok=True)
    for name, text in migration.core_files.items():
        (candidate / name).write_text(text, encoding="utf-8")
    report = PersonaService(candidate).validate()
    if not report.production_ready:
        raise RuntimeError(report.model_dump_json())
    settings = KnowledgeSettings()
    repo = KnowledgeRepository(settings, make_store(settings))
    indexer = KnowledgeIndexer(repo, LocalMultilingualEmbeddings())
    repo.migrate()
    submitted = []
    for document in migration.documents:
        (args.backup_dir / (document.document_id + ".md")).write_text(
            document.body, encoding="utf-8"
        )
        result = repo.submit(Upload(
            document_id=document.document_id, title=document.title, project=document.project,
            fact_type="project", author=document.author, subject_relation="owner",
            visibility="private_preview", source_date=document.source_date,
            effective_at=document.source_date, data=document.body.encode("utf-8"), suffix=".md",
            actor="persona-migration",
        ))
        if result["stage"] in ("queued", "parsing", "chunking"):
            process_one(repo, result["job_id"])
        deadline = time.monotonic() + 120
        while repo.job(result["job_id"])["stage"] in ("queued", "parsing", "chunking", "embedding"):
            if time.monotonic() >= deadline:
                raise RuntimeError("Document processing is pending; original Persona is unchanged")
            time.sleep(0.5)
        stage = repo.job(result["job_id"])["stage"]
        if stage not in ("extracted", "ready"):
            raise RuntimeError(f"Document requires review ({stage}); original Persona is unchanged")
        if stage != "ready":
            indexer.index_version(result["version_id"])
        indexer.activate_version(result["version_id"], publish=False, actor="persona-migration")
        submitted.append(result)
        print(json.dumps({"document_id": document.document_id, "status": "ready",
                          "published": False}), flush=True)
    for name in migration.core_files:
        shutil.copyfile(candidate / name, args.persona_dir / name)
    (args.backup_dir / "result.json").write_text(
        json.dumps({"persona_version": config["persona_version"], "documents": submitted},
                   indent=2), encoding="utf-8"
    )
    print(f"Persona {config['persona_version']}: {len(submitted)} private documents migrated")


if __name__ == "__main__":
    main()
