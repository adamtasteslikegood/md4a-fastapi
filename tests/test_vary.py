"""Every HTML or Markdown response must vary on Accept, converted or not."""

import asyncio
import sys
from collections.abc import Callable, Iterable
from typing import Any
from wsgiref.util import FileWrapper, setup_testing_defaults
from wsgiref.validate import validator

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from md4a import MarkdownForAgentsMiddleware, MarkdownForAgentsWSGIMiddleware, add_md4a

HTML = "<h1>Hello</h1>"


def asgi_app(*, vary: str | None = None, media_type: str = "text/html", **options: Any) -> FastAPI:
    app = FastAPI()

    @app.api_route("/", methods=["GET", "HEAD", "POST"])
    def page() -> Response:
        headers = {"Vary": vary} if vary is not None else {}
        if media_type == "application/json":
            return JSONResponse({"hello": "world"}, headers=headers)
        return HTMLResponse(HTML, headers=headers, media_type=media_type)

    add_md4a(app, **options)
    return app


def asgi_vary(app: FastAPI, method: str = "GET", accept: str = "text/html") -> list[str]:
    with TestClient(app) as client:
        response = client.request(method, "/", headers={"Accept": accept})
    return response.headers.get_list("vary")


@pytest.mark.parametrize(
    ("vary", "expected"),
    [
        (None, ["Accept"]),
        ("Origin", ["Origin, Accept"]),
        ("origin, accept", ["origin, accept"]),
        ("*", ["*"]),
    ],
)
def test_asgi_html_for_browsers_varies_on_accept(vary: str | None, expected: list[str]) -> None:
    assert asgi_vary(asgi_app(vary=vary)) == expected


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_asgi_varies_get_and_head(method: str) -> None:
    assert asgi_vary(asgi_app(), method=method) == ["Accept"]


def test_asgi_leaves_other_methods_and_media_types_alone() -> None:
    assert asgi_vary(asgi_app(), method="POST") == []
    assert asgi_vary(asgi_app(media_type="application/json")) == []


def test_asgi_vary_html_false_restores_passthrough() -> None:
    assert asgi_vary(asgi_app(vary_html=False)) == []
    assert asgi_vary(asgi_app(vary="Origin", vary_html=False)) == ["Origin"]


def test_asgi_converted_markdown_names_accept_once() -> None:
    assert asgi_vary(asgi_app(), accept="text/markdown") == ["Accept"]


def test_asgi_markdown_passthrough_changes_only_vary() -> None:
    app = asgi_app(vary="Origin", max_html_bytes=1)
    with TestClient(app) as client:
        response = client.get("/", headers={"Accept": "text/markdown"})
    assert response.text == HTML
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers.get_list("vary") == ["Origin, Accept"]


def test_asgi_does_not_change_the_applications_message() -> None:
    start: Message = {
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"text/html"), (b"vary", b"Origin")],
    }
    original = [*start["headers"]]
    sent: list[Message] = []

    async def origin(scope: Scope, receive: Receive, send: Send) -> None:
        await send(start)
        await send({"type": "http.response.body", "body": b"<p>x</p>"})

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    asyncio.run(MarkdownForAgentsMiddleware(origin)(scope, receive, send))
    assert start["headers"] == original
    assert (b"vary", b"Origin, Accept") in sent[0]["headers"]


def wsgi_page(
    *, vary: str | None = None, content_type: str = "text/html; charset=utf-8"
) -> Callable[..., Iterable[bytes]]:
    def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        headers = [("Content-Type", content_type)]
        if vary is not None:
            headers.append(("Vary", vary))
        start_response("200 OK", headers)
        return [HTML.encode()]

    return app


