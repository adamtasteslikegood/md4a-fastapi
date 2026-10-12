import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from md4a import FetchResult, MarkdownForAgentsClient, cli
from md4a.app import create_app

PUBLIC_ADDRESS = "93.184.216.34"  # what the fake resolver returns for example.com


def _markdown(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="# Page", headers={"content-type": "text/markdown"})


def _fetch(
    url: str, handler: object = _markdown, **options: object
) -> tuple[FetchResult, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)  # type: ignore[operator]

    client = MarkdownForAgentsClient(transport=httpx.MockTransport(record), **options)  # type: ignore[arg-type]
    return asyncio.run(client.fetch(url)), requests


def _assert_blocked(url: str, handler: object = _markdown) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)  # type: ignore[operator]

    client = MarkdownForAgentsClient(transport=httpx.MockTransport(record))
    with pytest.raises(ValueError, match="not a public address"):
        asyncio.run(client.fetch(url))
    return requests


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "[::1]",
        "[fe80::1]",
        "[fd00::1]",
        "[::ffff:127.0.0.1]",
        "[64:ff9b::7f00:1]",
        "[2002:7f00:1::]",
        # Spellings that libc-style parsers, including proxies, read as 127.0.0.1.
        "127.1",
        "2130706433",
        "0x7f000001",
        "017700000001",
    ],
)
def test_literal_non_public_address_is_rejected_without_a_request(host: str) -> None:
    assert _assert_blocked(f"http://{host}/page") == []


@pytest.mark.parametrize(
    "addresses",
    [["10.0.0.5"], ["::1"], [PUBLIC_ADDRESS, "192.168.1.1"]],
)
def test_hostname_resolving_to_non_public_address_is_rejected(
    dns: dict[str, list[str]], addresses: list[str]
) -> None:
    dns["internal.example"] = addresses

    assert _assert_blocked("https://internal.example/page") == []


@pytest.mark.parametrize("location", ["http://127.0.0.1/secret", "https://internal.example/"])
def test_redirect_to_non_public_address_is_rejected_before_following(
    dns: dict[str, list[str]], location: str
) -> None:
    dns["internal.example"] = ["10.0.0.5"]

    requests = _assert_blocked(
        "https://example.com/page",
        lambda request: httpx.Response(302, headers={"location": location}),
    )

    assert len(requests) == 1


def test_request_connects_to_the_validated_address() -> None:
    result, requests = _fetch("https://example.com:8443/page?x=1")

    request = requests[0]
    assert request.url == f"https://{PUBLIC_ADDRESS}:8443/page?x=1"
    assert request.headers["host"] == "example.com:8443"
    assert request.extensions["sni_hostname"] == "example.com"
    assert result.final_url == "https://example.com:8443/page?x=1"


def test_ipv6_address_is_used_for_the_connection(dns: dict[str, list[str]]) -> None:
    dns["v6.example"] = ["2606:4700::1111"]

    _, requests = _fetch("https://v6.example/page")

    assert requests[0].url == "https://[2606:4700::1111]/page"
    assert requests[0].headers["host"] == "v6.example"


def test_relative_redirect_is_resolved_against_the_requested_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return _markdown(request)

    result, requests = _fetch("https://example.com/old", handler)

    assert [request.headers["host"] for request in requests] == ["example.com", "example.com"]
    assert requests[1].url == f"https://{PUBLIC_ADDRESS}/new"
    assert result.final_url == "https://example.com/new"
    assert result.markdown == "# Page"


def test_unresolvable_host_is_reported_as_a_request_error() -> None:
    with pytest.raises(httpx.ConnectError, match="nowhere.example"):
        _fetch("https://nowhere.example/page")


def test_allow_private_addresses_permits_local_destinations() -> None:
    result, requests = _fetch("http://127.0.0.1:8000/page", allow_private_addresses=True)

    assert requests[0].url == "http://127.0.0.1:8000/page"
    assert result.markdown == "# Page"


def test_allowlisted_host_must_still_resolve_to_a_public_address(
    dns: dict[str, list[str]],
) -> None:
    dns["internal.example"] = ["10.0.0.5"]
    client = MarkdownForAgentsClient(
        allowed_hosts={"internal.example"}, transport=httpx.MockTransport(_markdown)
    )

    with pytest.raises(ValueError, match="not a public address"):
        asyncio.run(client.fetch("https://internal.example/page"))


def test_standalone_service_rejects_private_destination() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/fetch", params={"url": "http://127.0.0.1/admin"})

    assert response.status_code == 400
    assert "not a public address" in response.json()["detail"]


