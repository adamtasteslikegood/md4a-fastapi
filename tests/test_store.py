import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from md4a import FileStore, MemoryStore
from md4a import store as store_module

StoreFactory = Callable[..., MemoryStore | FileStore]


@pytest.fixture(params=["memory", "file"])
def make(request: pytest.FixtureRequest, tmp_path: Path) -> StoreFactory:
    def factory(**options: float | None) -> MemoryStore | FileStore:
        if request.param == "memory":
            return MemoryStore(**options)
        return FileStore(tmp_path / "cache", **options)

    return factory


@pytest.fixture
def advance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[[float], None]:
    """Make every stored entry `seconds` older, for both store kinds, without sleeping."""
    now = [1000.0]
    monkeypatch.setattr(store_module.time, "monotonic", lambda: now[0])

    def by(seconds: float) -> None:
        now[0] += seconds
        for path in (tmp_path / "cache").glob("*.md"):
            modified = path.stat().st_mtime - seconds
            os.utime(path, (modified, modified))

    return by


def test_entry_without_ttl_never_expires(make: StoreFactory, advance: Callable) -> None:
    store = make()
    store.put("/a", "# A")

    advance(10 * 365 * 24 * 3600)

    assert store.get("/a") == "# A"


def test_entry_expires_after_ttl(make: StoreFactory, advance: Callable) -> None:
    store = make(ttl=60)
    store.put("/a", "# A")

    advance(59)
    assert store.get("/a") == "# A"
    advance(2)
    assert store.get("/a") is None


def test_put_restarts_the_ttl(make: StoreFactory, advance: Callable) -> None:
    store = make(ttl=60)
    store.put("/a", "# old")
    advance(50)

    store.put("/a", "# new")
    advance(50)

    assert store.get("/a") == "# new"


@pytest.mark.parametrize("ttl", [0, -1])
def test_non_positive_ttl_is_rejected(make: StoreFactory, ttl: float) -> None:
    with pytest.raises(ValueError, match="ttl"):
        make(ttl=ttl)


def test_delete_removes_only_that_entry(make: StoreFactory) -> None:
    store = make()
    store.put("/a", "# A")
    store.put("/b", "# B")

    store.delete("/a")
    store.delete("/missing")

    assert store.get("/a") is None
    assert store.get("/b") == "# B"


def test_clear_removes_every_entry(make: StoreFactory) -> None:
    store = make()
    store.put("/a", "# A")
    store.put("/b", "# B")

    store.clear()

    assert store.get("/a") is None
    assert store.get("/b") is None
    store.put("/c", "# C")
    assert store.get("/c") == "# C"


def test_memory_store_evicts_oldest_entry_beyond_max_entries() -> None:
    store = MemoryStore(max_entries=2)
    store.put("/a", "# A")
    store.put("/b", "# B")
    store.put("/a", "# A2")  # re-storing makes /a the newest

    store.put("/c", "# C")

    assert store.get("/b") is None
    assert store.get("/a") == "# A2"
    assert store.get("/c") == "# C"


def test_memory_store_drops_expired_entries_before_evicting(advance: Callable) -> None:
    store = MemoryStore(ttl=60, max_entries=2)
    store.put("/old", "# old")
    advance(30)
    store.put("/kept", "# kept")
    advance(40)  # /old is expired, /kept is not

    store.put("/new", "# new")

    assert store.get("/kept") == "# kept"
    assert store.get("/new") == "# new"


@pytest.mark.parametrize("max_entries", [0, -1])
def test_memory_store_rejects_non_positive_max_entries(max_entries: int) -> None:
    with pytest.raises(ValueError, match="max_entries"):
        MemoryStore(max_entries=max_entries)


def _index(directory: Path) -> dict[str, str]:
    return json.loads((directory / "index.json").read_text(encoding="utf-8"))


def test_file_store_persists_across_instances_and_indexes_keys(tmp_path: Path) -> None:
    FileStore(tmp_path).put("/a?x=1", "# A")

    assert FileStore(tmp_path).get("/a?x=1") == "# A"
    assert list(_index(tmp_path)) == ["/a?x=1"]
    assert (tmp_path / _index(tmp_path)["/a?x=1"]).read_text(encoding="utf-8") == "# A"


def test_file_store_delete_removes_file_and_index_entry(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    store.put("/a", "# A")
    store.put("/b", "# B")

    store.delete("/a")

    assert list(_index(tmp_path)) == ["/b"]
    assert sorted(path.name for path in tmp_path.glob("*.md")) == [_index(tmp_path)["/b"]]


def test_file_store_expired_entry_is_removed_from_disk(tmp_path: Path, advance: Callable) -> None:
    store = FileStore(tmp_path / "cache", ttl=60)
    store.put("/a", "# A")
    advance(61)

    assert store.get("/a") is None

    assert list((tmp_path / "cache").glob("*.md")) == []
    assert _index(tmp_path / "cache") == {}


def test_file_store_clear_leaves_unrelated_files(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    store.put("/a", "# A")
    (tmp_path / "notes.md").write_text("mine", encoding="utf-8")

    store.clear()

    assert sorted(path.name for path in tmp_path.iterdir()) == ["index.json", "notes.md"]
    assert _index(tmp_path) == {}
