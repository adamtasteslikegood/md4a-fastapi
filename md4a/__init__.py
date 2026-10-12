"""Markdown-for-Agents helpers for FastAPI (ASGI) and WSGI applications."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__version__ = "0.1.0"

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


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        value = getattr(import_module(_EXPORTS[name], __name__), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
