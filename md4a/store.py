from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol


class Store(Protocol):
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, content: str) -> None: ...


class MemoryStore:
    """Process-local buffer store."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def put(self, key: str, content: str) -> None:
        self.data[key] = content


class FileStore:
    """Filesystem store with hashed filenames and a human-readable index."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.directory / f"{digest}.md"

    def get(self, key: str) -> str | None:
        path = self._path(key)
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def put(self, key: str, content: str) -> None:
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
        index_path = self.directory / "index.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            index = {}
        index[key] = path.name
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

