"""Frontmatter, JSON-LD, and Content-Signal, in the layout of Cloudflare's Markdown for Agents."""

import json
from collections.abc import Callable
from typing import Any
from wsgiref.util import setup_testing_defaults

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from md4a import MarkdownForAgentsMiddleware, MarkdownForAgentsWSGIMiddleware, MemoryStore, add_md4a
from md4a._negotiation import html_to_markdown

RECIPE = {"@context": "https://schema.org", "@type": "Recipe", "name": "Tofu scramble"}

PAGE = (
    "<html><head><title>Ignored title element</title>"
    '<meta property="og:title" content="OG title">'
    '<meta name="title" content="Page title">'
    '<meta property="og:description" content="OG description">'
    '<meta name="description" content="Page description">'
    '<meta property="og:image" content="https://example.com/cover.png">'
    f'<script type="application/ld+json">{json.dumps(RECIPE)}</script>'
    "</head><body><nav>Nav</nav><main><h1>Recipe</h1><p>Body text</p></main></body></html>"
)


def frontmatter_of(markdown: str) -> dict[str, str]:
    """Parse the block the way a YAML reader would read md4a's JSON-string values."""
    lines = markdown.split("\n")
    assert lines[0] == "---"
    end = lines.index("---", 1)
    fields = {}
    for line in lines[1:end]:
        key, _, value = line.partition(": ")
        fields[key] = json.loads(value)
    return fields


def json_ld_of(markdown: str) -> list[Any]:
    blocks = []
    lines = markdown.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```") and line.lstrip("`") == "json":
            fence = line[: len(line) - len("json")]
            end = lines.index(fence, index + 1)
            blocks.append(json.loads("\n".join(lines[index + 1 : end])))
            index = end
        index += 1
    return blocks


def test_options_are_off_by_default() -> None:
    assert html_to_markdown(PAGE) == html_to_markdown(PAGE, frontmatter=False, json_ld=False)
    assert "---" not in html_to_markdown(PAGE, content_selector="main")


def test_frontmatter_prefers_standard_meta_over_open_graph() -> None:
    markdown = html_to_markdown(PAGE, content_selector="main", frontmatter=True)
    assert frontmatter_of(markdown) == {
        "title": "Page title",
        "description": "Page description",
        "image": "https://example.com/cover.png",
    }
    assert markdown.split("---\n\n", 1)[1].startswith("# Recipe")
    assert "Nav" not in markdown


def test_frontmatter_falls_back_to_open_graph_and_omits_missing_fields() -> None:
    page = '<head><meta property="og:title" content="Only OG"></head><p>x</p>'
    assert frontmatter_of(html_to_markdown(page, frontmatter=True)) == {"title": "Only OG"}


def test_frontmatter_is_left_out_when_the_page_has_no_metadata() -> None:
    page = "<html><head><title>T</title></head><body><p>x</p></body></html>"
    assert html_to_markdown(page, frontmatter=True, json_ld=True) == html_to_markdown(page)


def test_frontmatter_reads_the_whole_document_whatever_the_selectors_keep() -> None:
    markdown = html_to_markdown(
        PAGE, content_selector="main", strip_selectors=["meta", "head"], frontmatter=True
    )
    assert frontmatter_of(markdown)["title"] == "Page title"


def test_frontmatter_values_cannot_inject_yaml() -> None:
    hostile = "A &quot;quoted&quot;\n---\nadmin: true\n# not a comment: [x]"
    page = (
        f'<head><meta name="Description" content="{hostile}">'
        '<meta name="title" content="   spaced\t  out  "></head><p>x</p>'
    )
    markdown = html_to_markdown(page, frontmatter=True)
    fields = frontmatter_of(markdown)
    assert fields == {
        "title": "spaced out",
        "description": 'A "quoted" --- admin: true # not a comment: [x]',
    }
    assert markdown.count("\n---") == 1


def test_json_ld_blocks_are_appended_once_whatever_their_position() -> None:
    second = {"@type": "BreadcrumbList", "itemListElement": []}
    page = PAGE.replace(
        "<p>Body text</p>",
        f'<p>Body text</p><script type="application/ld+json">{json.dumps(second)}</script>',
    )
    markdown = html_to_markdown(page, content_selector="main", json_ld=True)
    assert json_ld_of(markdown) == [RECIPE, second]
    assert markdown.count("Tofu scramble") == 1
    assert markdown.startswith("# Recipe")
    assert markdown.rstrip().endswith("```")


def test_json_ld_skips_invalid_scripts_and_other_script_types() -> None:
    page = (
        '<script type="application/ld+json">{not json</script>'
        '<script type="application/json">{"other": true}</script>'
        '<script type="Application/LD+JSON; charset=utf-8">{"@type": "Thing"}</script>'
        "<p>x</p>"
    )
    assert json_ld_of(html_to_markdown(page, json_ld=True)) == [{"@type": "Thing"}]


