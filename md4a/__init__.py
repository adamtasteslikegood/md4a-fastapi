"""Markdown-for-Agents helpers for FastAPI applications."""

__version__ = "0.1.0"

from .client import FetchResult, MarkdownForAgentsClient
from .middleware import MarkdownForAgentsMiddleware, add_md4a
from .store import FileStore, MemoryStore

__all__ = [
    "FetchResult",
    "FileStore",
    "MarkdownForAgentsClient",
    "MarkdownForAgentsMiddleware",
    "MemoryStore",
    "__version__",
    "add_md4a",
]