def wsgi_call(
    app: Callable[..., Iterable[bytes]],
    method: str = "GET",
    accept: str = "text/html",
    **options: Any,
) -> tuple[list[tuple[str, str]], bytes]:
    environ: dict[str, Any] = {"REQUEST_METHOD": method, "HTTP_ACCEPT": accept, "QUERY_STRING": ""}
    setup_testing_defaults(environ)
    started: list[list[tuple[str, str]]] = []

    def start_response(status: str, headers: list[tuple[str, str]], exc_info: Any = None) -> Any:
        started.append(headers)
        return lambda data: None

    middleware = validator(MarkdownForAgentsWSGIMiddleware(validator(app), **options))
    result = middleware(environ, start_response)
    try:
        body = b"".join(result)
    finally:
        result.close()
    return started[-1], body


def vary_of(headers: list[tuple[str, str]]) -> list[str]:
    return [value for name, value in headers if name.lower() == "vary"]


@pytest.mark.parametrize(
    ("vary", "expected"),
    [
        (None, ["Accept"]),
        ("Origin", ["Origin, Accept"]),
        ("origin, accept", ["origin, accept"]),
        ("*", ["*"]),
    ],
)
def test_wsgi_html_for_browsers_varies_on_accept(vary: str | None, expected: list[str]) -> None:
    headers, body = wsgi_call(wsgi_page(vary=vary))
    assert vary_of(headers) == expected
    assert body == HTML.encode()


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_wsgi_varies_get_and_head(method: str) -> None:
    assert vary_of(wsgi_call(wsgi_page(), method=method)[0]) == ["Accept"]


def test_wsgi_leaves_other_methods_and_media_types_alone() -> None:
    assert vary_of(wsgi_call(wsgi_page(), method="POST")[0]) == []
    assert vary_of(wsgi_call(wsgi_page(content_type="application/json"))[0]) == []


def test_wsgi_vary_html_false_restores_passthrough() -> None:
    assert vary_of(wsgi_call(wsgi_page(), vary_html=False)[0]) == []


def test_wsgi_converted_markdown_names_accept_once() -> None:
    headers, body = wsgi_call(wsgi_page(), accept="text/markdown")
    assert vary_of(headers) == ["Accept"]
    assert body == b"# Hello"


def test_wsgi_markdown_passthrough_changes_only_vary() -> None:
    headers, body = wsgi_call(wsgi_page(vary="Origin"), accept="text/markdown", max_html_bytes=1)
    assert body == HTML.encode()
    assert headers == [("Content-Type", "text/html; charset=utf-8"), ("Vary", "Origin, Accept")]


def test_wsgi_keeps_file_wrapper_identity_for_browsers() -> None:
    def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> Any:
        start_response("200 OK", [("Content-Type", "text/html")])
        return environ["wsgi.file_wrapper"](iter([b"<p>file</p>"]))

    environ: dict[str, Any] = {"REQUEST_METHOD": "GET", "HTTP_ACCEPT": "text/html"}
    setup_testing_defaults(environ)
    environ["wsgi.file_wrapper"] = FileWrapper
    started: list[list[tuple[str, str]]] = []
    result = MarkdownForAgentsWSGIMiddleware(app)(
        environ, lambda status, headers, exc_info=None: started.append(headers)
    )
    assert isinstance(result, FileWrapper)
    assert vary_of(started[0]) == ["Accept"]


def test_wsgi_error_replacement_also_varies() -> None:
    def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        start_response("200 OK", [("Content-Type", "text/html")])
        try:
            raise RuntimeError("late failure")
        except RuntimeError:
            headers = [("Content-Type", "text/html")]
            start_response("500 Internal Server Error", headers, sys.exc_info())
        return [b"<p>error</p>"]

    environ: dict[str, Any] = {"REQUEST_METHOD": "GET", "HTTP_ACCEPT": "text/html"}
    setup_testing_defaults(environ)
    calls: list[tuple[str, list[tuple[str, str]], Any]] = []
    MarkdownForAgentsWSGIMiddleware(app)(
        environ, lambda status, headers, exc_info=None: calls.append((status, headers, exc_info))
    )
    assert [vary_of(headers) for _, headers, _ in calls] == [["Accept"], ["Accept"]]
    assert calls[1][2] is not None
