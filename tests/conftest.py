import socket
from typing import Any

import pytest

PUBLIC_ADDRESS = "93.184.216.34"


@pytest.fixture(autouse=True)
def dns(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Replace name resolution so no test performs a real DNS lookup.

    Tests add hostnames to the returned mapping; unknown names fail to resolve.
    """
    records: dict[str, list[str]] = {"example.com": [PUBLIC_ADDRESS]}

    def getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        if host not in records:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (address, port or 0),
            )
            for address in records[host]
        ]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return records
