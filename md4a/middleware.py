from __future__ import annotations

from collections.abc import Callable, Sequence

from fastapi import FastAPI
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ._negotiation import (
    HTML_REPRESENTATION_HEADERS,
    MARKDOWN_CONTENT_TYPE,
    NEGOTIATED_MEDIA_TYPES,
    accepts_markdown,
    checked_content_signal,
    declared_charset,
    html_to_markdown,
    media_type,
    vary_with_accept,
)
from .store import MemoryStore, Store

MarkdownProvider = Callable[[str], str | None]

# ASGI header names are bytes.
_HTML_REPRESENTATION_HEADERS = {name.encode() for name in HTML_REPRESENTATION_HEADERS}


def _declared_length(headers: Headers) -> int:
    try:
        return int(headers.get("content-length", "0"))
    except ValueError:
        return 0


def _vary_negotiated(send: Send) -> Send:
    """Add Accept to Vary on every HTML or Markdown response sent through send."""

    async def send_varying(message: Message) -> None:
        if message["type"] == "http.response.start":
            raw = list(message.get("headers", []))
            headers = Headers(raw=raw)
            if media_type(headers.get("content-type", "")) in NEGOTIATED_MEDIA_TYPES:
                vary = vary_with_accept(headers.getlist("vary"))
                raw = [(name, value) for name, value in raw if name.lower() != b"vary"]
                raw.append((b"vary", vary.encode("latin-1")))
                # Copy rather than change the application's message.
                message = {**message, "headers": raw}
        await send(message)

    return send_varying


def _declared_charset(headers: Headers) -> str:
    return declared_charset(headers.get("content-type", ""))


