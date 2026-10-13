"""Negotiation rules shared by the ASGI and WSGI middleware.

Nothing here imports a web framework, so either middleware can use it alone.
"""

from __future__ import annotations

from email.message import Message as EmailMessage

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
