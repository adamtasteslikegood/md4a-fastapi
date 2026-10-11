import asyncio

import pytest
from starlette.types import Message, Receive, Scope, Send

from md4a import MemoryStore
from md4a.middleware import MarkdownForAgentsMiddleware


def _start(media_type: bytes, *extra: tuple[bytes, bytes], status: int = 200) -> Message:
    return {
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", media_type), *extra],
    }


def _body(*chunks: bytes) -> list[Message]:
    return [
        {"type": "http.response.body", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]


def _run(
    messages: list[Message], *, max_html_bytes: int = 5_000_000
) -> tuple[list[Message], list[int], MemoryStore]:
    """Return what was sent, how much had been sent after each origin message, and the store."""
    sent: list[Message] = []
    progress: list[int] = []
    store = MemoryStore()

    async def origin(scope: Scope, receive: Receive, send: Send) -> None:
        for message in messages:
            await send(message)
            progress.append(len(sent))

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
    middleware = MarkdownForAgentsMiddleware(origin, store=store, max_html_bytes=max_html_bytes)
    asyncio.run(middleware(scope, receive, send))
    return sent, progress, store


def _sent_body(sent: list[Message]) -> bytes:
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


@pytest.mark.parametrize(
    "start",
    [
        _start(b"text/event-stream"),
        _start(b"application/json"),
        _start(b"text/html", status=500),
        _start(b"text/markdown", status=404),
    ],
)
def test_nonconvertible_response_is_streamed_as_it_arrives(start: Message) -> None:
    messages = [start, *_body(b"one", b"two", b"three")]

    sent, progress, store = _run(messages)

    assert sent == messages
    assert progress == [1, 2, 3, 4]
    assert store.get("/") is None


@pytest.mark.parametrize("media_type", [b"text/html", b"text/markdown"])
def test_response_declaring_oversized_content_length_is_streamed(media_type: bytes) -> None:
    messages = [_start(media_type, (b"content-length", b"12")), *_body(b"<p>abc", b"def</p>")]

    sent, progress, store = _run(messages, max_html_bytes=10)

    assert sent == messages
    assert progress == [1, 2, 3]
    assert store.get("/") is None


@pytest.mark.parametrize("media_type", [b"text/html", b"text/markdown"])
def test_response_exceeding_limit_while_buffering_is_passed_through(media_type: bytes) -> None:
    start = _start(media_type, (b"etag", b'"original"'))
    chunks = [b"<p>abc", b"defgh", b"ijk", b"</p>"]

    sent, progress, store = _run([start, *_body(*chunks)], max_html_bytes=10)

    assert sent[0] == start
    assert _sent_body(sent) == b"".join(chunks)
    assert sent[-1].get("more_body", False) is False
    assert all(m.get("more_body") is True for m in sent[1:-1])
    # Nothing is sent while under the limit; once over it, chunks are no longer held back.
    assert progress[1] == 0
    assert progress[2] > 0
    assert progress[-1] == len(sent) == progress[-2] + 1
    assert store.get("/") is None


def test_response_exactly_at_limit_is_converted() -> None:
    sent, _, store = _run([_start(b"text/html"), *_body(b"<p>ab", b"c</p>")], max_html_bytes=10)

    assert (b"content-type", b"text/markdown; charset=utf-8") in sent[0]["headers"]
    assert _sent_body(sent).strip() == b"abc"
    assert store.get("/") is not None


def test_unbufferable_message_while_buffering_is_passed_through() -> None:
    # e.g. FileResponse with the ASGI pathsend extension: there is no body to convert.
    messages: list[Message] = [
        _start(b"text/html"),
        {"type": "http.response.pathsend", "path": "/srv/page.html"},
    ]

    sent, _, store = _run(messages)

    assert sent == messages
    assert store.get("/") is None


def test_message_before_response_start_is_forwarded_and_response_still_converted() -> None:
    # Starlette template responses emit http.response.debug before the start message.
    debug: Message = {"type": "http.response.debug", "info": {"template": "page.html"}}

    sent, _, store = _run([debug, _start(b"text/html"), *_body(b"<p>abc</p>")])

    assert sent[0] == debug
    assert (b"content-type", b"text/markdown; charset=utf-8") in sent[1]["headers"]
    assert _sent_body(sent).strip() == b"abc"
    assert store.get("/") is not None
