from __future__ import annotations

import argparse
import asyncio

import uvicorn

from .client import MarkdownForAgentsClient
from .store import FileStore


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="md4a", description="Markdown-for-Agents utility")
    sub = result.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="fetch and save a Markdown-for-Agents page")
    fetch.add_argument("url")
    fetch.add_argument("-o", "--output", help="output file (default: stdout)")
    serve = sub.add_parser("serve", help="run the standalone FastAPI service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return result


async def _fetch(url: str, output: str | None) -> int:
    result = await MarkdownForAgentsClient().fetch(url)
    if not result.available:
        print(f"No Markdown-for-Agents response ({result.content_type or 'unknown content type'})")
        return 2
    assert result.markdown is not None
    if output:
        FileStore(".md4a-cache").put(result.final_url, result.markdown)
        with open(output, "w", encoding="utf-8") as stream:
            stream.write(result.markdown)
    else:
        print(result.markdown, end="")
    return 0


def main() -> None:
    args = parser().parse_args()
    if args.command == "serve":
        uvicorn.run("md4a.app:app", host=args.host, port=args.port)
    else:
        raise SystemExit(asyncio.run(_fetch(args.url, args.output)))
