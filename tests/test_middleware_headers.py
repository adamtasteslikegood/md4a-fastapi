import asyncio
import gzip

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import Message, Receive, Scope, Send

from md4a import MemoryStore, add_md4a
from md4a.middleware import MarkdownForAgentsMiddleware

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'self'",
    "Strict-Transport-Security": "max-age=31536000",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Match Artazzen's security-header middleware, with a per-request marker."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        response.headers["X-Request-Id"] = request.headers.get("X-Request-Id", "test")
        return response


@pytest.mark.parametrize("encodings", [["identity"], ["identity", " Identity, identity "]])
def test_conversion_preserves_response_headers_without_mutating_html(encodings: list[str]) -> None:
    app = FastAPI()
    original = HTMLResponse(
        "<h1>Café</h1>",
        status_code=201,
        headers={
            "Cache-Control": "public, max-age=60",
            "Content-Language": "fr",
            "Access-Control-Allow-Origin": "https://example.com",
            "X-Custom": "keep-me",
            "ETag": '"html-only"',
            "Last-Modified": "Tue, 06 Oct 2026 00:00:00 GMT",
            "Content-MD5": "html-only",
            "Digest": "sha-256=html-only",
            "Content-Digest": "sha-256=:html-only:",
            "Repr-Digest": "sha-256=:html-only:",
            "Accept-Ranges": "bytes",
            "Content-Location": "/page.html",
            "Trailer": "x-checksum",
        },
    )
    for encoding in encodings:
        original.headers.append("Content-Encoding", encoding)
    original.set_cookie("first", "one", httponly=True)
    original.set_cookie("second", "two", secure=True)
    original.headers.append("Link", '</one>; rel="first"')
    original.headers.append("Link", '</two>; rel="next"')

    @app.get("/")
    def page() -> Response:
        return original

    # Reproduce add_md4a(existing_artazzen_app): security headers are downstream.
    app.add_middleware(SecurityHeadersMiddleware)
    add_md4a(app)
    with TestClient(app) as client:
        html = client.get("/", headers={"Accept": "text/html"})
        original_headers = list(original.raw_headers)
        markdown = client.get("/", headers={"Accept": "text/markdown"})

    assert markdown.status_code == 201
    assert markdown.text == "# Café"
    for name, value in SECURITY_HEADERS.items():
        assert markdown.headers[name] == html.headers[name] == value
    for name in ("Cache-Control", "Content-Language", "Access-Control-Allow-Origin", "X-Custom"):
        assert markdown.headers[name] == html.headers[name]
    assert markdown.headers.get_list("Set-Cookie") == html.headers.get_list("Set-Cookie")
    assert len(markdown.headers.get_list("Set-Cookie")) == 2
    assert markdown.headers.get_list("Link") == html.headers.get_list("Link")
    assert len(markdown.headers.get_list("Link")) == 2
    assert markdown.headers["Content-Type"] == "text/markdown; charset=utf-8"
    assert int(markdown.headers["Content-Length"]) == len(markdown.content)
    for name in (
        "ETag",
        "Last-Modified",
        "Content-MD5",
        "Digest",
        "Content-Digest",
        "Repr-Digest",
        "Accept-Ranges",
        "Content-Location",
        "Content-Encoding",
        "Trailer",
    ):
        assert name not in markdown.headers
        assert name in html.headers
    assert html.content == original.body
    assert original.raw_headers == original_headers


@pytest.mark.parametrize(
    ("vary_lines", "expected"),
    [
        ([], "Accept"),
        (["Origin"], "Origin, Accept"),
        (["Origin", "Accept-Encoding"], "Origin, Accept-Encoding, Accept"),
        (["Origin, aCcEpT", "Accept-Encoding"], "Origin, aCcEpT, Accept-Encoding"),
        (["*"], "*"),
    ],
)
def test_conversion_merges_vary(vary_lines: list[str], expected: str) -> None:
    app = FastAPI()

    @app.get("/")
    def page() -> Response:
        response = HTMLResponse("<h1>Hello</h1>")
        for value in vary_lines:
            response.headers.append("Vary", value)
        return response

    add_md4a(app)
    with TestClient(app) as client:
        response = client.get("/", headers={"Accept": "text/markdown"})
    assert response.headers["Vary"] == expected


