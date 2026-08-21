import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from md4a import __version__
from md4a.app import create_app
from md4a.client import MarkdownForAgentsClient
from md4a.middleware import add_md4a
from md4a.store import MemoryStore


def test_standalone_app_uses_package_version() -> None:
    assert create_app().version == __version__


def test_client_only_accepts_markdown_content_type() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept"] == "text/markdown"
        return httpx.Response(200, text="# Agent page", headers={"content-type": "text/markdown"})

    result = __import__("asyncio").run(
        MarkdownForAgentsClient(transport=httpx.MockTransport(handler)).fetch(
            "https://example.com/page"
        )
    )
    assert result.available
    assert result.markdown == "# Agent page"


def test_client_rejects_redirect_outside_allowlist() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://internal.example/secret"})

    client = MarkdownForAgentsClient(
        allowed_hosts={"example.com"}, transport=httpx.MockTransport(handler)
    )
    try:
        __import__("asyncio").run(client.fetch("https://example.com/page"))
    except ValueError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("redirect outside allowlist was accepted")


def test_middleware_converts_and_caches_html() -> None:
    app = FastAPI()
    store = MemoryStore()

    @app.get("/hello", response_class=HTMLResponse)
    def hello() -> str:
        return "<h1>Hello</h1><p>Agent world</p>"

    add_md4a(app, store=store)
    with TestClient(app) as client:
        html = client.get("/hello", headers={"Accept": "text/html"})
        markdown = client.get("/hello", headers={"Accept": "text/markdown"})
    assert html.headers["content-type"].startswith("text/html")
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "# Hello" in markdown.text
    assert store.get("/hello") == markdown.text


def test_middleware_uses_provider() -> None:
    app = FastAPI()

    @app.get("/known")
    def known() -> dict[str, bool]:
        return {"html": True}

    add_md4a(app, provider=lambda path: "# Known\n" if path == "/known" else None)
    with TestClient(app) as client:
        response = client.get("/known", headers={"Accept": "text/markdown"})
    assert response.text == "# Known\n"
    assert response.headers["vary"] == "Accept"
