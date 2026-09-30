"""Run the private knowledge manager on this computer without cloud services."""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

from local_kb_password import load_password
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "knowledge-data" / "personal-kb"
PYTHON = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
DB_SERVER = ROOT / "scripts" / "phase8-local-db" / "server.mjs"
MODEL_SERVER = ROOT / "local-model" / "runtime" / "llama-server.exe"
MODEL_CACHE = ROOT / "local-model" / "models"
MODEL_ALIAS = "local-model"


def port(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be a valid port")
    return value


def port_in_use(value: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", value)) == 0


def tail(path: Path) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
    except OSError:
        return ""


def launch(
    command: list[str], env: dict[str, str], log: Path, *,
    input_pipe: bool = False, cwd: Path = ROOT,
) -> subprocess.Popen[bytes]:
    with log.open("ab") as output:
        return subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE if input_pipe else subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def wait_for_database(process: subprocess.Popen[bytes], value: int, log: Path) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"本地数据库启动失败：\n{tail(log)}")
        if port_in_use(value):
            return
        time.sleep(0.3)
    raise RuntimeError(f"等待本地数据库超时：\n{tail(log)}")


def wait_for_api(
    process: subprocess.Popen[bytes], url: str, log: Path, *,
    path: str = "/api/v1/admin/kb/session", label: str = "管理页面",
) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{label}启动失败：\n{tail(log)}")
        try:
            with urlopen(url + path, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.5)
    raise RuntimeError(f"等待{label}超时：\n{tail(log)}")


def model_is_ready() -> bool:
    try:
        with urlopen("http://127.0.0.1:8010/v1/models", timeout=2) as response:
            models = json.load(response).get("data", [])
        return any(item.get("id") == MODEL_ALIAS for item in models)
    except (OSError, URLError, ValueError, TypeError):
        return False


def cached_model() -> Path | None:
    if not MODEL_CACHE.is_dir():
        return None
    return next(MODEL_CACHE.rglob("Qwen3-4B-Q4_K_M.gguf"), None)


def start_model(env: dict[str, str], log: Path) -> subprocess.Popen[bytes] | None:
    if os.environ.get("KB_LOCAL_START_MODEL", "1") == "0":
        print("已按 KB_LOCAL_START_MODEL=0 跳过本地回答模型。")
        return None
    if port_in_use(8010):
        if model_is_ready():
            print("已连接正在运行的本地回答模型。")
        else:
            print("端口 8010 已被其他程序占用，Agent 暂时无法生成回答。", file=sys.stderr)
        return None
    model = cached_model()
    if not MODEL_SERVER.is_file() or model is None:
        print("未找到本地回答模型或运行程序；资料仍可上传和检索。", file=sys.stderr)
        return None
    model_env = env.copy()
    model_env["HF_HOME"] = str(MODEL_CACHE)
    return launch(
        [str(MODEL_SERVER), "-m", str(model), "--alias", MODEL_ALIAS,
         "--host", "127.0.0.1", "--port", "8010", "-c", "8192",
         "-np", "1", "-ngl", "99"],
        model_env, log,
    )


def wait_for_model(process: subprocess.Popen[bytes], log: Path) -> bool:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if process.poll() is not None:
            print(f"本地回答模型启动失败：\n{tail(log)}", file=sys.stderr)
            return False
        if model_is_ready():
            return True
        time.sleep(1)
    print("本地回答模型仍在加载；管理页可以先使用，稍后再提问。", file=sys.stderr)
    return False


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_for_enter(done: threading.Event) -> None:
    try:
        input()
    except EOFError:
        pass
    done.set()


def run(*, background: bool = False) -> int:
    node = shutil.which("node")
    if not PYTHON.is_file() or node is None or not (DB_SERVER.parent / "node_modules").is_dir():
        print("缺少本地依赖。请先按 backend/app/knowledge/README.md 的“本地启动”安装 Python 和 Node 依赖。")
        return 1

    data = Path(os.environ.get("KB_LOCAL_DATA_DIR", DEFAULT_DATA)).resolve()
    db_port = port("KB_LOCAL_DB_PORT", 55437)
    api_port = port("KB_LOCAL_API_PORT", 8000)
    public_db_port = port("KB_PUBLIC_DB_PORT", 55438)
    public_api_port = port("KB_PUBLIC_API_PORT", 8003)
    ports = (db_port, api_port, public_db_port, public_api_port)
    if len(set(ports)) != len(ports) or any(port_in_use(value) for value in ports):
        print(f"本地服务端口 {ports} 有冲突；请先关闭已有的服务。")
        return 1
    password = os.environ.get("KB_ADMIN_PASSWORD") or load_password(data)
    if not password and not background:
        password = getpass.getpass("请设置本次本地管理密码：")
    if not password:
        print("本地管理密码未设置；请先运行 scripts/local-kb-password.py set。")
        return 1

    data.mkdir(parents=True, exist_ok=True)
    objects = data / "objects"
    objects.mkdir(exist_ok=True)
    logs = data / "logs"
    logs.mkdir(exist_ok=True)
    database = data / "db"
    db_log, worker_log, api_log, model_log, public_db_log, public_log, public_api_log = (
        logs / name for name in (
            "database.log", "worker.log", "api.log", "model.log",
            "public-database.log", "public-sync.log", "public-api.log",
        )
    )
    db_env = os.environ.copy()
    db_env.pop("KB_ADMIN_PASSWORD", None)
    db_env.update(KB_PGLITE_DB=str(database), KB_PGLITE_PORT=str(db_port))
    common = os.environ.copy()
    common.pop("KB_ADMIN_PASSWORD", None)
    common.update(
        APP_ENV="development",
        DATABASE_URL=f"postgresql://postgres:postgres@127.0.0.1:{db_port}/postgres?sslmode=disable",
        KB_PGLITE_COMPAT="true",
        KB_OBJECT_DIR=str(objects),
        LLM_PROVIDER="local",
        LLM_BASE_URL="http://127.0.0.1:8010/v1",
        LLM_MODEL=MODEL_ALIAS,
        LLM_API_KEY="",
        DEEPSEEK_API_KEY="",
        PYTHONUTF8="1",
        RUN_REAL_DEEPSEEK_SMOKE="0",
    )
    api_env = common.copy()
    api_env.update(RAG_ENABLED="true", KB_ADMIN_ENABLED="true", KB_ADMIN_PASSWORD=password)
    public_dsn = (
        f"postgresql://postgres:postgres@127.0.0.1:{public_db_port}/postgres?sslmode=disable"
    )
    db = worker = api = model = public_db = public_sync = public_api = None
    try:
        model = start_model(common, model_log)
        db = launch([node, str(DB_SERVER)], db_env, db_log, input_pipe=True)
        wait_for_database(db, db_port, db_log)
        migrated = subprocess.run(
            [str(PYTHON), str(ROOT / "scripts/kb-cli.py"), "migrate"],
            cwd=ROOT, env=common, capture_output=True, text=True, encoding="utf-8", timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if migrated.returncode:
            raise RuntimeError(f"本地数据库建表失败：\n{migrated.stdout}\n{migrated.stderr}")
        worker = launch([str(PYTHON), str(ROOT / "scripts/kb-cli.py"), "work-forever"], common, worker_log)
        api = launch(
            [str(PYTHON), "-m", "uvicorn", "app.main:app", "--app-dir", "backend",
             "--host", "127.0.0.1", "--port", str(api_port)], api_env, api_log,
        )
        url = f"http://127.0.0.1:{api_port}"
        wait_for_api(api, url, api_log)
        if worker.poll() is not None:
            raise RuntimeError(f"入库 Worker 启动失败：\n{tail(worker_log)}")
        if os.environ.get("KB_PUBLIC_API_ENABLED", "0") == "1":
            public_db_env = db_env.copy()
            public_db_env.update(
                KB_PGLITE_DB=str(data / "public-db"),
                KB_PGLITE_PORT=str(public_db_port),
            )
            public_db = launch(
                [node, str(DB_SERVER)], public_db_env, public_db_log, input_pipe=True,
            )
            wait_for_database(public_db, public_db_port, public_db_log)
            sync_env = common.copy()
            sync_env.update(
                PUBLIC_KB_DATABASE_URL=public_dsn,
                PUBLIC_KB_PGLITE_COMPAT="true",
            )
            initial_sync = subprocess.run(
                [str(PYTHON), str(ROOT / "scripts/public-kb-sync.py"), "init"],
                cwd=ROOT, env=sync_env, capture_output=True, text=True, encoding="utf-8",
                timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if initial_sync.returncode == 0:
                initial_sync = subprocess.run(
                    [str(PYTHON), str(ROOT / "scripts/public-kb-sync.py"), "sync"],
                    cwd=ROOT, env=sync_env, capture_output=True, text=True, encoding="utf-8",
                    timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            if initial_sync.returncode:
                raise RuntimeError(
                    f"本机公开资料镜像同步失败：\n{initial_sync.stdout}\n{initial_sync.stderr}"
                )
            public_sync = launch(
                [str(PYTHON), str(ROOT / "scripts/public-kb-sync.py"), "watch"],
                sync_env, public_log,
            )
            public_env = common.copy()
            public_env.pop("LLM_API_KEY", None)
            public_env.pop("DEEPSEEK_API_KEY", None)
            public_env.update(
                APP_ENV="production",
                DATABASE_URL=public_dsn,
                RAG_ENABLED="true",
                KB_ADMIN_ENABLED="false",
                LLM_PROVIDER="deepseek",
                LLM_BASE_URL="",
                LLM_MODEL="",
                CORS_ORIGINS=os.environ.get("KB_PUBLIC_CORS_ORIGINS", "https://your-site.example"),
                RAG_TIMEOUT_SECONDS="8",
                REQUIRE_APPROVED_PERSONA="true",
            )
            public_api = launch(
                [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                 "--port", str(public_api_port)],
                public_env, public_api_log, cwd=ROOT / "backend",
            )
            public_url = f"http://127.0.0.1:{public_api_port}"
            wait_for_api(public_api, public_url, public_api_log, path="/readyz", label="访客接口")
            print(f"访客问答接口已启动：{public_url}（只读取本机公开镜像）")
        if model is not None and wait_for_model(model, model_log):
            print("本地回答模型已就绪。")
        print(f"本地知识库已启动：{url}/admin/kb")
        print("登录时输入本地管理密码；上传资料请选择“仅自己预览”。")
        print("日志位于：", logs)
        if not background:
            print("按 Enter 停止本地知识库。")
        if not background and os.environ.get("KB_LOCAL_OPEN_BROWSER", "1") != "0":
            webbrowser.open(url + "/admin/kb")
        done = threading.Event()
        stop_file = data / "stop.request"
        if background:
            stop_file.unlink(missing_ok=True)
        else:
            threading.Thread(target=wait_for_enter, args=(done,), daemon=True).start()
        while not done.wait(1):
            if background and stop_file.exists():
                stop_file.unlink()
                break
            if model is not None and model.poll() is not None:
                print(f"本地回答模型已停止；资料管理仍可使用：\n{tail(model_log)}", file=sys.stderr)
                model = None
            for name, child, log in (
                ("数据库", db, db_log), ("Worker", worker, worker_log),
                ("管理页面", api, api_log), ("公开数据库", public_db, public_db_log),
                ("访客接口", public_api, public_api_log),
            ):
                if child is not None and child.poll() is not None:
                    raise RuntimeError(f"{name} 已停止：\n{tail(log)}")
            if public_sync is not None and public_sync.poll() is not None:
                raise RuntimeError(f"公开知识库同步进程已停止：\n{tail(public_log)}")
        return 0
    except (KeyboardInterrupt, EOFError):
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        stop_process(public_sync)
        stop_process(public_api)
        stop_process(model)
        stop_process(api)
        stop_process(worker)
        if public_db is not None and public_db.poll() is None and public_db.stdin is not None:
            try:
                public_db.stdin.write(b"stop\n")
                public_db.stdin.flush()
                public_db.wait(timeout=12)
            except (OSError, subprocess.TimeoutExpired):
                stop_process(public_db)
        if db is not None and db.poll() is None and db.stdin is not None:
            try:
                db.stdin.write(b"stop\n")
                db.stdin.flush()
                db.wait(timeout=12)
            except (OSError, subprocess.TimeoutExpired):
                stop_process(db)
        print("本地知识库已停止。")


if __name__ == "__main__":
    raise SystemExit(run(background="--background" in sys.argv[1:]))
