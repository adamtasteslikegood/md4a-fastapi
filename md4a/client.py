from __future__ import annotations

import ipaddress
import socket
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from urllib.parse import urlparse

from . import __version__
from ._extras import require_server_extra

try:
    import anyio
    import httpx
except ImportError as exc:
    raise require_server_extra("md4a.client", exc) from exc

MARKDOWN_ACCEPT = "text/markdown"

_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_IPV6_GLOBAL_UNICAST = ipaddress.ip_network("2000::/3")
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
        elif address not in _IPV6_GLOBAL_UNICAST:
            # ipaddress calls some ranges outside it global, such as site-local fec0::/10.
            return False
    return address.is_global and not address.is_multicast


def _literal_address(host: str) -> str | None:
    """Return the address a host spells, or None when it is a name to resolve."""
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    try:
        # Forms such as 127.1, 2130706433, and 0x7f000001 are addresses to libc.
        return socket.inet_ntoa(socket.inet_aton(host))
    except (OSError, UnicodeError):
        return None


def _exclusion_matches(pattern: httpx.URL, url: httpx.URL) -> bool:
    if pattern.scheme != "all" and pattern.scheme != url.scheme:
        return False
    if pattern.port is not None and pattern.port != url.port:
        return False
    host = pattern.host
    if host in ("", "*"):
        return True
    if host.startswith("*."):
        return url.host.endswith(host[1:]) and len(url.host) > len(host) - 1
    if host.startswith("*"):
        return url.host == host[1:] or url.host.endswith(f".{host[1:]}")
    return url.host == host


def _environment_proxy(url: httpx.URL) -> str | None:
    """Return the environment proxy httpx would send this URL through, if any.

    md4a routes requests itself, so it has to make this decision; it follows
    httpx's reading of the proxy variables (httpx._utils.get_environment_proxies).
    """
    settings = urllib.request.getproxies()
    rules: dict[str, str | None] = {}
    for scheme in ("http", "https", "all"):
        proxy = settings.get(scheme)
        if proxy:
            rules[f"{scheme}://"] = proxy if "://" in proxy else f"http://{proxy}"
    for entry in (item.strip() for item in settings.get("no", "").split(",")):
        if entry == "*":
            return None
        if not entry:
            continue
        address = entry.split("/")[0]
        if "://" in entry:
            rules[entry] = None
        elif _parses(ipaddress.IPv4Address, address) or entry.lower() == "localhost":
            rules[f"all://{entry}"] = None
        elif _parses(ipaddress.IPv6Address, address):
            rules[f"all://[{entry}]"] = None
        else:
            rules[f"all://*{entry}"] = None

    chosen: tuple[tuple[int, int, int], str | None] | None = None
    for key, proxy in rules.items():
        try:
            pattern = httpx.URL(key)
        except httpx.InvalidURL:
            continue
        if not _exclusion_matches(pattern, url):
            continue
        # The most specific rule wins: a port, then the longer host, then a scheme.
        priority = (
            pattern.port is None,
            -len("" if pattern.host == "*" else pattern.host),
            -len("" if pattern.scheme == "all" else pattern.scheme),
        )
        if chosen is None or priority < chosen[0]:
            chosen = (priority, proxy)
    return chosen[1] if chosen else None


def _parses(kind: type, value: str) -> bool:
    try:
        kind(value)
    except ValueError:
        return False
    return True


class _RoutingTransport(httpx.AsyncBaseTransport):
    """Send each request where md4a decided it goes: a proxy, or a checked address.

    Direct requests connect to the addresses that were validated instead of
    resolving the name again. Only the connection target changes: the hostname is
    kept for Host, SNI, and certificate verification, and the client still sees the
    original URL, so redirects and cookies stay scoped to the hostname.

    Each hostname gets its own direct transport. A connection pool only sees the
    pinned address, so sharing one would let a hostname reuse a connection whose
    certificate was verified for a different hostname at the same address.
    """

    def __init__(self, direct_transport: Callable[[], httpx.AsyncBaseTransport]) -> None:
        self._direct_transport = direct_transport
        self._direct: dict[str, httpx.AsyncBaseTransport] = {}
        self._proxies: dict[str, httpx.AsyncBaseTransport] = {}
        self._entered: dict[int, httpx.AsyncBaseTransport] = {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        proxy = request.extensions.get(_PROXY)
        if proxy is not None:
            if proxy not in self._proxies:
                self._proxies[proxy] = await self._enter(httpx.AsyncHTTPTransport(proxy=proxy))
            return await self._proxies[proxy].handle_async_request(request)
        addresses = request.extensions.get(_ADDRESSES)
        if not addresses:
            raise ValueError("refusing to send a request whose destination was not checked")
        hostname = request.url.raw_host.decode("ascii")
        if hostname not in self._direct:
            self._direct[hostname] = await self._enter(self._direct_transport())
        direct = self._direct[hostname]
        extensions = {**request.extensions, "sni_hostname": hostname}
        for index, address in enumerate(addresses):
            pinned = httpx.Request(
                request.method,
                request.url.copy_with(host=address),
                headers=request.headers,
                stream=request.stream,
                extensions=extensions,
            )
            try:
                return await direct.handle_async_request(pinned)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # Nothing was sent, so the next validated address can be tried.
                if index == len(addresses) - 1:
                    raise
        raise AssertionError("unreachable")

    async def _enter(self, transport: httpx.AsyncBaseTransport) -> httpx.AsyncBaseTransport:
        # A supplied transport is handed out for every hostname; enter it once.
        if id(transport) not in self._entered:
            self._entered[id(transport)] = transport
            await transport.__aenter__()
        return transport

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        entered, self._entered = self._entered, {}
        for transport in entered.values():
            await transport.__aexit__(exc_type, exc_value, traceback)

    async def aclose(self) -> None:
        await self.__aexit__()


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
        """Return the transport for one hostname's direct connections."""
        return self.transport or httpx.AsyncHTTPTransport()

    def _proxy_for(self, url: httpx.URL) -> str | None:
        """Return the environment proxy this URL goes through, if any.

        An explicitly supplied transport is never proxied.
        """
        return None if self.transport is not None else _environment_proxy(url)

    async def _route(self, url: str) -> dict[str, object]:
        """Refuse a non-public destination; return how the request must be sent."""
        target = httpx.URL(url)
        host = target.raw_host.decode("ascii")
        literal = _literal_address(host)
        if literal is not None:
            addresses = [literal]
        else:
            proxy = self._proxy_for(target)
            if proxy is not None:
                # The proxy resolves the name, so there is no address to check or pin.
                return {_PROXY: proxy}
            try:
                with anyio.fail_after(self.timeout):
                    found = await anyio.getaddrinfo(host, None, type=socket.SOCK_STREAM)
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
                else _RoutingTransport(self._direct_transport)
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
