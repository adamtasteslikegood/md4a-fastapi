import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from md4a import MemoryStore, add_md4a


def _get(body: bytes, content_type: str) -> tuple[Response, MemoryStore]:
    app = FastAPI()
    store = MemoryStore()

    @app.get("/")
    def page() -> Response:
        return Response(body, headers={"Content-Type": content_type})

    add_md4a(app, store=store)
    with TestClient(app) as client:
        return client.get("/", headers={"Accept": "text/markdown"}), store


@pytest.mark.parametrize(
    "content_type",
    ["text/html; charset=iso-8859-1", 'text/html; version=1; Charset="ISO-8859-1"'],
)
def test_html_is_decoded_with_declared_charset(content_type: str) -> None:
    response, store = _get("<p>café</p>".encode("iso-8859-1"), content_type)

    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.content.decode("utf-8").strip() == "café"
    assert store.get("/").strip() == "café"


def test_markdown_is_cached_using_declared_charset() -> None:
    body = "# café".encode("iso-8859-1")

    response, store = _get(body, "text/markdown; charset=iso-8859-1")

    assert response.content == body
    assert response.headers["content-type"] == "text/markdown; charset=iso-8859-1"
    assert store.get("/") == "# café"


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"<p>caf\xe9</p>", "text/html"),
        (b"<p>caf\xe9</p>", "text/html; charset=utf-8"),
        (b"<p>cafe</p>", "text/html; charset=x-no-such-charset"),
        (b"# caf\xe9", "text/markdown"),
    ],
)
def test_undecodable_response_is_returned_unchanged_and_not_cached(
    body: bytes, content_type: str
) -> None:
    response, store = _get(body, content_type)

    assert response.status_code == 200
    assert response.content == body
    assert response.headers["content-type"] == content_type
    assert store.get("/") is None


def test_charset_inside_quoted_parameter_value_is_ignored() -> None:
    content_type = 'text/html; profile="x;charset=iso-8859-1"; charset=utf-8'

    response, store = _get("<p>café</p>".encode(), content_type)

    assert response.content.decode("utf-8").strip() == "café"
    assert store.get("/").strip() == "café"


@pytest.mark.parametrize("media_type", ["text/html", "text/markdown"])
def test_text_that_cannot_be_served_as_utf8_is_returned_unchanged_and_not_cached(
    media_type: str,
) -> None:
    # UTF-7 can decode to a lone surrogate, which cannot be encoded as UTF-8.
    body = b"<p>+2AA-</p>"
    content_type = f"{media_type}; charset=utf-7"

    response, store = _get(body, content_type)

    assert response.status_code == 200
    assert response.content == body
    assert response.headers["content-type"] == content_type
    assert store.get("/") is None
