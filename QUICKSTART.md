# Quick start

This guide gets the middleware or standalone service running locally.

## Requirements

- Python 3.11 or newer
- Git
- Either [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Set up a development environment

Using uv (recommended):

```bash
git clone https://github.com/adamtasteslikegood/md4a-fastapi.git
cd md4a-fastapi
uv sync --extra test
```

This creates or updates `.venv`, installs the package in editable mode, and
installs the test tools. No activation is needed when using `uv run`. If you
prefer to activate the environment, use `source .venv/bin/activate` on
macOS/Linux or `.venv\Scripts\Activate.ps1` in Windows PowerShell, then run
commands without the `uv run` prefix.

Using Python's built-in venv and pip:

```bash
git clone https://github.com/adamtasteslikegood/md4a-fastapi.git
cd md4a-fastapi
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

Confirm the installation:

```bash
uv run md4a -h
uv run pytest -q
```

If you installed with pip, run the same checks directly:

```bash
md4a -h
pytest -q
```

## Add Markdown negotiation to FastAPI

Create `example.py`:

```python
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from md4a import add_md4a

app = FastAPI()
add_md4a(app)


@app.get("/hello", response_class=HTMLResponse)
def hello() -> str:
    return "<main><h1>Hello</h1><p>Readable by people and agents.</p></main>"
```

Run it:

```bash
uv run uvicorn example:app --reload
```

With a pip installation, use:

```bash
uvicorn example:app --reload
```

Compare responses:

```bash
curl -i http://127.0.0.1:8000/hello
curl -i -H 'Accept: text/markdown' http://127.0.0.1:8000/hello
```

The second response has `Content-Type: text/markdown; charset=utf-8` and
`Vary: Accept`.

## Serve hand-authored Markdown

Use a provider when conversion is not the desired source of truth:

```python
from md4a import FileStore, add_md4a

markdown_pages = {
    "/hello": "# Hello\n\nReadable by people and agents.\n",
}

add_md4a(
    app,
    store=FileStore(".md4a-cache"),
    provider=lambda key: markdown_pages.get(key),
    convert_html=False,
)
```

The provider key includes the request path and, when present, its query string.

## Probe a remote page

Print verified Markdown to standard output:

```bash
uv run md4a fetch https://blog.cloudflare.com/the-agentic-internet/
```

Write it to a file:

```bash
uv run md4a fetch https://blog.cloudflare.com/the-agentic-internet/ -o article.md
```

With a pip installation, omit the `uv run` prefix from these commands.

The command exits with status `2` when the page responds successfully but does
not advertise `text/markdown`.

## Run the standalone API

Restrict outbound requests to known hosts before exposing the service:

```bash
export MD4A_ALLOWED_HOSTS=blog.cloudflare.com,developers.cloudflare.com
export MD4A_CACHE_DIR=.md4a-cache
uv run md4a serve --host 127.0.0.1 --port 8000
```

With a pip installation, run `md4a serve --host 127.0.0.1 --port 8000` instead.

Then fetch through the API:

```bash
curl -H 'Accept: text/markdown' \
  'http://127.0.0.1:8000/fetch?url=https%3A%2F%2Fblog.cloudflare.com%2Fthe-agentic-internet%2F'
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Next steps

- Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes.
- Review [SECURITY.md](SECURITY.md) before deploying the fetch service publicly.
- Use `FileStore` when content must survive process restarts.