class MarkdownForAgentsMiddleware:
    """Serve Markdown when a GET request explicitly accepts text/markdown.

    Cached/provider content wins. Otherwise the normal FastAPI route executes and
    an HTML response is converted, cached by request path, and returned as Markdown.
    Non-GET and non-Markdown requests pass through unchanged.

    Only successful HTML and Markdown responses are buffered, up to max_html_bytes.
    Other responses, and bodies over that limit, are streamed through unconverted
    and uncached.

    Cached content is served until the store drops it; give the store a ttl to
    refresh it, or pass cache_responses=False to stop writing responses to the store.

    Conversion preserves response headers except metadata tied to the HTML bytes.
    Stores contain only content: security/auth middleware must wrap this middleware
    to run on cache hits and provider responses as well as converted responses.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        store: Store | None = None,
        provider: MarkdownProvider | None = None,
        convert_html: bool = True,
        max_html_bytes: int = 5_000_000,
        cache_responses: bool = True,
        content_selector: str | None = None,
        strip_selectors: Sequence[str] = (),
        escape_misc: bool = False,
        literal_selectors: Sequence[str] = (),
        frontmatter: bool = False,
        json_ld: bool = False,
        content_signal: str | None = None,
        vary_html: bool = True,
    ) -> None:
        self.app = app
        self.store = store or MemoryStore()
        self.provider = provider
        self.convert_html = convert_html
        self.max_html_bytes = max_html_bytes
        self.cache_responses = cache_responses
        self.content_selector = content_selector
        self.strip_selectors = tuple(strip_selectors)
        self.escape_misc = escape_misc
        self.literal_selectors = tuple(literal_selectors)
        self.frontmatter = frontmatter
        self.json_ld = json_ld
        self.content_signal = checked_content_signal(content_signal)
        self.vary_html = vary_html

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if self.vary_html and scope["method"] in {"GET", "HEAD"}:
            # The HTML a browser gets is one representation of a URL that also
            # has a Markdown one, so caches must key it on Accept too.
            send = _vary_negotiated(send)
        if scope["method"] != "GET":
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
        media_type = ""
        body_parts: list[bytes] = []
        buffered = 0
        passthrough = False

        async def release() -> None:
            """Give up on conversion: forward what is held and stop buffering."""
            nonlocal passthrough
            assert start is not None
            passthrough = True
            await send(start)
            if body_parts:
                body = b"".join(body_parts)
                body_parts.clear()
                await send({"type": "http.response.body", "body": body, "more_body": True})

        async def capture(message: Message) -> None:
            nonlocal start, media_type, buffered, passthrough
            if message["type"] == "http.response.start":
                start = message
                response_headers = Headers(raw=start["headers"])
                media_type = response_headers.get("content-type", "").partition(";")[0].lower()
                convertible = 200 <= start["status"] < 300 and (
                    media_type == "text/markdown"
                    or (self.convert_html and media_type == "text/html")
                )
                # Forward all messages, including trailers, when the representation
                # cannot be converted. Only buffer bodies that may be converted or
                # cached, and never compressed, partial, or oversized content.
                passthrough = (
                    not convertible
                    or bool(start.get("trailers", False))
                    or any(
                        coding.strip().lower() != "identity"
                        for value in response_headers.getlist("content-encoding")
                        for coding in value.split(",")
                    )
                    or start["status"] == 206
                    or "content-range" in response_headers
                    or _declared_length(response_headers) > self.max_html_bytes
                )
                if passthrough:
                    await send(message)
            elif passthrough or start is None:
                # Extension messages may precede the start (for example debug).
                await send(message)
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if buffered + len(body) > self.max_html_bytes:
                    await release()
                    await send(message)
                    return
                buffered += len(body)
                body_parts.append(body)
                if not message.get("more_body", False):
                    await finish()
            else:
                # Not a body this middleware can hold (for example pathsend).
                await release()
                await send(message)

        async def finish() -> None:
            assert start is not None
            body = b"".join(body_parts)
            try:
                text = body.decode(_declared_charset(Headers(raw=start["headers"])))
                # Some codecs decode to lone surrogates, which cannot be served or stored.
                text.encode("utf-8")
            except (LookupError, UnicodeError):
                text = None
            if text is None or media_type == "text/markdown":
                # Undecodable content is returned as the application sent it, uncached.
                if text is not None and self._may_cache(start["headers"]):
                    self.store.put(key, text)
                await send(start)
                await send({"type": "http.response.body", "body": body})
                return
            converted = html_to_markdown(
                text,
                content_selector=self.content_selector,
                strip_selectors=self.strip_selectors,
                escape_misc=self.escape_misc,
                literal_selectors=self.literal_selectors,
                frontmatter=self.frontmatter,
                json_ld=self.json_ld,
            )
            if self._may_cache(start["headers"]):
                self.store.put(key, converted)
            await self._send_markdown(
                send, converted, status=start["status"], raw_headers=start["headers"]
            )

        await self.app(scope, receive, capture)

    def _may_cache(self, raw_headers: list[tuple[bytes, bytes]]) -> bool:
        """Whether a response may go in the store, which keeps its body only.

        A response with its own Content-Signal is not stored when content_signal
        is set: a cache hit would otherwise get the fallback instead of the
        application's policy.
        """
        if not self.cache_responses:
            return False
        own_signal = any(name.lower() == b"content-signal" for name, _ in raw_headers)
        return self.content_signal is None or not own_signal

    async def _send_markdown(
        self,
        send: Send,
        content: str,
        status: int = 200,
        *,
        raw_headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        body = content.encode("utf-8")
        # Copy raw pairs so repeated fields (especially Set-Cookie) survive and
        # neither the original response nor its mutable headers are modified.
        message: Message = {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (name, value)
                for name, value in (raw_headers or [])
                if name.lower() not in _HTML_REPRESENTATION_HEADERS
            ],
        }
        headers = MutableHeaders(scope=message)
        headers["content-type"] = MARKDOWN_CONTENT_TYPE
        headers["content-length"] = str(len(body))
        headers["vary"] = vary_with_accept(headers.getlist("vary"))
        # The application's own Content-Signal, when it sent one, wins.
        if self.content_signal is not None and "content-signal" not in headers:
            headers["content-signal"] = self.content_signal
        await send(message)
        await send({"type": "http.response.body", "body": body})


def add_md4a(
    app: FastAPI,
    *,
    store: Store | None = None,
    provider: MarkdownProvider | None = None,
    convert_html: bool = True,
    max_html_bytes: int = 5_000_000,
    cache_responses: bool = True,
    content_selector: str | None = None,
    strip_selectors: Sequence[str] = (),
    escape_misc: bool = False,
    literal_selectors: Sequence[str] = (),
    frontmatter: bool = False,
    json_ld: bool = False,
    content_signal: str | None = None,
    vary_html: bool = True,
) -> None:
    """Add Markdown-for-Agents negotiation to an existing FastAPI app."""
    app.add_middleware(
        MarkdownForAgentsMiddleware,
        store=store,
        provider=provider,
        convert_html=convert_html,
        max_html_bytes=max_html_bytes,
        cache_responses=cache_responses,
        content_selector=content_selector,
        strip_selectors=strip_selectors,
        escape_misc=escape_misc,
        literal_selectors=literal_selectors,
        frontmatter=frontmatter,
        json_ld=json_ld,
        content_signal=content_signal,
        vary_html=vary_html,
    )
