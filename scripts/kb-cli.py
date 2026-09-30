"""Local Phase 8 document ingestion CLI. Run with backend/.venv/Scripts/python.exe."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.knowledge.repository import KnowledgeRepository, Upload  # noqa: E402
from app.knowledge.embeddings import LocalMultilingualEmbeddings  # noqa: E402
from app.knowledge.indexer import KnowledgeIndexer  # noqa: E402
from app.knowledge.retriever import KnowledgeRetriever  # noqa: E402
from app.knowledge.settings import KnowledgeSettings  # noqa: E402
from app.knowledge.storage import make_store  # noqa: E402
from app.knowledge.worker import process_one, run_forever  # noqa: E402


def display(value):
    def clean(obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return str(obj)
    print(json.dumps(value, ensure_ascii=False, indent=2, default=clean))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest="command", required=True)
    subs.add_parser("migrate")
    put = subs.add_parser("import")
    source = put.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--stdin", action="store_true", help="Read UTF-8 pasted text from stdin")
    put.add_argument("--document-id", required=True)
    put.add_argument("--title", required=True)
    put.add_argument("--project")
    put.add_argument("--fact-type", choices=["project","external_reference","identity"], default="project")
    put.add_argument("--author", required=True)
    put.add_argument("--subject-relation", choices=["fictional_owner","owner","external_author"],
                     required=True)
    put.add_argument("--visibility", choices=["private_preview","public_answer"],
                     default="private_preview")
    put.add_argument("--source-date", required=True)
    put.add_argument("--effective-at", required=True)
    put.add_argument("--replaces", help="Previous version ID of the same document")
    put.add_argument("--run-worker", action="store_true", help="Process this job immediately")
    subs.add_parser("work-once")
    subs.add_parser("work-forever")
    subs.add_parser("index-once")
    index = subs.add_parser("index")
    index.add_argument("version_id")
    activate = subs.add_parser("activate")
    activate.add_argument("version_id")
    activate.add_argument("--publish", action="store_true")
    unpublish = subs.add_parser("unpublish")
    unpublish.add_argument("document_id")
    delete = subs.add_parser("delete")
    delete.add_argument("document_id")
    search = subs.add_parser("search")
    search.add_argument("query")
    search.add_argument("--owner-preview", action="store_true")
    search.add_argument("--as-of", type=date.fromisoformat)
    search.add_argument("--history-version", action="append", default=[])
    job = subs.add_parser("job")
    job.add_argument("job_id")
    retry = subs.add_parser("retry")
    retry.add_argument("job_id")
    chunks = subs.add_parser("chunks")
    chunks.add_argument("version_id")
    subs.add_parser("list")
    return p


def main() -> None:
    args = parser().parse_args()
    settings = KnowledgeSettings()
    repository = KnowledgeRepository(settings, make_store(settings))
    if args.command == "migrate":
        repository.migrate()
        display({"migration": "004", "status": "applied"})
    elif args.command == "import":
        data = args.file.read_bytes() if args.file else sys.stdin.buffer.read(settings.max_file_bytes+1)
        result = repository.submit(Upload(
            document_id=args.document_id, title=args.title, project=args.project,
            fact_type=args.fact_type, author=args.author,
            subject_relation=args.subject_relation, visibility=args.visibility,
            source_date=args.source_date, effective_at=args.effective_at,
            data=data, suffix=args.file.suffix.lower() if args.file else ".txt",
            replaces=args.replaces, actor=os.environ.get("KB_ACTOR", "local-cli")))
        display(result)
        if args.run_worker:
            extracted = None
            if result["stage"] in ("queued", "parsing", "chunking"):
                extracted = process_one(repository, result["job_id"])
                display(extracted)
            if result["stage"] == "extracted" or (
                extracted and extracted["stage"] == "extracted"
            ):
                display(KnowledgeIndexer(repository, LocalMultilingualEmbeddings()).index_version(
                    result["version_id"]
                ))
    elif args.command == "work-once":
        display(process_one(repository) or {"status": "idle"})
    elif args.command == "work-forever":
        run_forever(repository, indexer=KnowledgeIndexer(
            repository, LocalMultilingualEmbeddings()
        ))
    elif args.command == "job":
        display(repository.job(args.job_id))
    elif args.command == "retry":
        repository.retry(args.job_id)
        display(repository.job(args.job_id))
    elif args.command == "chunks":
        display(repository.chunks(args.version_id))
    elif args.command == "list":
        display(repository.list_documents())
    elif args.command in ("index-once", "index", "activate", "unpublish", "delete", "search"):
        provider = LocalMultilingualEmbeddings()
        indexer = KnowledgeIndexer(repository, provider)
        if args.command == "index-once":
            display(indexer.index_pending() or {"status": "idle"})
        elif args.command == "index":
            display(indexer.index_version(args.version_id))
        elif args.command == "activate":
            indexer.activate_version(args.version_id, publish=args.publish)
            display({"version_id": args.version_id, "published": args.publish})
        elif args.command == "unpublish":
            indexer.set_published(args.document_id, False)
            display({"document_id": args.document_id, "published": False})
        elif args.command == "delete":
            indexer.delete_document(args.document_id)
            display({"document_id": args.document_id, "deleted": True})
        else:
            found = KnowledgeRetriever(repository, provider).retrieve(
                args.query, owner_preview=args.owner_preview,
                as_of=args.as_of, history=tuple(args.history_version))
            display({"status": found.status, "sources": [vars(e) for e in found.evidence]})


if __name__ == "__main__":
    main()
