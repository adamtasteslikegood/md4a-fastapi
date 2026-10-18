# Changelog

All notable changes to `md4a-fastapi` are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Until 1.0, minor versions may change
the API.

## [Unreleased]

### Changed

- Both middlewares add `Accept` to `Vary` on every `GET`/`HEAD` response whose media
  type is `text/html` or `text/markdown`, including the HTML sent to browsers, so
  shared caches keep the two representations apart. `vary_html=False` turns this
  off for responses md4a does not convert. (#46)

### Added

- `frontmatter`, `json_ld`, and `content_signal` options on both middlewares and
  `add_md4a` (all off by default), following Cloudflare's Markdown for Agents output:
  YAML frontmatter from `title`/`description`/`image` meta tags, JSON-LD scripts as
  fenced `json` blocks at the end, and a `Content-Signal` header on Markdown responses
  unless the application set its own. (#47)
- README "Caching and CDNs": why both representations need `Vary: Accept`, and three
  Cloudflare setups (no HTML caching, bypass for Markdown requests, or the Cache
  Rules Vary setting). (#46)
- The `md4a` distribution on PyPI: `pip install md4a` installs `md4a-fastapi` at the
  same version (extras included) and adds no code. Both are released together.

## [0.1.0] - 2026-10-17

First release.

### Added

- `MarkdownForAgentsMiddleware` and `add_md4a` for FastAPI and other ASGI apps:
  a `GET` request that accepts `text/markdown` gets a successful HTML response
  converted to Markdown, cached by path and query string; everything else passes
  through unchanged.
- `MarkdownForAgentsWSGIMiddleware` for Flask and other WSGI apps, with the same
  options and rules. Importing it does not import FastAPI, Starlette, or httpx.
- A synchronous `provider` hook for hand-written Markdown, served ahead of conversion.
- `MemoryStore` and `FileStore`, with `ttl`, `delete`, and `clear`, and
  `max_entries` for `MemoryStore`. `cache_responses=False` stops writing
  responses to the store.
- `content_selector` and `strip_selectors` to convert only the page content.
- `escape_misc` and `literal_selectors` (both off by default) to keep untrusted
  text, such as user comments, from becoming links or images in the Markdown.
- `MarkdownForAgentsClient` for remote discovery: sends `Accept: text/markdown`,
  accepts only `text/markdown` responses, and checks schemes, redirects, host
  allowlists, timeouts, response size, and non-public destination addresses.
- A standalone FastAPI service (`/health`, `/fetch`) and the `md4a fetch` and
  `md4a serve` commands.

### Behavior

- Converted responses keep application headers, including repeated `Set-Cookie`;
  md4a recalculates the content type and length, merges `Accept` into `Vary`, and
  drops validators, digests, and range metadata that described the HTML bytes.
- Only successful HTML and Markdown bodies are buffered, up to `max_html_bytes`
  (5 MB by default). Other media types and compressed, partial, oversized, and
  (ASGI) trailer-bearing responses pass through unconverted and uncached. A
  streamed HTML or Markdown body is held until it ends or reaches the limit, so
  conversion does not preserve chunk timing.
- Bodies are decoded with the charset declared in `Content-Type`; a response that
  cannot be decoded is returned unchanged and is not cached.

### Packaging

- The base install (`beautifulsoup4`, `markdownify`, `fastapi`) covers both
  middlewares and the stores. The `server` extra adds `httpx`, `anyio`, and
  `uvicorn[standard]` for the client, the service, and the `md4a` command, which
  say how to install it when it is missing. `flask` and `wsgi` are names for the
  base install.
- Python 3.11 to 3.14. Typed (`py.typed`).

[Unreleased]: https://github.com/adamtasteslikegood/md4a-fastapi/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/adamtasteslikegood/md4a-fastapi/releases/tag/v0.1.0
