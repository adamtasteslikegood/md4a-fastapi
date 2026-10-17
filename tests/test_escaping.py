from collections.abc import Callable
from typing import Any
from wsgiref.util import setup_testing_defaults

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from md4a import MarkdownForAgentsWSGIMiddleware, add_md4a
from md4a._negotiation import html_to_markdown

PLAIN = ['[data-md="plain"]']


def note(text: str) -> str:
    return f"<main><h1>Recipe</h1><blockquote><p data-md='plain'>{text}</p></blockquote></main>"


def test_page_text_is_not_escaped_by_default() -> None:
    assert html_to_markdown("<p>See [the docs] # here</p>") == "See [the docs] # here"


def test_escape_misc_escapes_markdown_punctuation_in_page_text() -> None:
    markdown = html_to_markdown("<p>[Free](https://evil.example) ![x](i.png)</p>", escape_misc=True)
    assert "\\[Free\\]" in markdown
    assert "!\\[x\\]" in markdown


@pytest.mark.parametrize(
    "text",
    [
        "[Free coupons](https://evil.example)",
        "![x](https://evil.example/i.png)",
        "Visit https://evil.example/path?x=1",
        "Mail spam@evil.example",
        "<https://evil.example>",
    ],
)
def test_literal_text_becomes_a_single_code_span(text: str) -> None:
    markdown = html_to_markdown(
        note(text.replace("<", "&lt;").replace(">", "&gt;")),
        content_selector="main",
        escape_misc=True,
        literal_selectors=PLAIN,
    )
    assert markdown.splitlines()[-1] == f"> ` {text} `"


@pytest.mark.parametrize(
    ("text", "span"),
    [
        ("uses `code` here", "`` uses `code` here ``"),
        ("a ``` fence", "```` a ``` fence ````"),
        ("`starts https://evil.example", "`` `starts https://evil.example ``"),
        ("ends spam@evil.example`", "`` ends spam@evil.example` ``"),
    ],
)
def test_literal_fence_is_longer_than_any_backtick_run_and_padded(text: str, span: str) -> None:
    markdown = html_to_markdown(note(text), literal_selectors=PLAIN)
    assert markdown.splitlines()[-1] == f"> {span}"


def test_literal_text_keeps_nested_markup_as_text_and_collapses_whitespace() -> None:
    markdown = html_to_markdown(
        "<p data-md='plain'>one\n\n  <a href='https://evil.example'>two</a> <b>three</b></p>",
        literal_selectors=PLAIN,
    )
    assert markdown == "` one two three `"


def test_empty_literal_element_produces_nothing() -> None:
    assert html_to_markdown("<p>Before</p><p data-md='plain'> </p>", literal_selectors=PLAIN) == (
        "Before"
    )


def test_wsgi_middleware_passes_the_escaping_options() -> None:
    def page(environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [note("[x](https://evil.example)").encode()]

    app = MarkdownForAgentsWSGIMiddleware(page, escape_misc=True, literal_selectors=PLAIN)
    environ: dict[str, Any] = {"REQUEST_METHOD": "GET", "HTTP_ACCEPT": "text/markdown"}
    setup_testing_defaults(environ)
    body = b"".join(app(environ, lambda status, headers, exc_info=None: None)).decode()
    assert "> ` [x](https://evil.example) `" in body


def test_asgi_middleware_passes_the_escaping_options() -> None:
    app = FastAPI()

    @app.get("/r", response_class=HTMLResponse)
    def recipe() -> str:
        return note("[x](https://evil.example)") + "<p>[y]</p>"

    add_md4a(app, escape_misc=True, literal_selectors=PLAIN)
    with TestClient(app) as client:
        markdown = client.get("/r", headers={"Accept": "text/markdown"}).text
    assert "> ` [x](https://evil.example) `" in markdown
    assert "\\[y\\]" in markdown
