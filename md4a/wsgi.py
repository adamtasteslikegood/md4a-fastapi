"""Markdown-for-Agents negotiation for WSGI applications (Flask, Django, ...)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Any
from urllib.parse import quote

from ._negotiation import (
    HTML_REPRESENTATION_HEADERS,
    MARKDOWN_CONTENT_TYPE,
    accepts_markdown,
    declared_charset,
    html_to_markdown,
    vary_with_accept,
)
from .store import MemoryStore, Store

MarkdownProvider = Callable[[str], str | None]

Environ = dict[str, Any]
HeaderList = list[tuple[str, str]]
StartResponse = Callable[..., Callable[[bytes], object]]
WSGIApp = Callable[[Environ, StartResponse], Iterable[bytes]]


def _values(headers: HeaderList, name: str) -> list[str]:
    return [value for field, value in headers if field.lower() == name]


def _declared_length(headers: HeaderList) -> int:
    try:
        return int(next(iter(_values(headers, "content-length")), "0"))
    except ValueError:
        return 0


def _request_key(environ: Environ) -> str:
    # WSGI decodes the path as latin-1; quoting it the same way gives back a
    # percent-encoded path like the one the ASGI key uses. The server's decoding
    # loses which characters the client escaped, so the characters RFC 3986
    # allows unescaped in a path segment are left as they are.
    path = quote(
        environ.get("SCRIPT_NAME", "") + environ.get("PATH_INFO", ""),
        safe="/:@!$&'()*+,;=",
        encoding="latin-1",
    )
    query = environ.get("QUERY_STRING", "")
    return f"{path}?{query}" if query else path


class _Exchange:
    """One request's response, held back until it is known to be convertible."""

    def __init__(self, start_response: StartResponse) -> None:
        self.start_response = start_response
        self.status: str | None = None
        self.headers: HeaderList = []
        self.media_type = ""
        self.passthrough = False
        self.parts: list[bytes] = []
        self.buffered = 0
        self.write: Callable[[bytes], object] | None = None

    def release(self) -> bytes:
        """Give up on conversion: start the real response and return what was held."""
        assert self.status is not None
        self.passthrough = True
        self.write = self.start_response(self.status, self.headers)
        held = b"".join(self.parts)
        self.parts.clear()
        return held


class _ClosingIterator:
    """Forward close even when the negotiated iterator was never started."""

    def __init__(self, iterator: Iterator[bytes], close_result: Callable[[], None]) -> None:
        self.iterator = iterator
        self.close_result = close_result
        self.closed = False

    def __iter__(self) -> _ClosingIterator:
        return self

    def __next__(self) -> bytes:
        return next(self.iterator)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.iterator.close()
        finally:
            self.close_result()