def test_cli_rejects_private_destination_unless_allowed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MD4A_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(
        cli,
        "MarkdownForAgentsClient",
        lambda **options: MarkdownForAgentsClient(
            transport=httpx.MockTransport(_markdown), **options
        ),
    )

    with pytest.raises(SystemExit) as blocked:
        cli.main(["fetch", "http://127.0.0.1:8000/page"])
    assert blocked.value.code == 1
    assert "not a public address" in capsys.readouterr().err

    with pytest.raises(SystemExit) as allowed:
        cli.main(["fetch", "http://127.0.0.1:8000/page", "--allow-private-addresses"])
    assert allowed.value.code == 0
    assert capsys.readouterr().out == "# Page"


def test_standalone_service_private_address_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MD4A_ALLOW_PRIVATE_ADDRESSES", "true")

    with TestClient(create_app()) as client:
        # Nothing listens on port 1: the request is attempted and fails, not refused.
        response = client.get("/fetch", params={"url": "http://127.0.0.1:1/page"})

    assert response.status_code == 502
    assert "origin request failed" in response.json()["detail"]


def _cookie_then_redirect(location: str) -> list[httpx.Request]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(
                302, headers={"location": location, "set-cookie": "session=secret; Path=/"}
            )
        return _markdown(request)

    _, requests = _fetch("https://example.com/start", handler)
    return requests


def test_cookie_is_not_sent_to_another_host_sharing_the_address(
    dns: dict[str, list[str]],
) -> None:
    dns["other.example"] = [PUBLIC_ADDRESS]

    requests = _cookie_then_redirect("https://other.example/next")

    assert requests[1].headers["host"] == "other.example"
    assert "cookie" not in requests[1].headers


def test_cookie_is_sent_back_to_the_host_that_set_it() -> None:
    requests = _cookie_then_redirect("/next")

    assert requests[1].headers["cookie"] == "session=secret"


PROXY_VARIABLES = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"]
DIRECT_REQUESTS: list[httpx.Request] = []


def _fetch_through_proxy(
    monkeypatch: pytest.MonkeyPatch, url: str, *, no_proxy: str = ""
) -> tuple[list[str], BaseException | None]:
    """Fetch with HTTPS_PROXY pointing at a local listener; return what it was asked for.

    Requests that do not go to the proxy are answered by a stand-in for the direct
    transport and recorded in ``DIRECT_REQUESTS``, so nothing leaves the machine.
    """
    DIRECT_REQUESTS.clear()

    def direct(request: httpx.Request) -> httpx.Response:
        DIRECT_REQUESTS.append(request)
        return _markdown(request)

    monkeypatch.setattr(
        MarkdownForAgentsClient,
        "_direct_transport",
        lambda self: httpx.MockTransport(direct),
        raising=False,
    )
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    request_lines: list[str] = []

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_lines.append((await reader.readline()).decode().strip())
        writer.close()

    async def run() -> BaseException | None:
        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{port}")
        if no_proxy:
            monkeypatch.setenv("NO_PROXY", no_proxy)
        try:
            await MarkdownForAgentsClient(timeout=5).fetch(url)
        except (ValueError, httpx.HTTPError) as exc:
            return exc
        finally:
            server.close()
            await server.wait_closed()
        return None

    return request_lines, asyncio.run(run())


def test_environment_proxy_is_asked_for_the_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    # The proxy resolves the name; pinning an address would break TLS through it.
    lines, error = _fetch_through_proxy(monkeypatch, "https://proxied.example/page")

    assert lines == ["CONNECT proxied.example:443 HTTP/1.1"]
    assert isinstance(error, httpx.HTTPError)


def test_literal_private_address_is_rejected_behind_a_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines, error = _fetch_through_proxy(monkeypatch, "https://10.0.0.5/page")

    assert lines == []
    assert isinstance(error, ValueError) and "not a public address" in str(error)


