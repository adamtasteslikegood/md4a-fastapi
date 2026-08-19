from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from markdownify import markdownify
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .store import MemoryStore, Store

MarkdownProvider = Callable[[str], str | None]


def accepts_markdown(value: str) -> bool:
    """Return true when text/markdown is an accepted media range (q=0 excluded)."""
    for item in value.lower().split(","):
        media, *parameters = (part.strip() for part in item.split(";"))
        if media != "text/markdown":
            continue
        quality = next((p.partition("=")[2] for p in parameters if p.startswith("q=")), "1")
        try:
            return float(quality) > 0
        except ValueError:
            return False
    return False


class MarkdownForAgentsMiddleware:
    """Serve Markdown when a GET request explicitly accepts text/markdown.

    Cached/provider content wins. Otherwise the normal FastAPI route executes and
    an HTML response is converted, cached by request path, and returned as Markdown.
    Non-GET and non-Markdown requests pass through unchanged.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        store: Store | None = None,
        provider: MarkdownProvider | None = None,
        convert_html: bool = True,
        max_html_bytes: int = 5_000_000,
    ) -> None:
        self.app = app
        self.store = store or MemoryStore()
        self.provider = provider
        self.convert_html = convert_html
        self.max_html_bytes = max_html_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET":
            await self.app(scope, receive, send)
            return
        request_headers = Headers(scope=scope)
        if not accepts_markdown(request_headers.get("accept", "")):
            await self.app(scope, receive, send)
            return

        key = scope.get("raw_path", scope["path"].encode()).decode()
        if scope.get("query_string"):
            key += "?" + scope["query_string"].decode()
        content = self.store.get(key)
        if content is None and self.provider is not None:
            content = self.provider(key)
        if content is not None:
            await self._send_markdown(send, content)
            return

        start: Message | None = None
        body_parts: list[bytes] = []

        async def capture(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))
                if not message.get("more_body", False):
                    await finish()

        async def finish() -> None:
            assert start is not None
            response_headers = Headers(raw=start["headers"])
            media_type = response_headers.get("content-type", "").partition(";")[0].lower()
            body = b"".join(body_parts)
            if media_type == "text/markdown":
                if 200 <= start["status"] < 300:
                    self.store.put(key, body.decode("utf-8"))
                await send(start)
                await send({"type": "http.response.body", "body": body})
            elif (
                self.convert_html
                and 200 <= start["status"] < 300
                and media_type == "text/html"
                and len(body) <= self.max_html_bytes
            ):
                converted = markdownify(body.decode("utf-8"), heading_style="ATX")
                self.store.put(key, converted)
                await self._send_markdown(send, converted, status=start["status"])
            else:
                await send(start)
                await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, capture)

    @staticmethod
    async def _send_markdown(send: Send, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        message: Message = {"type": "http.response.start", "status": status, "headers": []}
        headers = MutableHeaders(scope=message)
        headers["content-type"] = "text/markdown; charset=utf-8"
        headers["content-length"] = str(len(body))
        headers["vary"] = "Accept"
        await send(message)
        await send({"type": "http.response.body", "body": body})


def add_md4a(
    app: FastAPI,
    *,
    store: Store | None = None,
    provider: MarkdownProvider | None = None,
    convert_html: bool = True,
) -> None:
    """Add Markdown-for-Agents negotiation to an existing FastAPI app."""
    app.add_middleware(
        MarkdownForAgentsMiddleware,
        store=store,
        provider=provider,
        convert_html=convert_html,
    )
