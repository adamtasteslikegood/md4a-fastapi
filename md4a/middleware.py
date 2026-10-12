from __future__ import annotations

from collections.abc import Callable
from email.message import Message as EmailMessage

from fastapi import FastAPI
from markdownify import markdownify
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .store import MemoryStore, Store

MarkdownProvider = Callable[[str], str | None]

# These describe the original HTML bytes and cannot be reused after conversion.
_HTML_REPRESENTATION_HEADERS = {
    b"content-encoding",
    b"content-location",
    b"content-range",
    b"accept-ranges",
    b"etag",
    b"last-modified",
    b"content-md5",
    b"digest",
    b"content-digest",
    b"repr-digest",
    b"transfer-encoding",
    b"trailer",
}


def _declared_length(headers: Headers) -> int:
    try:
        return int(headers.get("content-length", "0"))
    except ValueError:
        return 0


def _declared_charset(headers: Headers) -> str:
    # Quote-aware: a ";" inside a quoted parameter value does not start a parameter.
    message = EmailMessage()
    message["content-type"] = headers.get("content-type", "")
    return message.get_content_charset() or "utf-8"


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

    Only successful HTML and Markdown responses are buffered, up to max_html_bytes.
    Other responses, and bodies over that limit, are streamed through unconverted
    and uncached.

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
                if text is not None:
                    self.store.put(key, text)
                await send(start)
                await send({"type": "http.response.body", "body": body})
                return
            converted = markdownify(text, heading_style="ATX")
            self.store.put(key, converted)
            await self._send_markdown(
                send, converted, status=start["status"], raw_headers=start["headers"]
            )

        await self.app(scope, receive, capture)

    @staticmethod
    async def _send_markdown(
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
        headers["content-type"] = "text/markdown; charset=utf-8"
        headers["content-length"] = str(len(body))
        vary = [item.strip() for value in headers.getlist("vary") for item in value.split(",")]
        if "*" in vary:
            headers["vary"] = "*"
        else:
            if "accept" not in {item.lower() for item in vary}:
                vary.append("Accept")
            headers["vary"] = ", ".join(item for item in vary if item)
        await send(message)
        await send({"type": "http.response.body", "body": body})


def add_md4a(
    app: FastAPI,
    *,
    store: Store | None = None,
    provider: MarkdownProvider | None = None,
    convert_html: bool = True,
    max_html_bytes: int = 5_000_000,
) -> None:
    """Add Markdown-for-Agents negotiation to an existing FastAPI app."""
    app.add_middleware(
        MarkdownForAgentsMiddleware,
        store=store,
        provider=provider,
        convert_html=convert_html,
        max_html_bytes=max_html_bytes,
    )
