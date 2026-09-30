"""Console-free entry point for the current user's scheduled task."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import os
from pathlib import Path
import runpy
import traceback


ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("KB_LOCAL_DATA_DIR", ROOT / "knowledge-data" / "personal-kb")).resolve()


def main() -> int:
    logs = DATA / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "launcher.log").open("a", encoding="utf-8", buffering=1) as output:
        with redirect_stdout(output), redirect_stderr(output):
            print(f"\n{datetime.now().isoformat(timespec='seconds')} 后台启动")
            try:
                namespace = runpy.run_path(str(ROOT / "scripts" / "start-local-kb.py"))
                result = namespace["run"](background=True)
            except Exception:
                traceback.print_exc()
                result = 1
            print(f"后台进程退出，状态 {result}")
            return result


if __name__ == "__main__":
    raise SystemExit(main())
