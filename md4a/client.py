from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from . import __version__

MARKDOWN_ACCEPT = "text/markdown"

_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _is_public(value: str) -> bool:
    """Return true for a globally routable unicast address."""
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address):
        # Judge addresses that carry an IPv4 destination by that destination.
        embedded = address.ipv4_mapped or address.sixtofour
        if embedded is None and address.teredo is not None:
            embedded = address.teredo[1]
        if embedded is None and address in _NAT64:
            embedded = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
        if embedded is not None:
            address = embedded
    return address.is_global and not address.is_multicast


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
        allow_private_addresses: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.allowed_hosts = allowed_hosts
        self.allow_private_addresses = allow_private_addresses
        self.transport = transport

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("url must be an absolute http(s) URL")
        if self.allowed_hosts is not None and parsed.hostname not in self.allowed_hosts:
            raise ValueError(f"host is not allowed: {parsed.hostname}")

    async def _public_address(self, host: str) -> str:
        """Resolve host and return one address, refusing any non-public result."""
        try:
            addresses = [str(ipaddress.ip_address(host))]
        except ValueError:
            try:
                async with asyncio.timeout(self.timeout):
                    found = await asyncio.get_running_loop().getaddrinfo(
                        host, None, type=socket.SOCK_STREAM
                    )
            except (OSError, TimeoutError) as exc:
                raise httpx.ConnectError(f"could not resolve host: {host}") from exc
            addresses = [str(item[4][0]) for item in found]
        if not addresses or not all(_is_public(address) for address in addresses):
            raise ValueError(f"host is not a public address: {host}")
        return addresses[0]

    async def _build_request(self, client: httpx.AsyncClient, url: str) -> httpx.Request:
        if self.allow_private_addresses:
            return client.build_request("GET", url)
        # Connect to the address that was checked, so a second DNS answer cannot
        # redirect the connection; keep the hostname for Host, SNI, and certificates.
        target = httpx.URL(url)
        address = await self._public_address(target.host)
        return client.build_request(
            "GET",
            target.copy_with(host=address),
            headers={"Host": target.netloc.decode("ascii")},
            extensions={"sni_hostname": target.host},
        )

    async def fetch(self, url: str) -> FetchResult:
        self._validate_url(url)
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=self.timeout,
            transport=self.transport,
            headers={"Accept": MARKDOWN_ACCEPT, "User-Agent": f"md4a/{__version__}"},
        ) as client:
            current_url = url
            for _ in range(11):
                self._validate_url(current_url)
                request = await self._build_request(client, current_url)
                response = await client.send(request, stream=True)
                if response.is_redirect:
                    location = response.headers.get("location")
                    await response.aclose()
                    if not location:
                        raise ValueError("redirect response did not include a usable location")
                    # Resolve against the requested URL, not the address connected to.
                    current_url = str(httpx.URL(current_url).join(location))
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
                    markdown = (
                        body.decode(response.encoding or "utf-8")
                        if media_type == MARKDOWN_ACCEPT
                        else None
                    )
                    return FetchResult(
                        requested_url=url,
                        final_url=str(httpx.URL(current_url)),
                        status_code=response.status_code,
                        content_type=content_type,
                        markdown=markdown,
                    )
                finally:
                    await response.aclose()
            raise ValueError("too many redirects")