def test_json_ld_fence_is_longer_than_any_backtick_run_in_the_data() -> None:
    data = {"name": "Run ``` this", "other": "`````"}
    page = f'<script type="application/ld+json">{json.dumps(data)}</script><p>x</p>'
    markdown = html_to_markdown(page, json_ld=True)
    assert "``````json\n" in markdown
    assert json_ld_of(markdown) == [data]


def test_frontmatter_and_json_ld_together_follow_cloudflares_order() -> None:
    markdown = html_to_markdown(PAGE, content_selector="main", frontmatter=True, json_ld=True)
    assert markdown.startswith("---\n")
    assert markdown.index("# Recipe") < markdown.index("```json")
    assert markdown.endswith("```\n")


def asgi_client(**options: Any) -> TestClient:
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return PAGE

    @app.get("/signed", response_class=HTMLResponse)
    def signed() -> HTMLResponse:
        return HTMLResponse(PAGE, headers={"Content-Signal": "ai-train=no"})

    add_md4a(app, **options)
    return TestClient(app)


def test_asgi_middleware_passes_frontmatter_and_json_ld() -> None:
    with asgi_client(content_selector="main", frontmatter=True, json_ld=True) as client:
        markdown = client.get("/", headers={"Accept": "text/markdown"}).text
    assert frontmatter_of(markdown)["title"] == "Page title"
    assert json_ld_of(markdown) == [RECIPE]


def test_asgi_content_signal_is_added_to_markdown_only() -> None:
    with asgi_client(content_signal="ai-train=yes, search=yes, ai-input=yes") as client:
        markdown = client.get("/", headers={"Accept": "text/markdown"})
        html = client.get("/", headers={"Accept": "text/html"})
        signed = client.get("/signed", headers={"Accept": "text/markdown"})
    assert markdown.headers["content-signal"] == "ai-train=yes, search=yes, ai-input=yes"
    assert "content-signal" not in html.headers
    assert signed.headers.get_list("content-signal") == ["ai-train=no"]


def test_asgi_content_signal_applies_to_cached_and_provider_markdown() -> None:
    store = MemoryStore()
    store.put("/", "# Cached\n")
    app = FastAPI()
    add_md4a(app, store=store, provider=lambda key: "# Provided\n", content_signal="search=yes")
    with TestClient(app) as client:
        cached = client.get("/", headers={"Accept": "text/markdown"})
        provided = client.get("/other", headers={"Accept": "text/markdown"})
    assert cached.headers["content-signal"] == "search=yes"
    assert provided.headers["content-signal"] == "search=yes"


@pytest.mark.parametrize("value", ["a\r\nX-Injected: 1", "a\nb", "a\0"])
def test_content_signal_must_be_one_header_line(value: str) -> None:
    with pytest.raises(ValueError, match="single header line"):
        MarkdownForAgentsMiddleware(FastAPI(), content_signal=value)
    with pytest.raises(ValueError, match="single header line"):
        MarkdownForAgentsWSGIMiddleware(lambda environ, start: [], content_signal=value)


def wsgi_call(
    app: Callable[..., Any], accept: str = "text/markdown", **options: Any
) -> tuple[list[tuple[str, str]], str]:
    environ: dict[str, Any] = {"REQUEST_METHOD": "GET", "HTTP_ACCEPT": accept}
    setup_testing_defaults(environ)
    started: list[list[tuple[str, str]]] = []
    result = MarkdownForAgentsWSGIMiddleware(app, **options)(
        environ, lambda status, headers, exc_info=None: started.append(headers)
    )
    body = b"".join(result).decode()
    getattr(result, "close", lambda: None)()
    return started[-1], body


def wsgi_page(headers: list[tuple[str, str]] | None = None) -> Callable[..., Any]:
    def app(environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), *(headers or [])])
        return [PAGE.encode()]

    return app


def test_wsgi_middleware_passes_frontmatter_json_ld_and_content_signal() -> None:
    headers, markdown = wsgi_call(
        wsgi_page(), content_selector="main", frontmatter=True, json_ld=True, content_signal="x=y"
    )
    assert frontmatter_of(markdown)["description"] == "Page description"
    assert json_ld_of(markdown) == [RECIPE]
    assert ("Content-Signal", "x=y") in headers


def test_wsgi_applications_own_content_signal_wins() -> None:
    headers, _ = wsgi_call(wsgi_page([("Content-Signal", "ai-train=no")]), content_signal="x=y")
    assert [value for name, value in headers if name.lower() == "content-signal"] == ["ai-train=no"]


def test_wsgi_content_signal_is_not_added_to_html() -> None:
    headers, _ = wsgi_call(wsgi_page(), accept="text/html", content_signal="x=y")
    assert all(name.lower() != "content-signal" for name, _ in headers)
