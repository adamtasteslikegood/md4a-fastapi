import subprocess
import sys
from collections.abc import Callable, Iterable, Iterator
from typing import Any
from wsgiref.util import setup_testing_defaults
from wsgiref.validate import validator

import pytest

from md4a import MarkdownForAgentsWSGIMiddleware, MemoryStore

Headers = list[tuple[str, str]]


class Result:
    def __init__(self, status: str, headers: Headers, body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body

    def all(self, name: str) -> list[str]:
        return [value for field, value in self.headers if field.lower() == name.lower()]

    def one(self, name: str) -> str:
        (value,) = self.all(name)
        return value


def page(
    body: bytes = b"<h1>Hello</h1><p>Agent world</p>",
    *,
    status: str = "200 OK",
    content_type: str = "text/html; charset=utf-8",
    headers: Headers | None = None,
) -> Callable[..., Iterable[bytes]]:
    def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        start_response(status, [("Content-Type", content_type), *(headers or [])])
        return [body]

    return app


def call(
    app: Callable[..., Iterable[bytes]],
    path: str = "/hello",
    *,
    accept: str = "text/markdown",
    method: str = "GET",
    query: str = "",
) -> Result:
    """Run one request, with wsgiref's validator checking what the middleware emits."""
    environ: dict[str, Any] = {
        "REQUEST_METHOD": method,
        "SCRIPT_NAME": "",
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "HTTP_ACCEPT": accept,
    }
    setup_testing_defaults(environ)
    seen: dict[str, Any] = {}

    def start_response(status: str, headers: Headers, exc_info: Any = None) -> Callable[..., None]:
        seen.update(status=status, headers=headers)
        return seen.setdefault("written", []).append

    result = validator(app)(environ, start_response)
    try:
        body = b"".join(result)
    finally:
        result.close()  # type: ignore[attr-defined]
    return Result(seen["status"], seen["headers"], b"".join(seen.get("written", [])) + body)


def wrap(app: Callable[..., Iterable[bytes]], **options: Any) -> MarkdownForAgentsWSGIMiddleware:
    # The inner validator checks that the middleware calls the application correctly,
    # including closing the iterable it returns.
    return MarkdownForAgentsWSGIMiddleware(validator(app), **options)


def test_converts_and_caches_html() -> None:
    store = MemoryStore()
    response = call(wrap(page(), store=store))
    assert response.status == "200 OK"
    assert response.one("Content-Type") == "text/markdown; charset=utf-8"
    assert response.one("Vary") == "Accept"
    assert response.one("Content-Length") == str(len(response.body))
    assert "# Hello" in response.body.decode()
    assert store.get("/hello") == response.body.decode()


@pytest.mark.parametrize(
    ("accept", "method"),
    [("text/html", "GET"), ("text/markdown;q=0", "GET"), ("text/markdown", "POST")],
)
def test_other_requests_pass_through_unchanged(accept: str, method: str) -> None:
    store = MemoryStore()
    response = call(wrap(page(), store=store), accept=accept, method=method)
    assert response.one("Content-Type") == "text/html; charset=utf-8"
    assert response.body == b"<h1>Hello</h1><p>Agent world</p>"
    assert response.all("Vary") == []
    assert store.data == {}


def test_provider_wins_without_running_the_application() -> None:
    def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        raise AssertionError("the application must not run on a provider hit")

    middleware = MarkdownForAgentsWSGIMiddleware(
        app, provider=lambda key: "# Known\n" if key == "/known" else None
    )
    response = call(middleware, "/known")
    assert response.body == b"# Known\n"
    assert response.one("Vary") == "Accept"


@pytest.mark.parametrize(
    "app",
    [
        page(status="404 Not Found"),
        page(b'{"html": true}', content_type="application/json"),
        page(headers=[("Content-Encoding", "gzip")]),
        page(status="206 Partial Content"),
        page(headers=[("Content-Range", "bytes 0-9/100")]),
    ],
    ids=["not-found", "json", "compressed", "partial", "content-range"],
)
def test_unconvertible_responses_pass_through_uncached(
    app: Callable[..., Iterable[bytes]],
) -> None:
    store = MemoryStore()
    direct = call(app)
    response = call(wrap(app, store=store))
    assert (response.status, response.headers, response.body) == (
        direct.status,
        direct.headers,
        direct.body,
    )
    assert store.data == {}


def test_conversion_keeps_application_headers_and_drops_html_metadata() -> None:
    app = page(
        headers=[
            ("Set-Cookie", "first=one; HttpOnly"),
            ("Set-Cookie", "second=two; Secure"),
            ("Cache-Control", "public, max-age=60"),
            ("X-Frame-Options", "DENY"),
            ("ETag", '"html-only"'),
            ("Last-Modified", "Tue, 06 Oct 2026 00:00:00 GMT"),
            ("Content-Length", "32"),
            ("Vary", "Cookie"),
        ]
    )
    response = call(wrap(app))
    assert response.all("Set-Cookie") == ["first=one; HttpOnly", "second=two; Secure"]
    assert response.one("Cache-Control") == "public, max-age=60"
    assert response.one("X-Frame-Options") == "DENY"
    assert response.all("ETag") == []
    assert response.all("Last-Modified") == []
    assert response.one("Content-Length") == str(len(response.body))
    assert response.one("Vary") == "Cookie, Accept"


@pytest.mark.parametrize(("vary", "expected"), [("*", "*"), ("accept", "accept")])
def test_vary_is_not_duplicated(vary: str, expected: str) -> None:
    response = call(wrap(page(headers=[("Vary", vary)])))
    assert response.one("Vary") == expected


def test_body_over_the_limit_is_streamed_through_uncached() -> None:
    chunks = [b"<p>one</p>", b"<p>two</p>", b"<p>three</p>"]

    def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterator[bytes]:
        start_response("200 OK", [("Content-Type", "text/html")])
        yield from chunks

    store = MemoryStore()
    response = call(wrap(app, store=store, max_html_bytes=15))
    assert response.one("Content-Type") == "text/html"
    assert response.body == b"".join(chunks)
    assert store.data == {}


def test_declared_length_over_the_limit_is_not_buffered() -> None:
    body = b"<p>" + b"x" * 40 + b"</p>"
    store = MemoryStore()
    response = call(
        wrap(
            page(body, headers=[("Content-Length", str(len(body)))]),
            store=store,
            max_html_bytes=10,
        )
    )
    assert response.one("Content-Type") == "text/html; charset=utf-8"
    assert response.body == body
    assert store.data == {}


def test_legacy_write_callable_passes_through() -> None:
    def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        write = start_response("200 OK", [("Content-Type", "text/html")])
        write(b"<h1>Written</h1>")
        return [b"<p>returned</p>"]

    store = MemoryStore()
    response = call(wrap(app, store=store))
    assert response.one("Content-Type") == "text/html"
    assert response.body == b"<h1>Written</h1><p>returned</p>"
    assert store.data == {}


def test_html_is_decoded_with_declared_charset() -> None:
    app = page("<h1>Café</h1>".encode("latin-1"), content_type="text/html; charset=latin-1")
    assert "# Café" in call(wrap(app)).body.decode("utf-8")


def test_undecodable_html_is_returned_as_sent() -> None:
    body = b"<h1>\xff\xfe</h1>"
    store = MemoryStore()
    response = call(wrap(page(body), store=store))
    assert response.one("Content-Type") == "text/html; charset=utf-8"
    assert response.body == body
    assert store.data == {}


def test_existing_markdown_is_cached_and_returned() -> None:
    store = MemoryStore()
    response = call(wrap(page(b"# Native\n", content_type="text/markdown"), store=store))
    assert response.body == b"# Native\n"
    assert store.get("/hello") == "# Native\n"


def test_cache_key_is_the_encoded_path_and_query() -> None:
    store = MemoryStore()
    # WSGI hands the application the percent-decoded path, as latin-1.
    call(wrap(page(), store=store), "/caf\xc3\xa9 au lait", query="page=2")
    assert list(store.data) == ["/caf%C3%A9%20au%20lait?page=2"]


def test_cached_markdown_is_served_on_the_next_request() -> None:
    calls = 0

    def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        nonlocal calls
        calls += 1
        start_response("200 OK", [("Content-Type", "text/html")])
        return [b"<h1>Once</h1>"]

    middleware = wrap(app)
    first = call(middleware)
    second = call(middleware)
    assert calls == 1
    assert second.body == first.body


def test_cache_responses_false_leaves_the_store_empty() -> None:
    store = MemoryStore()
    call(wrap(page(), store=store, cache_responses=False))
    assert store.data == {}


def test_convert_html_false_passes_html_through() -> None:
    response = call(wrap(page(), convert_html=False))
    assert response.one("Content-Type") == "text/html; charset=utf-8"


def test_importing_the_wsgi_middleware_does_not_import_an_asgi_framework() -> None:
    script = (
        "import sys, md4a.wsgi\n"
        "from md4a import MarkdownForAgentsWSGIMiddleware\n"
        "loaded = {'fastapi', 'starlette', 'httpx', 'uvicorn'} & set(sys.modules)\n"
        "assert not loaded, loaded\n"
    )
    subprocess.run([sys.executable, "-c", script], check=True)
