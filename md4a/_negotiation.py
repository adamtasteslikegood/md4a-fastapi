"""Negotiation rules shared by the ASGI and WSGI middleware.

Nothing here imports a web framework, so either middleware can use it alone.
"""

from __future__ import annotations

import json
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


def checked_content_signal(value: str | None) -> str | None:
    """A Content-Signal header value, refused if it could split the header."""
    if value is not None and any(char in value for char in "\r\n\0"):
        raise ValueError("content_signal must be a single header line")
    return value


# Media types md4a negotiates between: a response of either type is one
# representation of a URL that has another, so caches must key it on Accept.
NEGOTIATED_MEDIA_TYPES = frozenset({"text/html", "text/markdown"})


def media_type(content_type: str) -> str:
    """The media type of a Content-Type value, lowercased, without parameters."""
    return content_type.partition(";")[0].strip().lower()


def vary_with_accept(values: list[str]) -> str:
    """Merge the response's Vary field values and make sure Accept is among them."""
    vary = [item.strip() for value in values for item in value.split(",")]
    if "*" in vary:
        return "*"
    if "accept" not in {item.lower() for item in vary}:
        vary.append("Accept")
    return ", ".join(item for item in vary if item)


# Matched elements whose Markdown only adds block structure around their content
# keep their tag; any other match (a link, an image, inline formatting, code) is
# replaced, so its own Markdown syntax cannot wrap the literal text.
_LITERAL_CONTAINERS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "caption",
        "dd",
        "div",
        "dt",
        "figcaption",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "p",
        "section",
        "td",
        "th",
    }
)


def _code_span(text: str, *, in_table: bool = False) -> str:
    """Text as an inline code span that no Markdown in it can escape from."""
    text = " ".join(text.split())
    if not text:
        return ""
    if in_table:
        # Table rows are split into cells before code spans are parsed, so a
        # pipe must be escaped even inside one; GFM shows "\|" there as "|".
        text = text.replace("|", "\\|")
    # A fence longer than any backtick run in the text, padded with a space on
    # each side so text that starts or ends with a backtick cannot join it.
    fence = "`" * (max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    # The spaces outside the fences keep them from joining a backtick next to
    # the span, including the fence of an adjacent literal span.
    return f" {fence} {text} {fence} "


class _Converter(MarkdownConverter):
    def convert_md4aliteral(self, el: Any, text: str, *args: Any, **kwargs: Any) -> str:
        return _code_span(el.get_text(), in_table=el.find_parent(["td", "th"]) is not None)


def _meta_content(soup: BeautifulSoup, attribute: str, value: str) -> str | None:
    """The first non-empty content of a meta tag whose attribute matches, ignoring case."""
    for tag in soup.find_all("meta"):
        if str(tag.get(attribute, "")).strip().lower() == value:
            content = " ".join(str(tag.get("content", "")).split())
            if content:
                return content
    return None


def _frontmatter(soup: BeautifulSoup) -> str:
    """YAML frontmatter from the page's meta tags, as Cloudflare's Markdown for Agents emits.

    Standard meta tags win over Open Graph ones whatever their order. Values are
    written as JSON strings, which YAML reads as double-quoted scalars, so page
    text cannot add keys or break out of the block.
    """
    fields = {
        "title": _meta_content(soup, "name", "title")
        or _meta_content(soup, "property", "og:title"),
        "description": _meta_content(soup, "name", "description")
        or _meta_content(soup, "property", "og:description"),
        "image": _meta_content(soup, "property", "og:image"),
    }
    lines = [
        f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in fields.items() if value
    ]
    return "---\n" + "\n".join(lines) + "\n---" if lines else ""


def _reject_constant(name: str) -> None:
    raise ValueError(f"{name} is not valid JSON")


def _json_ld_blocks(soup: BeautifulSoup) -> list[str]:
    """Each valid JSON-LD script in the page as a fenced json block."""
    blocks = []
    for script in soup.find_all("script"):
        if str(script.get("type", "")).partition(";")[0].strip().lower() != "application/ld+json":
            continue
        try:
            data = json.loads(script.get_text(), parse_constant=_reject_constant)
            text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)
            try:
                text.encode("utf-8")
            except UnicodeEncodeError:
                # An escaped lone surrogate parses to a character UTF-8 cannot
                # carry; keep this block's non-ASCII characters escaped instead.
                text = json.dumps(data, indent=2, allow_nan=False)
        except (ValueError, RecursionError):
            # Not valid JSON (including NaN and Infinity) or nested too deeply:
            # leave it out rather than pass on a broken block or fail the page.
            continue
        fence = "`" * max(3, max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
        blocks.append(f"{fence}json\n{text}\n{fence}")
    return blocks


def html_to_markdown(
    html: str,
    *,
    content_selector: str | None = None,
    strip_selectors: Sequence[str] = (),
    escape_misc: bool = False,
    literal_selectors: Sequence[str] = (),
    frontmatter: bool = False,
    json_ld: bool = False,
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
    link, image, or autolink. Use it for untrusted text such as user comments,
    together with ``escape_misc`` so a stray backtick in the page's own text
    cannot open a code span that runs into the literal one.

    ``frontmatter`` prepends YAML frontmatter (``title``, ``description``,
    ``image``) from the page's meta tags, and ``json_ld`` appends each JSON-LD
    script as a fenced ``json`` block, in the layout of Cloudflare's Markdown for
    Agents. Both read the whole document, whatever the selectors keep.
    """
    body = _convert_body(
        html,
        content_selector=content_selector,
        strip_selectors=strip_selectors,
        escape_misc=escape_misc,
        literal_selectors=literal_selectors,
    )
    if not frontmatter and not json_ld:
        return body
    document = BeautifulSoup(html, "html.parser")
    head = _frontmatter(document) if frontmatter else ""
    tail = _json_ld_blocks(document) if json_ld else []
    if not head and not tail:
        return body
    return "\n\n".join(part for part in [head, body.strip("\n"), *tail] if part) + "\n"


def _convert_body(
    html: str,
    *,
    content_selector: str | None,
    strip_selectors: Sequence[str],
    escape_misc: bool,
    literal_selectors: Sequence[str],
) -> str:
    converter = _Converter(heading_style="ATX", escape_misc=escape_misc)
    if content_selector is None and not strip_selectors and not literal_selectors:
        return converter.convert(html)
    soup = BeautifulSoup(html, "html.parser")
    for selector in strip_selectors:
        for element in soup.select(selector):
            element.decompose()
    for selector in literal_selectors:
        for element in soup.select(selector):
            if element.parent is None:
                continue  # inside an element already made literal
            literal = soup.new_tag(_LITERAL_TAG)
            literal.string = element.get_text()
            if element.name in _LITERAL_CONTAINERS:
                element.clear()
                element.append(literal)
            else:
                element.replace_with(literal)
    content = soup.select_one(content_selector) if content_selector else None
    return converter.convert(str(content if content is not None else soup))
