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
- `Accept: text/markdown` negotiation for GET requests
- HTML-to-Markdown conversion with transparent pass-through for other media types
- Synchronous provider hook for hand-authored Markdown
- In-memory and filesystem-backed content stores
- Remote Markdown discovery with redirect, host allowlist, timeout, and size controls
- Standalone FastAPI service and `md4a` command-line interface

## Installation

The package has not been published to PyPI yet. For local development:

```bash
git clone https://github.com/adamtasteslikegood/md4a-fastapi.git
cd md4a-fastapi
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

After the first release:

```bash
python -m pip install md4a-fastapi
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

## Remote discovery and standalone service

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

The remote client sends `Accept: text/markdown` and only considers the page
available when the origin confirms `Content-Type: text/markdown`. Redirects are
validated before following them, and responses are capped at 5 MB by default.

Standalone configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MD4A_CACHE_DIR` | `.md4a-cache` | Directory for fetched Markdown and its index |
| `MD4A_ALLOWED_HOSTS` | unrestricted | Comma-separated hostname allowlist |

Always set `MD4A_ALLOWED_HOSTS` before exposing the standalone fetch service to
untrusted users. An unrestricted URL-fetching endpoint can create an SSRF risk.

## Documentation

- [Quick start](QUICKSTART.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## Project scope

`md4a-fastapi` focuses on FastAPI/ASGI integration and verified Markdown retrieval.
It does not attempt to reproduce a browser, execute JavaScript, or claim that
converted Markdown is identical to a publisher-authored agent representation.

## License

Licensed under the [MIT License](LICENSE).
