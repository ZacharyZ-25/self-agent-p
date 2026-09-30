import re
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.knowledge.settings import KnowledgeSettings


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str, max_bytes: int) -> bytes: ...
    def delete(self, key: str) -> None: ...


class ReadOnlyStore:
    """The public chat process has no access to uploaded original files."""

    def put(self, key: str, data: bytes) -> None:
        raise RuntimeError("Public knowledge storage is read-only")

    def get(self, key: str, max_bytes: int) -> bytes:
        raise RuntimeError("Original files are not present in the public mirror")

    def delete(self, key: str) -> None:
        raise RuntimeError("Public knowledge storage is read-only")


def object_key(suffix: str) -> str:
    return f"{uuid4().hex}{suffix}"


def check_key(key: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{32}\.(md|txt|pdf|docx)", key):
        raise ValueError("Invalid object key")


class LocalStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        check_key(key)
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise ValueError("Object path escapes storage")
        return path

    def put(self, key: str, data: bytes) -> None:
        with self.path(key).open("xb") as stream:
            stream.write(data)

    def get(self, key: str, max_bytes: int) -> bytes:
        with self.path(key).open("rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("FILE_TOO_LARGE")
        return data

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


class S3Store:
    def __init__(self, settings: KnowledgeSettings):
        import boto3

        if not settings.s3_bucket:
            raise ValueError("KB_S3_BUCKET is required")
        self.bucket = settings.s3_bucket
        self.client = boto3.client("s3", endpoint_url=settings.s3_endpoint,
                                   region_name=settings.s3_region)

    def put(self, key: str, data: bytes) -> None:
        check_key(key)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key: str, max_bytes: int) -> bytes:
        check_key(key)
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        try:
            data = response["Body"].read(max_bytes + 1)
        finally:
            response["Body"].close()
        if len(data) > max_bytes:
            raise ValueError("FILE_TOO_LARGE")
        return data

    def delete(self, key: str) -> None:
        check_key(key)
        self.client.delete_object(Bucket=self.bucket, Key=key)


def make_store(settings: KnowledgeSettings) -> ObjectStore:
    return LocalStore(settings.object_dir) if settings.storage == "local" else S3Store(settings)
