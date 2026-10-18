# md4a-fastapi

[![CI](https://github.com/adamtasteslikegood/md4a-fastapi/actions/workflows/ci.yml/badge.svg)](https://github.com/adamtasteslikegood/md4a-fastapi/actions/workflows/ci.yml)
[![CodeQL](https://github.com/adamtasteslikegood/md4a-fastapi/actions/workflows/codeql.yml/badge.svg)](https://github.com/adamtasteslikegood/md4a-fastapi/actions/workflows/codeql.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

`md4a-fastapi` adds Markdown for Agents content negotiation to FastAPI applications.
When an agent sends `Accept: text/markdown`, an existing HTML route can return a
compact Markdown representation while normal browser requests remain unchanged.

The package also includes a client and standalone service for discovering whether
remote pages natively serve Markdown, then buffering or storing verified Markdown
responses.

> Status: early alpha. APIs may change before the first stable release.

## Features

- ASGI middleware designed for FastAPI
- WSGI middleware for Flask and other WSGI applications
- `Accept: text/markdown` negotiation for GET requests
- HTML-to-Markdown conversion with transparent pass-through for other media types
- Synchronous provider hook for hand-authored Markdown
- In-memory and filesystem-backed content stores
- Remote Markdown discovery with redirect, host allowlist, timeout, and size controls
- Standalone FastAPI service and `md4a` command-line interface

## Installation

```bash
python -m pip install md4a-fastapi             # FastAPI and Flask middleware
python -m pip install 'md4a-fastapi[server]'   # adds the md4a command, client, and service
```

With uv, use `uv add md4a-fastapi` or `uv pip install md4a-fastapi` the same way.
`pip install md4a` is the same install under a shorter name: the `md4a`
distribution depends on `md4a-fastapi` at the same version and adds no code.

| Install | What you get | Extra dependencies |
| --- | --- | --- |
| `md4a-fastapi` | ASGI and WSGI middleware, content stores | `beautifulsoup4`, `markdownify`, `fastapi` |
| `md4a-fastapi[server]` | also the remote client, standalone service, `md4a` command | `httpx`, `anyio`, `uvicorn[standard]` |
| `md4a-fastapi[flask]` | the same as the base install | none |

The WSGI middleware needs nothing beyond the base install and never imports
FastAPI, so a Flask application can use the base install as it is. `[flask]` and
`[wsgi]` are accepted as names for it. Without the server extra, importing
`md4a.client` or running `md4a` says which package to install.

### Development setup

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
git clone https://github.com/adamtasteslikegood/md4a-fastapi.git
cd md4a-fastapi
uv sync --extra test
```

This creates or updates the project virtual environment in `.venv`, installs
the package in editable mode, and installs the test tools. No activation is
needed when using the `uv run` commands below. If you prefer to activate the
environment, use `source .venv/bin/activate` on macOS/Linux or
`.venv\Scripts\Activate.ps1` in Windows PowerShell, then run the commands
without the `uv run` prefix.

Using Python's built-in venv and pip:

```bash
git clone https://github.com/adamtasteslikegood/md4a-fastapi.git
cd md4a-fastapi
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

## FastAPI middleware

```python
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from md4a import FileStore, add_md4a

app = FastAPI()
add_md4a(app, store=FileStore(".md4a-cache"))


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return "<h1>Hello agents</h1><p>This remains HTML for browsers.</p>"
```

Request either representation from the same URL:

```bash
curl http://localhost:8000/
curl -H 'Accept: text/markdown' http://localhost:8000/
```

For hand-authored Markdown, provide a callable that returns Markdown or `None`:

```python
pages = {"/": "# Hello agents\n"}
add_md4a(app, provider=lambda key: pages.get(key), convert_html=False)
```

Provider and cached content take precedence. Otherwise, when `convert_html=True`,
the middleware executes the normal route, converts a successful HTML response,
caches it by path and query string, and responds as `text/markdown`. JSON and other
response types pass through unchanged.

Converted responses retain application headers, including security headers, CORS,
and repeated `Set-Cookie` fields. md4a recalculates the content type and length,
merges `Accept` into `Vary`, and removes HTML-specific validators, digests, and
range metadata. Compressed, partial, and trailer-bearing responses pass through
unchanged.

Only successful HTML and Markdown responses are buffered, up to `max_html_bytes`
(5 MB by default; pass `max_html_bytes=` to `add_md4a`). Everything else, including
streaming responses and bodies over the limit, is forwarded as it arrives and is
neither converted nor cached. Bodies are decoded with the charset declared in
`Content-Type` (UTF-8 when absent); a response that cannot be decoded is returned
unchanged and is not cached.

For headers that must be present on **every** response, register your security/CORS
middleware **after** `add_md4a(app)` so it wraps md4a. Cache hits and provider
responses skip the wrapped application; stores hold Markdown text only, not
response headers. Use caching for public, non-personalized content, and keep
authentication outside md4a: route-level authentication does not run on these
shortcuts. See [middleware ordering](QUICKSTART.md#middleware-ordering-and-response-headers).

### Converting only the content

By default the whole HTML document is converted, navigation and footer included.
`content_selector` is a CSS selector; only its first match is converted.
`strip_selectors` are CSS selectors whose elements are removed first:

```python
add_md4a(app, content_selector="main", strip_selectors=[".related", "form"])
```

A page the content selector does not match is converted whole. Provider, cached,
and application-authored Markdown are not affected.

### Escaping untrusted text

Text on a page can contain Markdown syntax that an agent would read as a link or
image, for example a user comment such as `[Free coupons](https://evil.example)`.
Two options keep such text inert. Both are off by default.

```python
add_md4a(app, escape_misc=True, literal_selectors=['[data-md="plain"]'])
```

- `escape_misc=True` escapes Markdown punctuation (`[`, `]`, `#`, `>`, and the
  like) in all page text, so it cannot form links, images, or headings. Some
  text gains backslashes, which Markdown readers drop.
- `literal_selectors` are CSS selectors for elements whose text is emitted as an
  inline code span. Escaping does not stop bare URLs and email addresses from
  being linked, but nothing inside a code span is, so use this for user-written
  text. Whitespace is collapsed to single spaces and nested markup is kept as text.
  A matched link, image, or code element is replaced by the span, so its own
  syntax cannot wrap the text; in a table cell, pipes are escaped.

Use the two together: without `escape_misc`, a stray backtick in the page's own
text can open a code span that runs into the literal one. Both options work the
same in the WSGI middleware.

## Flask and other WSGI applications

`MarkdownForAgentsWSGIMiddleware` applies the same negotiation to a WSGI
application. It takes the same options as `add_md4a`:

```python
from flask import Flask

from md4a import FileStore, MarkdownForAgentsWSGIMiddleware

app = Flask(__name__)
app.wsgi_app = MarkdownForAgentsWSGIMiddleware(app.wsgi_app, store=FileStore(".md4a-cache"))


@app.get("/")
def home() -> str:
    return "<h1>Hello agents</h1><p>This remains HTML for browsers.</p>"
```

The rules above apply unchanged: provider and cached content take precedence,
only successful HTML and Markdown `GET` responses up to `max_html_bytes` are
buffered, application headers are kept, and compressed, partial, and oversized
responses pass through. The cache key is the percent-encoded `SCRIPT_NAME` plus
`PATH_INFO`, followed by `?` and the query string when there is one.

A response the application sends through the legacy `write()` callable passes
through unconverted. Importing `md4a.wsgi`, or `MarkdownForAgentsWSGIMiddleware`
from `md4a`, does not import FastAPI or Starlette, although the base install
still includes them.

Use WSGI conversion for ordinary buffered page responses, not streaming HTML
iterables. The middleware must see the complete eligible body before it can choose
converted headers or an unchanged size/decoding fallback, so that conversion path
cannot preserve PEP 3333 asynchronous block-boundary scheduling. Responses whose
initial status and headers establish pass-through return the application's original
iterable, including `wsgi.file_wrapper` objects used for optimized file transfer.

As with ASGI, cache and provider hits return before the wrapped application runs,
so wrap only public, non-personalized pages and keep authentication outside md4a.

## Cache lifetime

Cached Markdown is served until the store drops it, and by default a store never
does: a converted page stays as it was first rendered. Give the store a lifetime,
bound it, or stop caching responses:

```python
from md4a import FileStore, MemoryStore, add_md4a

add_md4a(app, store=MemoryStore(ttl=300, max_entries=1000))  # 5 minutes, 1000 pages
add_md4a(app, store=FileStore(".md4a-cache", ttl=3600))  # 1 hour, on disk
add_md4a(app, cache_responses=False)  # convert every request
```

- `ttl` is in seconds. An entry that old is treated as missing, so the route runs
  again and the fresh result is stored.
- `max_entries` (`MemoryStore` only) drops expired entries, then the oldest stored,
  when the limit is reached. The cache key includes the query string, so set it
  when callers control the query.
- `store.delete(key)` and `store.clear()` remove entries by hand, for example after
  publishing a change.
- `cache_responses=False` stops md4a writing responses to the store. Content already
  in the store, and provider content, is still served.

## Caching and CDNs

A URL that md4a negotiates has two representations, HTML and Markdown, so a
shared cache must key both on the `Accept` request header. md4a adds `Accept` to
`Vary` on every `GET` and `HEAD` response whose media type is `text/html` or
`text/markdown`: converted Markdown, and the HTML the application sends to
browsers. It merges with the application's own `Vary` and leaves `Vary: *` alone.
Other responses are untouched. Pass `vary_html=False` to stop it adding `Vary`
to responses it does not convert.

md4a sets no `Cache-Control`; converted responses keep the application's caching
headers, minus validators such as `ETag` that described the HTML bytes.

### Cloudflare

By default Cloudflare ignores `Vary` when it caches. That is safe while HTML is
not cached, which is Cloudflare's default. If a "Cache Everything" or other Cache
Rule makes negotiated pages cacheable, whichever representation is cached first
is served to everyone. Choose one of these:

1. **Keep negotiated pages out of the cache.** Exclude their paths from any rule
   that makes HTML eligible for cache.
2. **Bypass the cache for Markdown requests.** Add a Cache Rule with the custom
   filter expression below and **Cache eligibility: Bypass cache**, placed after
   any rule that makes those pages eligible. Browsers keep getting cached HTML;
   agents always reach the origin.

   ```text
   any(http.request.headers["accept"][*] contains "text/markdown")
   ```

3. **Cache both representations.** In a Cache Rule for those pages, set
   **Vary** for `accept` to `normalize`, with media types `text/html` and
   `text/markdown`. Cloudflare then stores one version per normalized `Accept` value
   and forwards the normalized `Accept` to the origin. This needs `Vary: Accept` on
   both representations, which md4a sends unless `vary_html=False`.

Cache Rules, including Bypass and the Vary setting, are available on every plan.
See Cloudflare's [Vary](https://developers.cloudflare.com/cache/concepts/vary/) and
[Cache Rules settings](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/)
documentation.

For other CDNs and reverse proxies, make sure they honor `Vary: Accept` or add
`Accept` to the cache key for these pages.

## Remote discovery and standalone service

These need the server extra: `python -m pip install 'md4a-fastapi[server]'`.

With the uv-managed project environment, run the CLI with `uv run`:

```bash
# Show all commands
uv run md4a -h

# Verify that the origin returns text/markdown, then save it
uv run md4a fetch https://blog.cloudflare.com/the-agentic-internet/ -o article.md

# Start the standalone API
uv run md4a serve --host 127.0.0.1 --port 8000
```

After installing with pip, use the same commands without the `uv run` prefix:

```bash
# Show all commands
md4a -h

# Verify that the origin returns text/markdown, then save it
md4a fetch https://blog.cloudflare.com/the-agentic-internet/ -o article.md

# Start the standalone API
md4a serve --host 127.0.0.1 --port 8000
curl -H 'Accept: text/markdown' \
  'http://127.0.0.1:8000/fetch?url=https%3A%2F%2Fblog.cloudflare.com%2Fthe-agentic-internet%2F'
```

The uv and pip commands above start the same standalone FastAPI service. Keep
the server running in one terminal and use the `curl` request from another.

The remote client sends `Accept: text/markdown` and only considers the page
available when the origin confirms `Content-Type: text/markdown`. Redirects are
validated before following them, and responses are capped at 5 MB by default.

Standalone configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MD4A_CACHE_DIR` | `.md4a-cache` | Directory for fetched Markdown and its index |
| `MD4A_ALLOWED_HOSTS` | unrestricted | Comma-separated hostname allowlist |
| `MD4A_ALLOW_PRIVATE_ADDRESSES` | off | Set to `1`, `true`, or `yes` to permit non-public destinations |

The client refuses destinations that are, or resolve to, loopback, private,
link-local, or other non-public addresses, on the first request and on every
redirect, and connects to the address it checked. This applies to allowlisted hosts
too. Behind an environment proxy the proxy resolves names, so only literal addresses
and hosts that bypass the proxy are checked; see [SECURITY.md](SECURITY.md). For local development, pass `allow_private_addresses=True` to
`MarkdownForAgentsClient`, `--allow-private-addresses` to `md4a fetch`, or set
`MD4A_ALLOW_PRIVATE_ADDRESSES` for the service.

Always set `MD4A_ALLOWED_HOSTS` before exposing the standalone fetch service to
untrusted users. An unrestricted URL-fetching endpoint can create an SSRF risk.

## Documentation

- [Quick start](QUICKSTART.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## Project scope

`md4a-fastapi` focuses on FastAPI/ASGI integration, a WSGI middleware with the same
behavior, and verified Markdown retrieval.
It does not attempt to reproduce a browser, execute JavaScript, or claim that
converted Markdown is identical to a publisher-authored agent representation.

## License

Licensed under the [MIT License](LICENSE).
