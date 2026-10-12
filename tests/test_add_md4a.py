import pytest
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from md4a import MemoryStore, add_md4a
from md4a import store as store_module


def _get(**options: int) -> tuple[str, MemoryStore]:
    app = FastAPI()
    store = MemoryStore()

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return "<h1>Hello</h1>"

    add_md4a(app, store=store, **options)
    with TestClient(app) as client:
        response = client.get("/", headers={"Accept": "text/markdown"})
    return response.headers["content-type"], store


def test_add_md4a_applies_max_html_bytes() -> None:
    content_type, store = _get(max_html_bytes=5)

    assert content_type.startswith("text/html")
    assert store.get("/") is None


def test_add_md4a_converts_by_default() -> None:
    content_type, store = _get()

    assert content_type == "text/markdown; charset=utf-8"
    assert store.get("/") is not None


def _counting_app(media_type: str, **options: bool) -> tuple[TestClient, MemoryStore, list[int]]:
    app = FastAPI()
    store = MemoryStore()
    calls: list[int] = []

    @app.get("/")
    def page() -> Response:
        calls.append(1)
        return Response(f"<h1>Call {len(calls)}</h1>", media_type=media_type)

    add_md4a(app, store=store, **options)
    return TestClient(app), store, calls


@pytest.mark.parametrize("media_type", ["text/html", "text/markdown"])
def test_cache_responses_false_runs_the_route_every_time(media_type: str) -> None:
    client, store, calls = _counting_app(media_type, cache_responses=False)

    first = client.get("/", headers={"Accept": "text/markdown"})
    second = client.get("/", headers={"Accept": "text/markdown"})

    assert len(calls) == 2
    assert "Call 1" in first.text and "Call 2" in second.text
    assert store.get("/") is None


def test_cache_responses_false_still_serves_content_already_in_the_store() -> None:
    client, store, calls = _counting_app("text/html", cache_responses=False)
    store.put("/", "# Hand-authored")

    response = client.get("/", headers={"Accept": "text/markdown"})

    assert response.text == "# Hand-authored"
    assert calls == []


def test_responses_are_cached_by_default() -> None:
    client, store, calls = _counting_app("text/html")

    client.get("/", headers={"Accept": "text/markdown"})
    second = client.get("/", headers={"Accept": "text/markdown"})

    assert len(calls) == 1
    assert "Call 1" in second.text


def test_expired_cache_entry_runs_the_route_again(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(store_module.time, "monotonic", lambda: now[0])
    app = FastAPI()
    calls: list[int] = []

    @app.get("/")
    def page() -> Response:
        calls.append(1)
        return Response(f"<h1>Call {len(calls)}</h1>", media_type="text/html")

    add_md4a(app, store=MemoryStore(ttl=60))
    client = TestClient(app)

    client.get("/", headers={"Accept": "text/markdown"})
    now[0] += 61
    refreshed = client.get("/", headers={"Accept": "text/markdown"})

    assert "Call 2" in refreshed.text
