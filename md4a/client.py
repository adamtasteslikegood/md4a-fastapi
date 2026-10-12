from __future__ import annotations

import asyncio
import ipaddress
import socket
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from . import __version__

MARKDOWN_ACCEPT = "text/markdown"

_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_ADDRESS = "md4a.address"


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


class _PinnedTransport(httpx.AsyncBaseTransport):
    """Connect to the address that was checked instead of resolving the name again.

    Only the connection target changes: the hostname is kept for Host, SNI, and
    certificate verification, and the client still sees the original URL, so
    redirects and cookies stay scoped to the hostname.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        self._transport = transport

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        address = request.extensions.get(_ADDRESS)
        if address is not None:
            request = httpx.Request(
                request.method,
                request.url.copy_with(host=address),
                headers=request.headers,
                stream=request.stream,
                extensions={
                    **request.extensions,
                    "sni_hostname": request.url.raw_host.decode("ascii"),
                },
            )
        return await self._transport.handle_async_request(request)

    async def aclose(self) -> None:
        await self._transport.aclose()


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

    def _proxied(self, url: httpx.URL) -> bool:
        """Return true when httpx will send this URL through an environment proxy."""
        if self.transport is not None:
            # httpx ignores environment proxies when it is given a transport.
            return False
        proxies = urllib.request.getproxies()
        if not (proxies.get(url.scheme) or proxies.get("all")):
            return False
        return not urllib.request.proxy_bypass(url.host)

    def _client_transport(self) -> httpx.AsyncBaseTransport | None:
        if self.allow_private_addresses:
            return self.transport
        if self.transport is not None:
            return _PinnedTransport(self.transport)
        proxies = urllib.request.getproxies()
        if any(proxies.get(scheme) for scheme in ("http", "https", "all")):
            # Leave proxy routing to httpx. A proxy resolves names itself and is
            # addressed by hostname, so connections through it cannot be pinned.
            return None
        return _PinnedTransport(httpx.AsyncHTTPTransport())

    async def _checked_address(self, url: str) -> str | None:
        """Refuse a non-public destination; return the address to connect to, if known."""
        if self.allow_private_addresses:
            return None
        target = httpx.URL(url)
        host = target.raw_host.decode("ascii")
        try:
            addresses = [str(ipaddress.ip_address(host))]
        except ValueError:
            if self._proxied(target):
                return None
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

    async def fetch(self, url: str) -> FetchResult:
        self._validate_url(url)
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=self.timeout,
            transport=self._client_transport(),
            headers={"Accept": MARKDOWN_ACCEPT, "User-Agent": f"md4a/{__version__}"},
        ) as client:
            current_url = url
            for _ in range(11):
                self._validate_url(current_url)
                address = await self._checked_address(current_url)
                request = client.build_request(
                    "GET", current_url, extensions={_ADDRESS: address} if address else {}
                )
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
                    markdown = (
                        body.decode(response.encoding or "utf-8")
                        if media_type == MARKDOWN_ACCEPT
                        else None
                    )
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
