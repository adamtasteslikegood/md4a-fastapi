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
_ADDRESSES = "md4a.addresses"
_PROXY = "md4a.proxy"


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


class _RoutingTransport(httpx.AsyncBaseTransport):
    """Send each request where md4a decided it goes: a proxy, or a checked address.

    Direct requests connect to the addresses that were validated instead of
    resolving the name again. Only the connection target changes: the hostname is
    kept for Host, SNI, and certificate verification, and the client still sees the
    original URL, so redirects and cookies stay scoped to the hostname.
    """

    def __init__(self, direct: httpx.AsyncBaseTransport) -> None:
        self._direct = direct
        self._proxies: dict[str, httpx.AsyncBaseTransport] = {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        proxy = request.extensions.get(_PROXY)
        if proxy is not None:
            if proxy not in self._proxies:
                self._proxies[proxy] = httpx.AsyncHTTPTransport(proxy=proxy)
            return await self._proxies[proxy].handle_async_request(request)
        addresses = request.extensions.get(_ADDRESSES)
        if not addresses:
            raise ValueError("refusing to send a request whose destination was not checked")
        extensions = {**request.extensions, "sni_hostname": request.url.raw_host.decode("ascii")}
        for index, address in enumerate(addresses):
            pinned = httpx.Request(
                request.method,
                request.url.copy_with(host=address),
                headers=request.headers,
                stream=request.stream,
                extensions=extensions,
            )
            try:
                return await self._direct.handle_async_request(pinned)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # Nothing was sent, so the next validated address can be tried.
                if index == len(addresses) - 1:
                    raise
        raise AssertionError("unreachable")

    async def aclose(self) -> None:
        await self._direct.aclose()
        for transport in self._proxies.values():
            await transport.aclose()


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

    def _direct_transport(self) -> httpx.AsyncBaseTransport:
        return self.transport or httpx.AsyncHTTPTransport()

    def _proxy_for(self, url: httpx.URL) -> str | None:
        """Return the environment proxy this URL goes through, if any.

        md4a routes requests itself, so this is the only place that decides it;
        an explicitly supplied transport is never proxied.
        """
        if self.transport is not None:
            return None
        proxies = urllib.request.getproxies()
        proxy = proxies.get(url.scheme) or proxies.get("all")
        if not proxy:
            return None
        port = url.port or (443 if url.scheme == "https" else 80)
        host = url.raw_host.decode("ascii")
        # Exclusions may name a host or a host:port pair.
        if urllib.request.proxy_bypass(host) or urllib.request.proxy_bypass(f"{host}:{port}"):
            return None
        return proxy if "://" in proxy else f"http://{proxy}"

    async def _route(self, url: str) -> dict[str, object]:
        """Refuse a non-public destination; return how the request must be sent."""
        target = httpx.URL(url)
        host = target.raw_host.decode("ascii")
        try:
            addresses = [str(ipaddress.ip_address(host))]
        except ValueError:
            proxy = self._proxy_for(target)
            if proxy is not None:
                # The proxy resolves the name, so there is no address to check or pin.
                return {_PROXY: proxy}
            try:
                async with asyncio.timeout(self.timeout):
                    found = await asyncio.get_running_loop().getaddrinfo(
                        host, None, type=socket.SOCK_STREAM
                    )
            except (OSError, TimeoutError) as exc:
                raise httpx.ConnectError(f"could not resolve host: {host}") from exc
            addresses = list(dict.fromkeys(str(item[4][0]) for item in found))
        if not addresses or not all(_is_public(address) for address in addresses):
            raise ValueError(f"host is not a public address: {host}")
        proxy = self._proxy_for(target)
        return {_PROXY: proxy} if proxy is not None else {_ADDRESSES: addresses}

    async def fetch(self, url: str) -> FetchResult:
        self._validate_url(url)
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=self.timeout,
            # With the check off, httpx routes and resolves as it normally would.
            transport=(
                self.transport
                if self.allow_private_addresses
                else _RoutingTransport(self._direct_transport())
            ),
            headers={"Accept": MARKDOWN_ACCEPT, "User-Agent": f"md4a/{__version__}"},
        ) as client:
            current_url = url
            for _ in range(11):
                self._validate_url(current_url)
                route = {} if self.allow_private_addresses else await self._route(current_url)
                request = client.build_request("GET", current_url, extensions=route)
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
