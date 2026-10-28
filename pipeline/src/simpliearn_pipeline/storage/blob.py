"""Blob storage for audio. Keys are deterministic (see ids.py), so writing the same key twice with the
same bytes is a no-op and a retried recorder resumes instead of duplicating."""

import os
import tempfile
from pathlib import Path
from typing import Protocol

from simpliearn_pipeline.ids import sha256_bytes


class BlobConflictError(Exception):
    """A key already exists with different content."""


class BlobStore(Protocol):
    def put(self, key: str, data: bytes) -> bool:
        """Store data. Return True if written, False if identical content was already there.
        Raise BlobConflictError if the key exists with different content."""

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def list(self, prefix: str) -> list[str]: ...


class LocalBlobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Blob key escapes the store root: {key!r}")
        return path

    def put(self, key: str, data: bytes) -> bool:
        path = self._path(key)
        if path.exists():
            if sha256_bytes(path.read_bytes()) == sha256_bytes(data):
                return False
            raise BlobConflictError(f"{key} already exists with different content")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file and rename so a killed job never leaves a half-written blob.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return True

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str) -> list[str]:
        base = self._path(prefix) if prefix else self.root
        if not base.exists():
            return []
        if base.is_file():
            return [str(base.relative_to(self.root))]
        return sorted(
            str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file() and p.suffix != ".tmp"
        )
