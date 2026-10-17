"""Negotiation rules shared by the ASGI and WSGI middleware.

Nothing here imports a web framework, so either middleware can use it alone.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from email.message import Message as EmailMessage
from typing import Any

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

# A tag name no page uses; markdownify calls convert_<name> for it.
_LITERAL_TAG = "md4aliteral"

# These describe the original HTML bytes and cannot be reused after conversion.
HTML_REPRESENTATION_HEADERS = frozenset(
    {
        "content-encoding",
        "content-location",
        "content-range",
        "accept-ranges",
        "etag",
        "last-modified",
        "content-md5",
        "digest",
        "content-digest",
        "repr-digest",
        "transfer-encoding",
        "trailer",
    }
)

MARKDOWN_CONTENT_TYPE = "text/markdown; charset=utf-8"


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


def declared_charset(content_type: str) -> str:
    """Charset named in a Content-Type value, or utf-8 when it names none."""
    # Quote-aware: a ";" inside a quoted parameter value does not start a parameter.
    message = EmailMessage()
    message["content-type"] = content_type
    return message.get_content_charset() or "utf-8"


def vary_with_accept(values: list[str]) -> str:
    """Merge the response's Vary field values and make sure Accept is among them."""
    vary = [item.strip() for value in values for item in value.split(",")]
    if "*" in vary:
        return "*"
    if "accept" not in {item.lower() for item in vary}:
        vary.append("Accept")
    return ", ".join(item for item in vary if item)


def _code_span(text: str) -> str:
    """Text as an inline code span that no Markdown in it can escape from."""
    text = " ".join(text.split())
    if not text:
        return ""
    # A fence longer than any backtick run in the text, padded with a space on
    # each side so text that starts or ends with a backtick cannot join it.
    fence = "`" * (max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    return f"{fence} {text} {fence}"


class _Converter(MarkdownConverter):
    def convert_md4aliteral(self, el: Any, text: str, *args: Any, **kwargs: Any) -> str:
        return _code_span(el.get_text())


def html_to_markdown(
    html: str,
    *,
    content_selector: str | None = None,
    strip_selectors: Sequence[str] = (),
    escape_misc: bool = False,
    literal_selectors: Sequence[str] = (),
) -> str:
    """Convert an HTML document to Markdown, optionally only part of it.

    ``strip_selectors`` are CSS selectors whose elements are removed first.
    ``content_selector`` is a CSS selector; its first match is what gets
    converted. A page it does not match is converted whole, so a template
    without that element still yields Markdown rather than nothing.

    ``escape_misc`` escapes Markdown punctuation in page text (``[``, ``]``,
    ``#``, ``>`` and the like) so it reads as text, not as links or headings.
    ``literal_selectors`` are CSS selectors whose elements' text is emitted as
    an inline code span: shown as written, with nothing in it rendered as a
    link, image, or autolink. Use it for untrusted text such as user comments.
    """
    converter = _Converter(heading_style="ATX", escape_misc=escape_misc)
    if content_selector is None and not strip_selectors and not literal_selectors:
        return converter.convert(html)
    soup = BeautifulSoup(html, "html.parser")
    for selector in strip_selectors:
        for element in soup.select(selector):
            element.decompose()
    for selector in literal_selectors:
        for element in soup.select(selector):
            literal = soup.new_tag(_LITERAL_TAG)
            literal.string = element.get_text()
            element.clear()
            element.append(literal)
    content = soup.select_one(content_selector) if content_selector else None
    return converter.convert(str(content if content is not None else soup))
