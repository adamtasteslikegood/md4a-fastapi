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

Add user-visible changes under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md)
as part of each pull request.

To release, a maintainer:

1. Opens a `release/vX.Y.Z` pull request to `main` that sets `__version__` in
   `md4a/__init__.py`, sets the same version and `==X.Y.Z` pins in
   `meta/md4a/pyproject.toml` (a test fails if they differ), and moves the
   `Unreleased` entries under a dated `## [X.Y.Z]` heading.
2. Merges it once CI is green.
3. Publishes a GitHub release whose new tag `vX.Y.Z` targets `main`, using the
   changelog section as the release notes.
4. Approves the `pypi` environment deployment after checking the built
   `release-distributions` artifact.

The release publishes both `md4a-fastapi` and the `md4a` alias. The publish
workflow refuses a commit that is not on `main` and a tag that does not match
`__version__`. It uses PyPI Trusted Publishing through the protected
`pypi` GitHub environment.

Do not add API tokens to the repository or workflow files.