class MarkdownForAgentsWSGIMiddleware:
    """Serve Markdown when a GET request explicitly accepts text/markdown.

    The WSGI counterpart of ``MarkdownForAgentsMiddleware``, with the same rules:
    cached/provider content wins; otherwise the wrapped application runs and a
    successful HTML response is converted, cached by path and query string, and
    returned as Markdown. Non-GET and non-Markdown requests pass through unchanged.

    Only successful HTML and Markdown responses are buffered, up to max_html_bytes.
    Other responses, bodies over that limit, and applications that use the legacy
    ``write()`` callable are passed through unconverted and uncached.

    Stores contain only content: security/auth middleware must wrap this middleware
    to run on cache hits and provider responses as well as converted responses.

    Flask::

        app.wsgi_app = MarkdownForAgentsWSGIMiddleware(app.wsgi_app)
    """

    def __init__(
        self,
        app: WSGIApp,
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

    def __call__(self, environ: Environ, start_response: StartResponse) -> Iterable[bytes]:
        if environ.get("REQUEST_METHOD") != "GET" or not accepts_markdown(
            environ.get("HTTP_ACCEPT", "")
        ):
            return self.app(environ, start_response)

        key = _request_key(environ)
        content = self.store.get(key)
        if content is None and self.provider is not None:
            content = self.provider(key)
        if content is not None:
            return [self._start_markdown(start_response, content, "200 OK", [])]
        return self._negotiate(environ, start_response, key)

    def _negotiate(
        self, environ: Environ, start_response: StartResponse, key: str
    ) -> Iterable[bytes]:
        exchange = _Exchange(start_response)

        def held_write(data: bytes) -> None:
            # The legacy write() callable streams past the returned iterable, so
            # the body cannot be held for conversion.
            if not exchange.passthrough:
                data = exchange.release() + data
            assert exchange.write is not None
            exchange.write(data)

        def capture(
            status: str, headers: HeaderList, exc_info: Any = None
        ) -> Callable[[bytes], object]:
            exchange.status = status
            exchange.headers = list(headers)
            if exc_info is not None:
                # An error response replacing an earlier one: hand it straight on.
                exchange.passthrough = True
                exchange.write = start_response(status, headers, exc_info)
                return exchange.write
            try:
                code = int(status.split(None, 1)[0])
            except (IndexError, ValueError):
                code = 0
            exchange.media_type = (
                next(iter(_values(exchange.headers, "content-type")), "").partition(";")[0].lower()
            )
            convertible = 200 <= code < 300 and (
                exchange.media_type == "text/markdown"
                or (self.convert_html and exchange.media_type == "text/html")
            )
            # Only hold bodies that may be converted or cached, and never
            # compressed, partial, or oversized content.
            if (
                not convertible
                or any(
                    coding.strip().lower() != "identity"
                    for value in _values(exchange.headers, "content-encoding")
                    for coding in value.split(",")
                )
                or code == 206
                or _values(exchange.headers, "content-range")
                or _declared_length(exchange.headers) > self.max_html_bytes
            ):
                exchange.passthrough = True
                exchange.write = start_response(status, headers)
                return exchange.write
            return held_write

        result = self.app(environ, capture)
        # Preserve server-specific iterables such as wsgi.file_wrapper when the
        # application has already established that no conversion is possible.
        if exchange.passthrough:
            return result

        result_closed = False

        def close_result() -> None:
            nonlocal result_closed
            if result_closed:
                return
            result_closed = True
            close = getattr(result, "close", None)
            if close is not None:
                close()

        def negotiate_result() -> Iterator[bytes]:
            try:
                for chunk in result:
                    if exchange.passthrough or exchange.status is None:
                        yield chunk
                    elif exchange.buffered + len(chunk) > self.max_html_bytes:
                        held = exchange.release()
                        if held:
                            yield held
                        yield chunk
                    else:
                        exchange.buffered += len(chunk)
                        exchange.parts.append(chunk)
            finally:
                close_result()

            if exchange.passthrough or exchange.status is None:
                return
            body = b"".join(exchange.parts)
            try:
                content_type = next(iter(_values(exchange.headers, "content-type")), "")
                text: str | None = body.decode(declared_charset(content_type))
                # Some codecs decode to lone surrogates, which cannot be served or stored.
                text.encode("utf-8")
            except (LookupError, UnicodeError):
                text = None
            if text is None or exchange.media_type == "text/markdown":
                # Undecodable content is returned as the application sent it, uncached.
                if text is not None and self.cache_responses:
                    self.store.put(key, text)
                start_response(exchange.status, exchange.headers)
                yield body
                return
            converted = html_to_markdown(
                text,
                content_selector=self.content_selector,
                strip_selectors=self.strip_selectors,
                escape_misc=self.escape_misc,
                literal_selectors=self.literal_selectors,
            )
            if self.cache_responses:
                self.store.put(key, converted)
            yield self._start_markdown(start_response, converted, exchange.status, exchange.headers)

        return _ClosingIterator(negotiate_result(), close_result)

    @staticmethod
    def _start_markdown(
        start_response: StartResponse, content: str, status: str, headers: HeaderList
    ) -> bytes:
        body = content.encode("utf-8")
        # Keep repeated fields (especially Set-Cookie); drop what described the
        # HTML bytes and the fields recalculated below.
        recalculated = {"content-type", "content-length", "vary"}
        kept = [
            (name, value)
            for name, value in headers
            if name.lower() not in HTML_REPRESENTATION_HEADERS and name.lower() not in recalculated
        ]
        kept += [
            ("Content-Type", MARKDOWN_CONTENT_TYPE),
            ("Content-Length", str(len(body))),
            ("Vary", vary_with_accept(_values(headers, "vary"))),
        ]
        start_response(status, kept)
        return body
