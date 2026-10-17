from __future__ import annotations

import argparse
import asyncio
import os
import sys

from ._extras import require_server_extra

try:
    import httpx
    import uvicorn

    from .client import MarkdownForAgentsClient
except ImportError as exc:
    # Reported by main() so the md4a command prints one line, not a traceback.
    _missing_extra: ModuleNotFoundError | None = require_server_extra("The md4a command", exc)
else:
    _missing_extra = None


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="md4a", description="Markdown-for-Agents utility")
    sub = result.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="fetch and save a Markdown-for-Agents page")
    fetch.add_argument("url")
    fetch.add_argument("-o", "--output", help="output file (default: stdout)")
    fetch.add_argument(
        "--allowed-host",
        action="append",
        metavar="HOST",
        help="only contact this host; repeatable (default: MD4A_ALLOWED_HOSTS, else unrestricted)",
    )
    fetch.add_argument(
        "--allow-private-addresses",
        action="store_true",
        help="permit loopback, private, and other non-public destinations",
    )
    fetch.add_argument("--timeout", type=float, default=15.0, help="seconds (default: 15)")
    fetch.add_argument(
        "--max-bytes", type=int, default=5_000_000, help="response size limit (default: 5000000)"
    )
    serve = sub.add_parser("serve", help="run the standalone FastAPI service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return result


def _allowed_hosts(options: list[str] | None) -> set[str] | None:
    if options:
        return set(options)
    allowed = os.getenv("MD4A_ALLOWED_HOSTS")
    return {host.strip() for host in allowed.split(",") if host.strip()} if allowed else None


async def _fetch(args: argparse.Namespace) -> int:
    client = MarkdownForAgentsClient(
        timeout=args.timeout,
        max_bytes=args.max_bytes,
        allowed_hosts=_allowed_hosts(args.allowed_host),
        allow_private_addresses=args.allow_private_addresses,
    )
    try:
        result = await client.fetch(args.url)
    except httpx.HTTPStatusError as exc:
        print(f"md4a: origin returned HTTP {exc.response.status_code}", file=sys.stderr)
        return 1
    except (ValueError, httpx.RequestError) as exc:
        print(f"md4a: {exc}", file=sys.stderr)
        return 1
    if not result.available:
        print(f"No Markdown-for-Agents response ({result.content_type or 'unknown content type'})")
        return 2
    assert result.markdown is not None
    if args.output:
        with open(args.output, "w", encoding="utf-8") as stream:
            stream.write(result.markdown)
    else:
        print(result.markdown, end="")
    return 0


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if _missing_extra is not None:
        raise SystemExit(f"md4a: {_missing_extra}")
    if args.command == "serve":
        uvicorn.run("md4a.app:app", host=args.host, port=args.port)
    else:
        raise SystemExit(asyncio.run(_fetch(args)))