@pytest.mark.parametrize("source", ["converted", "native", "cached", "provider"])
def test_outer_security_middleware_covers_cached_and_provider_responses(source: str) -> None:
    app = FastAPI()
    store = MemoryStore()
    calls = 0

    @app.get("/")
    def page() -> Response:
        nonlocal calls
        calls += 1
        response = (
            Response("# Hello", media_type="text/markdown")
            if source == "native"
            else HTMLResponse("<h1>Hello</h1>")
        )
        response.set_cookie("one-time", "value")
        return response

    if source == "cached":
        store.put("/", "# Hello")
    provider = (lambda key: "# Hello") if source == "provider" else None
    add_md4a(app, store=store, provider=provider)
    # Last registered middleware runs outermost, including on early cache hits.
    app.add_middleware(SecurityHeadersMiddleware)
    with TestClient(app) as client:
        for request_id in ("first", "second"):
            response = client.get(
                "/", headers={"Accept": "text/markdown", "X-Request-Id": request_id}
            )
            assert response.text == "# Hello"
            for name, value in SECURITY_HEADERS.items():
                assert response.headers[name] == value
            assert response.headers["X-Request-Id"] == request_id
            if request_id == "second":
                assert "Set-Cookie" not in response.headers
    assert calls == (1 if source in ("converted", "native") else 0)


@pytest.mark.parametrize(
    ("status", "media_type", "body", "extra_headers"),
    [
        (403, "text/html", b"<h1>Forbidden</h1>", {}),
        (200, "application/json", b'{"ok":true}', {}),
        (200, "text/markdown", b"# Native", {}),
        (206, "text/html", b"<h1>Part", {"Content-Range": "bytes 0-7/20"}),
        (200, "text/html", gzip.compress(b"<h1>Hello</h1>"), {"Content-Encoding": "gzip"}),
    ],
)
def test_nonconverted_responses_keep_headers_and_body(
    status: int, media_type: str, body: bytes, extra_headers: dict[str, str]
) -> None:
    app = FastAPI()
    original = Response(
        body,
        status_code=status,
        media_type=media_type,
        headers={**SECURITY_HEADERS, "ETag": '"unchanged"', "Vary": "Origin", **extra_headers},
    )

    @app.get("/")
    def page() -> Response:
        return original

    add_md4a(app)
    with TestClient(app) as client:
        response = client.get("/", headers={"Accept": "text/markdown"})
    assert response.status_code == status
    assert dict(response.headers) == dict(original.headers)
    assert response.content == (
        gzip.decompress(body) if "Content-Encoding" in extra_headers else body
    )


@pytest.mark.parametrize(
    "encodings",
    [
        [b"identity", b"gzip"],
        [b"gzip", b"identity"],
        [b"identity, gzip"],
        [b"identity", b" identity, GZip "],
    ],
)
def test_encoded_response_passes_through_without_conversion_or_caching(
    encodings: list[bytes],
) -> None:
    body = gzip.compress(b"<h1>Hello</h1>")
    messages: list[Message] = [
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/html")]
            + [(b"content-encoding", value) for value in encodings],
        },
        {"type": "http.response.body", "body": body[:8], "more_body": True},
        {"type": "http.response.body", "body": body[8:], "more_body": False},
    ]
    _assert_asgi_passthrough(messages)


def test_trailer_response_passes_through_without_conversion_or_caching() -> None:
    # Exercise ASGI directly: TestClient does not expose response trailers.
    messages: list[Message] = [
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/html"), (b"trailer", b"x-checksum")],
            "trailers": True,
        },
        {"type": "http.response.body", "body": b"<h1>Hello", "more_body": True},
        {"type": "http.response.body", "body": b"</h1>", "more_body": False},
        {
            "type": "http.response.trailers",
            "headers": [(b"x-checksum", b"html-checksum")],
            "more_trailers": False,
        },
    ]
    _assert_asgi_passthrough(messages)


def _assert_asgi_passthrough(messages: list[Message]) -> None:
    sent: list[Message] = []
    store = MemoryStore()

    async def origin(scope: Scope, receive: Receive, send: Send) -> None:
        for message in messages:
            await send(message)

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"accept", b"text/markdown")],
    }
    asyncio.run(MarkdownForAgentsMiddleware(origin, store=store)(scope, receive, send))
    assert sent == messages
    assert store.get("/") is None
