from collections.abc import Callable
from typing import Any
from wsgiref.util import setup_testing_defaults

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from md4a import MarkdownForAgentsWSGIMiddleware, add_md4a
from md4a._negotiation import html_to_markdown

PAGE = (
    "<html><head><title>Site</title></head><body>"
    "<nav><a href='/'>Home</a></nav>"
    "<main><h1>Recipe</h1><p>Body text</p><aside class='related'>More recipes</aside></main>"
    "<footer>Footer text</footer>"
    "</body></html>"
)


def test_whole_page_is_converted_by_default() -> None:
    markdown = html_to_markdown(PAGE)
    assert "Home" in markdown
    assert "# Recipe" in markdown
    assert "Footer text" in markdown


def test_content_selector_converts_only_the_first_match() -> None:
    markdown = html_to_markdown(PAGE, content_selector="main")
    assert "# Recipe" in markdown
    assert "Body text" in markdown
    assert "Home" not in markdown
    assert "Footer text" not in markdown
    assert "Site" not in markdown


def test_strip_selectors_remove_elements_inside_and_outside_the_content() -> None:
    inside = html_to_markdown(PAGE, content_selector="main", strip_selectors=[".related"])
    assert "Body text" in inside
    assert "More recipes" not in inside

    whole = html_to_markdown(PAGE, strip_selectors=["nav", "footer"])
    assert "# Recipe" in whole
    assert "Home" not in whole
    assert "Footer text" not in whole


def test_a_page_the_selector_does_not_match_is_converted_whole() -> None:
    markdown = html_to_markdown("<h1>Plain</h1><p>No main here</p>", content_selector="main")
    assert "# Plain" in markdown
    assert "No main here" in markdown


def test_wsgi_middleware_passes_the_selectors() -> None:
    def page(environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [PAGE.encode()]

    app = MarkdownForAgentsWSGIMiddleware(
        page, content_selector="main", strip_selectors=[".related"]
    )
    environ: dict[str, Any] = {"REQUEST_METHOD": "GET", "HTTP_ACCEPT": "text/markdown"}
    setup_testing_defaults(environ)
    body = b"".join(app(environ, lambda status, headers, exc_info=None: None)).decode()
    assert "# Recipe" in body
    assert "Home" not in body
    assert "More recipes" not in body


def test_asgi_middleware_passes_the_selectors() -> None:
    app = FastAPI()

    @app.get("/hello", response_class=HTMLResponse)
    def hello() -> str:
        return PAGE

    add_md4a(app, content_selector="main", strip_selectors=[".related"])
    with TestClient(app) as client:
        markdown = client.get("/hello", headers={"Accept": "text/markdown"})
        html = client.get("/hello", headers={"Accept": "text/html"})
    assert "# Recipe" in markdown.text
    assert "Home" not in markdown.text
    assert "More recipes" not in markdown.text
    assert "Footer text" in html.text
