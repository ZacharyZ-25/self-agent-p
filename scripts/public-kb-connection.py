"""One-time local setup for the published-only cloud database."""

from __future__ import annotations

import getpass
import os
from pathlib import Path
import sys

from public_kb_connection import connection_file, save_connection


ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("KB_LOCAL_DATA_DIR", ROOT / "knowledge-data" / "personal-kb")).resolve()


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "status":
        print("已配置公开知识库连接" if connection_file(DATA).is_file() else "尚未配置公开知识库连接")
        return 0
    if action == "set":
        dsn = getpass.getpass("粘贴独立的云端 PostgreSQL 连接地址：")
        save_connection(DATA, dsn)
        print("云端连接已保存在当前 Windows 用户可解密的本地文件中。")
        return 0
    if action == "remove":
        connection_file(DATA).unlink(missing_ok=True)
        print("已停用自动同步；云端已有资料仍需单独撤回或清理。")
        return 0
    print("用法：python scripts/public-kb-connection.py [set|status|remove]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
