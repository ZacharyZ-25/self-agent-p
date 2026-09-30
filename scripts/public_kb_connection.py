"""Save the public mirror database connection for this Windows user."""

from __future__ import annotations

from pathlib import Path

from local_kb_password import _transform


def connection_file(data_dir: Path) -> Path:
    return data_dir / "public-database.dpapi"


def save_connection(data_dir: Path, dsn: str) -> None:
    if not dsn.startswith("postgresql://"):
        raise ValueError("请使用 PostgreSQL 连接地址。")
    data_dir.mkdir(parents=True, exist_ok=True)
    connection_file(data_dir).write_bytes(_transform(dsn.encode("utf-8"), protect=True))


def load_connection(data_dir: Path) -> str | None:
    path = connection_file(data_dir)
    if not path.is_file():
        return None
    return _transform(path.read_bytes(), protect=False).decode("utf-8")
