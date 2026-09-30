"""Create or refresh the public-only knowledge mirror for the website."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.knowledge.public_mirror import (  # noqa: E402
    initialize_public_mirror,
    public_catalog_version,
    sync_public_mirror,
)
from app.knowledge.repository import KnowledgeRepository  # noqa: E402
from app.knowledge.settings import KnowledgeSettings  # noqa: E402
from app.knowledge.storage import LocalStore  # noqa: E402
from public_kb_connection import load_connection  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "sync", "watch"))
    args = parser.parse_args()
    data = Path(os.environ.get("KB_LOCAL_DATA_DIR", ROOT / "knowledge-data" / "personal-kb"))
    target_dsn = os.environ.get("PUBLIC_KB_DATABASE_URL") or load_connection(data)
    if not target_dsn:
        parser.error("请先设置 PUBLIC_KB_DATABASE_URL；不要把数据库密码写进命令行。")
    source_dsn = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@127.0.0.1:55437/postgres?sslmode=disable",
    )
    source_settings = KnowledgeSettings(
        DATABASE_URL=source_dsn,
        pglite_compat=os.environ.get("KB_PGLITE_COMPAT", "true").lower() == "true",
    )
    target_settings = KnowledgeSettings(
        DATABASE_URL=target_dsn,
        pglite_compat=os.environ.get("PUBLIC_KB_PGLITE_COMPAT", "false").lower() == "true",
    )
    source = KnowledgeRepository(source_settings, LocalStore(source_settings.object_dir))
    target = KnowledgeRepository(target_settings, LocalStore(target_settings.object_dir))
    if args.action == "init":
        initialize_public_mirror(target)
        print("公开镜像数据库已初始化。")
    elif args.action == "sync":
        result = sync_public_mirror(source, target)
        print(f"已同步 {result['documents']} 份公开资料、{result['chunks']} 个片段。")
    else:
        previous = None
        while True:
            try:
                current = public_catalog_version(source)
                if current != previous:
                    initialize_public_mirror(target)
                    result = sync_public_mirror(source, target)
                    previous = current
                    print(f"已同步 {result['documents']} 份公开资料、{result['chunks']} 个片段。", flush=True)
            except Exception as exc:
                print(f"公开知识库同步失败：{type(exc).__name__}", file=sys.stderr, flush=True)
            time.sleep(30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
