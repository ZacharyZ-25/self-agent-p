"""Store the local manager password for the current Windows user with DPAPI."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path


class DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(value: bytes) -> tuple[DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(value)
    return DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _transform(value: bytes, *, protect: bool) -> bytes:
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    function.argtypes = [
        ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.POINTER(DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
    ]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    source, buffer = _blob(value)
    destination = DataBlob()
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(destination)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(destination.data, destination.size)
    finally:
        kernel.LocalFree(destination.data)


def password_file(data_dir: Path) -> Path:
    return data_dir / "admin-password.dpapi"


def save_password(data_dir: Path, password: str) -> None:
    if not password:
        raise ValueError("本地管理密码不能为空。")
    data_dir.mkdir(parents=True, exist_ok=True)
    password_file(data_dir).write_bytes(_transform(password.encode("utf-8"), protect=True))


def load_password(data_dir: Path) -> str | None:
    path = password_file(data_dir)
    if not path.is_file():
        return None
    return _transform(path.read_bytes(), protect=False).decode("utf-8")
