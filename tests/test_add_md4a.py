from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from md4a import MemoryStore, add_md4a


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
