# md4a

`md4a` discovers, stores, and serves Markdown-for-Agents content using HTTP
content negotiation (`Accept: text/markdown`). It can run as a standalone
FastAPI service or extend an existing FastAPI application.

## Install and run

```bash
python -m venv .venv
.venv/bin/pip install -e '.[test]'

# `-h` shows CLI help
.venv/bin/md4a -h

# Probe a page and write the verified Markdown response to a file
.venv/bin/md4a fetch https://blog.cloudflare.com/the-agentic-internet/ \
  -o the-agentic-internet.md

# Standalone service
.venv/bin/md4a serve --host 0.0.0.0 --port 8000
curl -H 'Accept: text/markdown' \
  'http://localhost:8000/fetch?url=https%3A%2F%2Fblog.cloudflare.com%2Fthe-agentic-internet%2F'
```

The standalone service follows redirects, sends `Accept: text/markdown`, and
only stores/returns the body when the origin confirms `Content-Type:
text/markdown`. Set `MD4A_CACHE_DIR` to choose the file cache. In exposed
deployments, set `MD4A_ALLOWED_HOSTS=example.com,docs.example.com` to prevent
the fetch endpoint from becoming an unrestricted proxy.

## Add to FastAPI

```python
from fastapi import FastAPI
from md4a import FileStore, add_md4a

app = FastAPI()
add_md4a(app, store=FileStore(".md4a-cache"))

@app.get("/")
def home():
    return HTMLResponse("<h1>Hello agents</h1>")
```

Now the existing HTML route negotiates its representation:

```bash
curl http://localhost:8000/                     # original response
curl -H 'Accept: text/markdown' http://localhost:8000/  # Markdown
```

For hand-authored Markdown, pass a synchronous provider. It receives the path
and query string and returns Markdown or `None`:

```python
add_md4a(app, provider=lambda key: pages.get(key), convert_html=False)
```

The middleware serves provider/cached content first. If none exists and
`convert_html=True`, it executes the normal route, converts an HTML response,
stores it, and returns it as `text/markdown`. JSON and other response types are
left unchanged.
