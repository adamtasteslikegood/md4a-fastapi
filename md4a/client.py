from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

MARKDOWN_ACCEPT = "text/markdown"


@dataclass(frozen=True, slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    markdown: str | None

    @property
    def available(self) -> bool:
        return self.markdown is not None


class MarkdownForAgentsClient:
    """Probe URLs using the Markdown-for-Agents content negotiation header."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_bytes: int = 5_000_000,
        allowed_hosts: set[str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.allowed_hosts = allowed_hosts
        self.transport = transport

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("url must be an absolute http(s) URL")
        if self.allowed_hosts is not None and parsed.hostname not in self.allowed_hosts:
            raise ValueError(f"host is not allowed: {parsed.hostname}")

    async def fetch(self, url: str) -> FetchResult:
        self._validate_url(url)
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=self.timeout,
            transport=self.transport,
            headers={"Accept": MARKDOWN_ACCEPT, "User-Agent": "md4a/0.1"},
        ) as client:
            current_url = url
            for _ in range(11):
                self._validate_url(current_url)
                request = client.build_request("GET", current_url)
                response = await client.send(request, stream=True)
                if response.is_redirect:
                    redirect = response.next_request
                    await response.aclose()
                    if redirect is None:
                        raise ValueError("redirect response did not include a usable location")
                    current_url = str(redirect.url)
                    continue

                try:
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise ValueError(f"response exceeds {self.max_bytes} bytes")
                        chunks.append(chunk)

                    content_type = response.headers.get("content-type", "")
                    media_type = content_type.partition(";")[0].strip().lower()
                    body = b"".join(chunks)
                    markdown = body.decode(response.encoding or "utf-8") if media_type == MARKDOWN_ACCEPT else None
                    return FetchResult(
                        requested_url=url,
                        final_url=str(response.url),
                        status_code=response.status_code,
                        content_type=content_type,
                        markdown=markdown,
                    )
                finally:
                    await response.aclose()
            raise ValueError("too many redirects")
