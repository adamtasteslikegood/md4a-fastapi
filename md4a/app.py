from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response

from . import __version__
from ._extras import require_server_extra
from .store import FileStore

try:
    import httpx

    from .client import MarkdownForAgentsClient
except ImportError as exc:
    raise require_server_extra("The standalone md4a service", exc) from exc


def create_app() -> FastAPI:
    cache_dir = Path(os.getenv("MD4A_CACHE_DIR", ".md4a-cache"))
    allowed = os.getenv("MD4A_ALLOWED_HOSTS")
    allowed_hosts = (
        {host.strip() for host in allowed.split(",") if host.strip()} if allowed else None
    )
    store = FileStore(cache_dir)
    allow_private = os.getenv("MD4A_ALLOW_PRIVATE_ADDRESSES", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    client = MarkdownForAgentsClient(
        allowed_hosts=allowed_hosts, allow_private_addresses=allow_private
    )
    app = FastAPI(title="md4a", version=__version__)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/fetch")
    async def fetch(url: str = Query(..., description="Absolute page URL")) -> Response:
        try:
            result = await client.fetch(url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"origin returned HTTP {exc.response.status_code}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"origin request failed: {exc}") from exc
        if not result.available:
            raise HTTPException(
                status_code=406,
                detail=(
                    f"origin returned {result.content_type or 'no content type'}, not text/markdown"
                ),
            )
        assert result.markdown is not None
        store.put(result.final_url, result.markdown)
        return Response(
            result.markdown,
            media_type="text/markdown",
            headers={"X-MD4A-Source": result.final_url},
        )

    return app


app = create_app()
