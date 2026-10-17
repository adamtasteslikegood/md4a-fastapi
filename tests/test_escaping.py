from collections.abc import Callable
from typing import Any
from wsgiref.util import setup_testing_defaults

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from markdown_it import MarkdownIt

from md4a import MarkdownForAgentsWSGIMiddleware, add_md4a
from md4a._negotiation import html_to_markdown

PLAIN = ['[data-md="plain"]']
EVIL = "[click](https://evil.example) ![x](https://evil.example/i.png)"
# CommonMark with GFM tables, as agents' Markdown readers commonly parse it.
GFM = MarkdownIt("commonmark").enable("table")


def note(text: str) -> str:
    return f"<main><h1>Recipe</h1><blockquote><p data-md='plain'>{text}</p></blockquote></main>"


def inline_tokens(markdown: str) -> list[Any]:
    return [child for token in GFM.parse(markdown) for child in token.children or []]


def code_spans(markdown: str) -> list[str]:
    return [token.content for token in inline_tokens(markdown) if token.type == "code_inline"]


def assert_inert(markdown: str) -> None:
    """No link or image survives parsing."""
    active = [t.type for t in inline_tokens(markdown) if t.type in {"link_open", "image"}]
    assert active == [], markdown


def convert_direct(html: str) -> str:
    return html_to_markdown(html, escape_misc=True, literal_selectors=PLAIN)


def convert_wsgi(html: str) -> str:
    def page(environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [html.encode()]

    app = MarkdownForAgentsWSGIMiddleware(page, escape_misc=True, literal_selectors=PLAIN)
    environ: dict[str, Any] = {"REQUEST_METHOD": "GET", "HTTP_ACCEPT": "text/markdown"}
    setup_testing_defaults(environ)
    return b"".join(app(environ, lambda status, headers, exc_info=None: None)).decode()


def convert_asgi(html: str) -> str:
    app = FastAPI()

    @app.get("/r", response_class=HTMLResponse)
    def recipe() -> str:
        return html

    add_md4a(app, escape_misc=True, literal_selectors=PLAIN)
    with TestClient(app) as client:
        return client.get("/r", headers={"Accept": "text/markdown"}).text


CONVERTERS = [convert_direct, convert_wsgi, convert_asgi]


def test_page_text_is_not_escaped_by_default() -> None:
    assert html_to_markdown("<p>See [the docs] # here</p>").strip() == "See [the docs] # here"


def test_escape_misc_escapes_markdown_punctuation_in_page_text() -> None:
    markdown = html_to_markdown("<p>[Free](https://evil.example) ![x](i.png)</p>", escape_misc=True)
    # markdownify before 1.0 escapes only the opening bracket, which is enough.
    assert "\\[Free" in markdown
    assert "!\\[x" in markdown
    assert_inert(markdown)


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
    assert markdown.strip().splitlines()[-1] == f"> ` {text} `"
    assert code_spans(markdown) == [text]
    assert_inert(markdown)


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
    assert markdown.strip().splitlines()[-1] == f"> {span}"
    assert code_spans(markdown) == [text]


def test_literal_text_keeps_nested_markup_as_text_and_collapses_whitespace() -> None:
    markdown = html_to_markdown(
        "<p data-md='plain'>one\n\n  <a href='https://evil.example'>two</a> <b>three</b></p>",
        literal_selectors=PLAIN,
    )
    assert markdown.strip() == "` one two three `"


def test_empty_literal_element_produces_nothing() -> None:
    markdown = html_to_markdown("<p>Before</p><p data-md='plain'> </p>", literal_selectors=PLAIN)
    assert markdown.strip() == "Before"


@pytest.mark.parametrize(
    "texts",
    [
        ("foo", "x ` " + EVIL),
        ("a ``", "`` b ` " + EVIL),
        ("`", "``` " + EVIL + " `"),
    ],
)
def test_adjacent_literal_spans_cannot_merge(texts: tuple[str, str]) -> None:
    html = "<p>" + "".join(f'<span data-md="plain">{t}</span>' for t in texts) + "</p>"
    markdown = convert_direct(html)
    assert_inert(markdown)
    assert code_spans(markdown) == list(texts)


def test_an_unmatched_backtick_in_page_text_cannot_open_into_a_literal_span() -> None:
    # Without escape_misc the page's own lone backtick would start a code span
    # that ends inside the literal text; escape_misc escapes it.
    html = '<p>code`<span data-md="plain">` ' + EVIL + "</span>`more</p>"
    markdown = convert_direct(html)
    assert_inert(markdown)
    assert "` " + EVIL in code_spans(markdown)


@pytest.mark.parametrize(
    "cell",
    ["a|" + EVIL + "|b", "a\\|" + EVIL + "\\|b", "ends with a backslash\\", "|"],
)
def test_literal_table_cells_escape_pipes_and_keep_the_cell_count(cell: str) -> None:
    html = (
        "<table><tr><th>A</th><th>B</th><th>C</th></tr>"
        f'<tr><td>1</td><td data-md="plain">{cell}</td><td>3</td></tr></table>'
    )
    markdown = convert_direct(html)
    assert_inert(markdown)
    assert sum(token.type == "td_open" for token in GFM.parse(markdown)) == 3
    assert code_spans(markdown) == [cell]


def test_pipes_outside_tables_are_not_escaped() -> None:
    assert convert_direct('<p data-md="plain">a|b</p>').strip() == "` a|b `"


@pytest.mark.parametrize("convert", CONVERTERS)
@pytest.mark.parametrize(
    ("element", "text"),
    [
        ('<a data-md="plain" href="https://evil.example">Click me</a>', "Click me"),
        ('<img data-md="plain" alt="x" src="https://evil.example/i.png">', None),
        ('<em data-md="plain">' + EVIL + "</em>", EVIL),
        ('<code data-md="plain">``` ' + EVIL + "</code>", "``` " + EVIL),
        ('<pre data-md="plain">```\n' + EVIL + "</pre>", "``` " + EVIL),
    ],
)
def test_a_matched_element_loses_its_own_link_and_image_syntax(
    convert: Callable[[str], str], element: str, text: str | None
) -> None:
    markdown = convert(f"<main><p>Before</p>{element}<p>After</p></main>")
    assert_inert(markdown)
    assert code_spans(markdown) == ([text] if text else [])
    assert "Before" in markdown
    assert "After" in markdown


def test_nested_matches_are_converted_once() -> None:
    html = '<div data-md="plain">outer <span data-md="plain">inner</span></div>'
    assert convert_direct(html).strip() == "` outer inner `"


@pytest.mark.parametrize("convert", [convert_wsgi, convert_asgi])
def test_middlewares_pass_the_escaping_options(convert: Callable[[str], str]) -> None:
    markdown = convert(note("[x](https://evil.example)") + "<p>[y]</p>")
    assert "> ` [x](https://evil.example) `" in markdown
    assert "\\[y" in markdown
    assert_inert(markdown)
