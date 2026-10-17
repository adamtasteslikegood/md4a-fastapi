"""Clear errors for features that need the optional ``server`` dependencies."""

from __future__ import annotations

SERVER_EXTRA = frozenset({"anyio", "httpx", "uvicorn"})


def require_server_extra(feature: str, exc: ImportError) -> ModuleNotFoundError:
    """Explain how to install a missing server dependency; re-raise anything else."""
    if exc.name not in SERVER_EXTRA:
        raise exc
    return ModuleNotFoundError(
        f"{feature} needs {exc.name}, which is part of the optional server dependencies. "
        "Install them with: pip install 'md4a-fastapi[server]'",
        name=exc.name,
    )
