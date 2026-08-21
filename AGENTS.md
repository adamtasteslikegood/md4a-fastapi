# AGENTS.md

## Project

`md4a-fastapi` is an early-alpha Python package that adds Markdown for Agents
content negotiation to FastAPI/ASGI applications. The PyPI distribution is
`md4a-fastapi`; the Python import package and CLI are both `md4a`.

The supported runtime is Python 3.11 through 3.14. Core behavior lives in:

- `md4a/middleware.py`: inbound `Accept: text/markdown` negotiation and HTML conversion
- `md4a/client.py`: outbound discovery with redirect and response-size controls
- `md4a/store.py`: in-memory and filesystem content stores
- `md4a/app.py`: standalone FastAPI service
- `md4a/cli.py`: `md4a fetch` and `md4a serve`

## Working conventions

- Branch from protected `main`; use `feat/`, `fix/`, `docs/`, or `chore/` branches.
- Do not push directly to `main`. Open a pull request and keep required checks green.
- Preserve normal responses when Markdown negotiation does not apply or conversion fails.
- Treat outbound URL fetching and filesystem writes as security-sensitive.
- Never add credentials, PyPI tokens, private URLs, or fetched private content.
- Add or update tests for observable behavior changes.
- Keep the distribution version in `pyproject.toml` and `md4a.__version__` synchronized.

## Required checks

Run before committing:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m build
python -m twine check dist/*
```

GitHub Actions runs linting, formatting, tests on Python 3.11-3.14, package
validation, and CodeQL. Dependabot monitors Python and GitHub Actions dependencies.

## Releases

The `Publish to PyPI` workflow runs for published GitHub releases and uses OIDC
Trusted Publishing through the protected `pypi` environment. Do not replace it
with a repository API token. Before publishing, confirm that the package name is
registered, the version is unique, and CI is green.

## Documentation

Keep `README.md`, `QUICKSTART.md`, `CONTRIBUTING.md`, and `SECURITY.md` aligned
with actual commands and behavior. Update this file after material changes to
architecture, workflows, release procedure, or repository policy.
