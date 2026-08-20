# Contributing

Thanks for helping improve `md4a-fastapi`. This project is in early alpha, so
focused issues and small pull requests are especially valuable.

## Before starting

1. Search existing issues and pull requests.
2. Open an issue for behavioral changes or larger designs.
3. Do not include secrets, credentials, private URLs, or sensitive fetched content.
4. Use a feature branch; direct pushes to `main` are not part of the workflow.

Security vulnerabilities should follow [SECURITY.md](SECURITY.md), not a public issue.

## Development setup

```bash
git clone https://github.com/adamtasteslikegood/md4a-fastapi.git
cd md4a-fastapi
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

## Make a change

Create a descriptive branch:

```bash
git switch -c feat/short-description
```

Keep changes scoped. Add or update tests for observable behavior, especially:

- `Accept` header parsing and content negotiation
- response media types and `Vary: Accept`
- redirects, allowlists, response limits, and error paths
- filesystem and in-memory storage behavior

## Local checks

Run the same baseline checks as CI:

```bash
ruff check .
ruff format --check .
pytest -q
python -m build
python -m twine check dist/*
```

Install the packaging tools for the final two commands when needed:

```bash
python -m pip install build twine
```

## Pull requests

- Complete the pull request template.
- Explain the user-visible outcome and any compatibility or security impact.
- Link the relevant issue when one exists.
- Keep CI and CodeQL green.
- Resolve review conversations before merge.
- Use a Conventional Commit-style title such as `feat:`, `fix:`, `docs:`, or `chore:`.

Maintainers use squash merges so the pull request title becomes the commit on
`main`.

## Releases

Releases are built from GitHub release tags matching `v*`. The publish workflow
uses PyPI Trusted Publishing and a protected GitHub environment named `pypi`.
Maintainers must verify the package version, changelog/release notes, license,
CI status, and built artifacts before creating a release.

Do not add API tokens to the repository or workflow files.
