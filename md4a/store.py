from __future__ import annotations

import hashlib
import json
import string
import time
from pathlib import Path
from typing import Protocol


class Store(Protocol):
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, content: str) -> None: ...


def _validated_ttl(ttl: float | None) -> float | None:
    if ttl is not None and ttl <= 0:
        raise ValueError("ttl must be greater than 0, or None to never expire")
    return ttl


class MemoryStore:
    """Process-local buffer store.

    Entries older than ``ttl`` seconds are treated as missing. With ``max_entries``
    set, storing beyond the limit drops expired entries, then the oldest stored.
    """

    def __init__(self, *, ttl: float | None = None, max_entries: int | None = None) -> None:
        if max_entries is not None and max_entries < 1:
            raise ValueError("max_entries must be at least 1, or None for no limit")
        self.ttl = _validated_ttl(ttl)
        self.max_entries = max_entries
        self.data: dict[str, str] = {}
        self._stored_at: dict[str, float] = {}

    def _expired(self, key: str) -> bool:
        return self.ttl is not None and time.monotonic() - self._stored_at[key] >= self.ttl

    def get(self, key: str) -> str | None:
        if key in self.data and self._expired(key):
            self.delete(key)
        return self.data.get(key)

    def put(self, key: str, content: str) -> None:
        # Remove first so a re-stored key becomes the newest entry.
        self.delete(key)
        if self.max_entries is not None and len(self.data) >= self.max_entries:
            for stale in [item for item in self.data if self._expired(item)]:
                self.delete(stale)
            while len(self.data) >= self.max_entries:
                self.delete(next(iter(self.data)))
        self.data[key] = content
        self._stored_at[key] = time.monotonic()

    def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self._stored_at.pop(key, None)

    def clear(self) -> None:
        self.data.clear()
        self._stored_at.clear()


class FileStore:
    """Filesystem store with hashed filenames and a human-readable index.

    Entries whose file is older than ``ttl`` seconds are removed when read.
    """

    def __init__(self, directory: str | Path, *, ttl: float | None = None) -> None:
        self.ttl = _validated_ttl(ttl)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.directory / f"{digest}.md"

    def _read_index(self) -> dict[str, str]:
        try:
            index = json.loads((self.directory / "index.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return index if isinstance(index, dict) else {}

    def _write_index(self, index: dict[str, str]) -> None:
        (self.directory / "index.json").write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def get(self, key: str) -> str | None:
        path = self._path(key)
        try:
            if self.ttl is not None and time.time() - path.stat().st_mtime >= self.ttl:
                self.delete(key)
                return None
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def put(self, key: str, content: str) -> None:
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
        index = self._read_index()
        index[key] = path.name
        self._write_index(index)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
        index = self._read_index()
        if index.pop(key, None) is not None:
            self._write_index(index)

    def clear(self) -> None:
        # Only remove files this store names: a SHA-256 hex digest plus ".md".
        for path in self.directory.glob("*.md"):
            if len(path.stem) == 64 and set(path.stem) <= set(string.hexdigits):
                path.unlink(missing_ok=True)
        self._write_index({})
