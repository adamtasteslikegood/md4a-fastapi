from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from md4a import __version__, cli
from md4a.client import MarkdownForAgentsClient

URL = "https://example.com/page"
Handler = Callable[[httpx.Request], httpx.Response]


def _markdown(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="# Agent page\n", headers={"content-type": "text/markdown"})


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[..., int]:
    """Run the CLI in an empty directory against a fake origin; return the exit code."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MD4A_ALLOWED_HOSTS", raising=False)

    def invoke(*argv: str, handler: Handler = _markdown) -> int:
        def client(**options: Any) -> MarkdownForAgentsClient:
            return MarkdownForAgentsClient(transport=httpx.MockTransport(handler), **options)

        monkeypatch.setattr(cli, "MarkdownForAgentsClient", client)
        with pytest.raises(SystemExit) as exit_info:
            cli.main(list(argv))
        return int(exit_info.value.code or 0)

    return invoke


def test_fetch_prints_markdown(run: Callable[..., int], capsys: pytest.CaptureFixture[str]) -> None:
    assert run("fetch", URL) == 0
    assert capsys.readouterr().out == "# Agent page\n"


def test_fetch_output_writes_only_the_requested_file(
    run: Callable[..., int], tmp_path: Path
) -> None:
    assert run("fetch", URL, "-o", "article.md") == 0

    assert (tmp_path / "article.md").read_text(encoding="utf-8") == "# Agent page\n"
    assert [path.name for path in tmp_path.iterdir()] == ["article.md"]


def test_fetch_reports_origin_without_markdown(
    run: Callable[..., int], capsys: pytest.CaptureFixture[str]
) -> None:
    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<h1>Page</h1>", headers={"content-type": "text/html"})

    assert run("fetch", URL, handler=html) == 2
    assert "text/html" in capsys.readouterr().out


def test_fetch_allowed_host_option_rejects_other_hosts(
    run: Callable[..., int], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("fetch", URL, "--allowed-host", "other.example") == 1
    assert "host is not allowed: example.com" in capsys.readouterr().err


def test_fetch_allowed_host_option_accepts_listed_host(run: Callable[..., int]) -> None:
    assert (
        run("fetch", URL, "--allowed-host", "other.example", "--allowed-host", "example.com") == 0
    )


def test_fetch_honours_allowed_hosts_environment(
    run: Callable[..., int],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MD4A_ALLOWED_HOSTS", "other.example, another.example")

    assert run("fetch", URL) == 1
    assert "host is not allowed: example.com" in capsys.readouterr().err


def test_fetch_max_bytes_option_limits_response(
    run: Callable[..., int], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("fetch", URL, "--max-bytes", "5") == 1
    assert "response exceeds 5 bytes" in capsys.readouterr().err


def test_fetch_timeout_option_reports_timeout(
    run: Callable[..., int], capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[dict[str, float]] = []

    def slow(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        raise httpx.ReadTimeout("timed out", request=request)

    assert run("fetch", URL, "--timeout", "3", handler=slow) == 1
    assert seen[0]["read"] == 3.0
    assert "timed out" in capsys.readouterr().err


def test_fetch_reports_origin_error_status(
    run: Callable[..., int], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("fetch", URL, handler=lambda request: httpx.Response(503)) == 1
    assert "503" in capsys.readouterr().err


def test_client_user_agent_uses_package_version(run: Callable[..., int]) -> None:
    agents: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        agents.append(request.headers["user-agent"])
        return _markdown(request)

    assert run("fetch", URL, handler=record) == 0
    assert agents == [f"md4a/{__version__}"]
