"""Markdown-for-Agents helpers for FastAPI (ASGI) and WSGI applications."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__version__ = "0.2.0"

if TYPE_CHECKING:
    from .client import FetchResult, MarkdownForAgentsClient
    from .middleware import MarkdownForAgentsMiddleware, add_md4a
    from .store import FileStore, MemoryStore
    from .wsgi import MarkdownForAgentsWSGIMiddleware

# Loaded on first use, so importing md4a.wsgi for a Flask application does not
# import FastAPI, Starlette or httpx.
_EXPORTS = {
    "FetchResult": ".client",
    "MarkdownForAgentsClient": ".client",
    "MarkdownForAgentsMiddleware": ".middleware",
    "add_md4a": ".middleware",
    "FileStore": ".store",
    "MemoryStore": ".store",
    "MarkdownForAgentsWSGIMiddleware": ".wsgi",
}

__all__ = [
    "FetchResult",
    "FileStore",
    "MarkdownForAgentsClient",
    "MarkdownForAgentsMiddleware",
    "MarkdownForAgentsWSGIMiddleware",
    "MemoryStore",
    "__version__",
    "add_md4a",
]


# Importing these eagerly used to make them attributes of the package, so
# ``md4a.store.MemoryStore`` keeps working after ``import md4a`` alone.
_SUBMODULES = frozenset({"client", "middleware", "store", "wsgi"})


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        value = getattr(import_module(_EXPORTS[name], __name__), name)
        globals()[name] = value
        return value
    if name in _SUBMODULES:
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Include lazy public exports in module discovery before first access."""
    return sorted(set(globals()) | set(__all__))
