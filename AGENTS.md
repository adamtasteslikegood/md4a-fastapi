# AGENTS.md

This file tells coding agents how to work safely and consistently in this repository.

## Project overview

`md4a-fastapi` is an early-alpha Python library and service for Markdown for Agents
HTTP content negotiation. It lets FastAPI/ASGI applications respond to
`Accept: text/markdown`, discovers native Markdown representations from remote URLs,
and stores verified or converted Markdown in memory or on disk.

- PyPI distribution: `md4a-fastapi`
- Python import and CLI: `md4a`
- Runtime: Python 3.11 through 3.14
- Framework: FastAPI/Starlette ASGI
- Build backend: Hatchling
- License: MIT

## Repository map

- `md4a/middleware.py` — intercepts eligible GET requests, negotiates Markdown,
  invokes providers, converts successful HTML responses, and caches results.
- `md4a/client.py` — requests remote URLs with `Accept: text/markdown`; validates
  schemes, redirects, host allowlists, status codes, media type, and response size.
- `md4a/store.py` — `MemoryStore`, filesystem-backed `FileStore`, and the store protocol.
- `md4a/app.py` — standalone FastAPI application with `/health` and `/fetch`.
- `md4a/cli.py` — `md4a fetch` and `md4a serve` commands.
- `md4a/__init__.py` — public exports and canonical runtime `__version__`.
- `tests/` — unit and integration-style tests using pytest and FastAPI TestClient.
- `.github/workflows/` — CI, CodeQL, and PyPI publishing automation.
- `README.md`, `QUICKSTART.md` — user installation and usage documentation.
- `CONTRIBUTING.md`, `SECURITY.md` — contributor and vulnerability guidance.

## Request and content flow

For middleware requests:

1. Non-HTTP, non-GET, or requests that do not accept `text/markdown` pass through.
2. Cached or provider-supplied Markdown is returned first.
3. Otherwise, the wrapped application runs normally.
4. Successful HTML may be converted to Markdown and cached.
5. Existing Markdown is cached; JSON and other response types pass through unchanged.

For remote discovery, only a response whose media type is exactly `text/markdown`
is considered available. Do not infer availability merely because a body resembles
Markdown.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

If a copied or moved virtual environment has stale launcher paths, recreate it.
Prefer `python -m <tool>` so the intended interpreter is explicit.

## Required local checks

Run before committing:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m build
python -m twine check dist/*
```

Install `build` and `twine` when needed. Add or update tests for every observable
behavior change, particularly header parsing, content types, `Vary: Accept`,
redirects, allowlists, size limits, error paths, and storage behavior.

## Coding and security invariants

- Preserve ordinary application responses when Markdown negotiation does not apply.
- Do not convert or cache unsuccessful HTML responses as successful Markdown.
- Preserve `Content-Type: text/markdown; charset=utf-8` and `Vary: Accept` semantics.
- Keep redirect validation active before each outbound request.
- Treat remote fetching as SSRF-sensitive. Do not weaken scheme or host validation;
  deployments exposed to untrusted callers must set `MD4A_ALLOWED_HOSTS` and should
  also enforce network-level egress controls.
- Bound buffered response bodies and HTML conversion inputs.
- Treat filesystem paths and cache indexes as security-sensitive.
- Never commit credentials, PyPI tokens, private URLs, or fetched private content.
- Keep `pyproject.toml` version and `md4a.__version__` synchronized. Runtime consumers,
  including the standalone FastAPI app, must read the canonical package version.
- Maintain Python 3.11 compatibility and public typing information (`py.typed`).

## Git and pull requests

`main` is protected. Work on `feat/`, `fix/`, `docs/`, or `chore/` branches and open
a pull request; do not push directly to `main`. Use focused conventional-style
commits and a conventional-style PR title. Resolve every review finding by fixing
it, technically rebutting it, or explicitly escalating it. Resolve review threads
before merge and delete merged feature branches.

Required GitHub checks are:

- `Lint`
- `Test (Python 3.11)` through `Test (Python 3.14)`
- `Build package`
- `Analyze (Python)` / CodeQL
- `GitGuardian Security Checks`

## CI, security, and dependency automation

- `ci.yml` runs on PRs to `main`, pushes to `main`, and manual dispatch. It checks
  Ruff lint/format, tests Python 3.11–3.14, builds wheel/sdist artifacts, and runs Twine.
- `codeql.yml` scans PRs and `main`, runs weekly, and supports manual dispatch.
- `dependabot.yml` checks pip and GitHub Actions dependencies every Monday.
- GitHub vulnerability alerts, automated security updates, private vulnerability
  reporting, secret scanning, and protected-main checks are repository controls.

Do not weaken action permissions, required checks, branch protection, or security
scanning without an explicit, documented decision.

## Releases and publishing

`publish.yml` builds and publishes when a GitHub Release is published, with optional
manual dispatch. Publishing uses OIDC Trusted Publishing through the protected
`pypi` GitHub environment; never replace this with a committed or long-lived PyPI
API token.

Before a release:

1. Confirm the PyPI Trusted Publisher matches owner `adamtasteslikegood`, repository
   `md4a-fastapi`, workflow `publish.yml`, and environment `pypi`.
2. Update both version declarations and release notes.
3. Run the complete local suite and confirm required PR checks and security scans.
4. Merge through protected `main`, then publish the GitHub Release.
5. Verify the actual PyPI project, artifacts, metadata, and installation afterward.

## Documentation maintenance

Keep this file and all user documentation aligned with real behavior and commands.
Update `AGENTS.md` after material architecture, dependency, workflow, security,
branch-policy, or release-process changes.