@pytest.mark.parametrize("host", ["127.1", "2130706433", "0x7f000001"])
def test_alternative_address_spelling_is_rejected_behind_a_proxy(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    lines, error = _fetch_through_proxy(monkeypatch, f"https://{host}/page")

    assert lines == []
    assert isinstance(error, ValueError) and "not a public address" in str(error)


def test_host_bypassing_the_proxy_is_still_resolved_and_checked(
    monkeypatch: pytest.MonkeyPatch, dns: dict[str, list[str]]
) -> None:
    dns["internal.example"] = ["10.0.0.5"]

    lines, error = _fetch_through_proxy(
        monkeypatch, "https://internal.example/page", no_proxy="internal.example"
    )

    assert lines == []
    assert isinstance(error, ValueError) and "not a public address" in str(error)


def test_port_qualified_proxy_bypass_is_resolved_and_checked(
    monkeypatch: pytest.MonkeyPatch, dns: dict[str, list[str]]
) -> None:
    dns["internal.example"] = ["10.0.0.5"]

    lines, error = _fetch_through_proxy(
        monkeypatch, "https://internal.example:8443/page", no_proxy="internal.example:8443"
    )

    assert lines == [] and DIRECT_REQUESTS == []
    assert isinstance(error, ValueError) and "not a public address" in str(error)


def test_host_bypassing_the_proxy_connects_to_the_validated_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines, error = _fetch_through_proxy(
        monkeypatch, "https://example.com/page", no_proxy="example.com"
    )

    assert error is None and lines == []
    assert [str(request.url) for request in DIRECT_REQUESTS] == [f"https://{PUBLIC_ADDRESS}/page"]
    assert DIRECT_REQUESTS[0].headers["host"] == "example.com"


def test_unproxied_scheme_connects_to_the_validated_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only HTTPS_PROXY is set, so plain HTTP goes direct and must stay pinned.
    lines, error = _fetch_through_proxy(monkeypatch, "http://example.com/page")

    assert error is None and lines == []
    assert [str(request.url) for request in DIRECT_REQUESTS] == [f"http://{PUBLIC_ADDRESS}/page"]


def test_next_validated_address_is_tried_when_one_cannot_be_reached(
    dns: dict[str, list[str]],
) -> None:
    dns["multi.example"] = ["2606:4700::1111", PUBLIC_ADDRESS]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != PUBLIC_ADDRESS:
            raise httpx.ConnectError("unreachable", request=request)
        return _markdown(request)

    result, requests = _fetch("https://multi.example/page", handler)

    assert [request.url.host for request in requests] == ["2606:4700::1111", PUBLIC_ADDRESS]
    assert result.markdown == "# Page"
    assert result.final_url == "https://multi.example/page"


def test_connection_error_is_raised_when_no_validated_address_can_be_reached(
    dns: dict[str, list[str]],
) -> None:
    dns["multi.example"] = ["2606:4700::1111", PUBLIC_ADDRESS]

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    with pytest.raises(httpx.ConnectError):
        _fetch("https://multi.example/page", handler)


@pytest.mark.parametrize("no_proxy", ["*,localhost", "https://example.com", ".com"])
def test_proxy_exclusion_forms_understood_by_httpx_connect_directly(
    monkeypatch: pytest.MonkeyPatch, no_proxy: str
) -> None:
    lines, error = _fetch_through_proxy(monkeypatch, "https://example.com/page", no_proxy=no_proxy)

    assert error is None and lines == []
    assert [str(request.url) for request in DIRECT_REQUESTS] == [f"https://{PUBLIC_ADDRESS}/page"]


@pytest.mark.parametrize(
    "no_proxy",
    [
        "",
        "*",
        "localhost, *",
        "example.com",
        ".example.com",
        "ample.com",
        "com",
        "example.com:443",
        "example.com:8443",
        "https://example.com",
        "http://example.com",
        "all://*.example.com",
        "93.184.216.34",
        "10.0.0.0/8",
        "::1",
        "localhost",
    ],
)
@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/page",
        "http://example.com/page",
        "https://www.example.com/page",
        "https://example.com:8443/page",
        "https://93.184.216.34/page",
        "https://[::1]/page",
        "http://localhost/page",
    ],
)
def test_proxy_decision_matches_httpx(
    monkeypatch: pytest.MonkeyPatch, no_proxy: str, url: str
) -> None:
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", no_proxy)
    probe = httpx.AsyncClient()
    expected = probe._transport_for_url(httpx.URL(url)) is not probe._transport

    assert (MarkdownForAgentsClient()._proxy_for(httpx.URL(url)) is not None) == expected


def test_hostnames_sharing_an_address_do_not_share_connections(
    monkeypatch: pytest.MonkeyPatch, dns: dict[str, list[str]]
) -> None:
    # A pooled connection is keyed by the pinned address, and its certificate was
    # only verified for the hostname it was opened for.
    dns["other.example"] = [PUBLIC_ADDRESS]
    seen: list[tuple[int, str]] = []
    created: list[httpx.MockTransport] = []

    def direct_transport(self: MarkdownForAgentsClient) -> httpx.MockTransport:
        index = len(created)

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((index, request.headers["host"]))
            hops = {"/a": "https://other.example/b", "/b": "https://example.com/c"}
            if request.url.path in hops:
                return httpx.Response(302, headers={"location": hops[request.url.path]})
            return _markdown(request)

        created.append(httpx.MockTransport(handler))
        return created[-1]

    monkeypatch.setattr(MarkdownForAgentsClient, "_direct_transport", direct_transport)
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)

    asyncio.run(MarkdownForAgentsClient().fetch("https://example.com/a"))

    assert seen == [(0, "example.com"), (1, "other.example"), (0, "example.com")]
