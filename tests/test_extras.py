import subprocess
import sys
from importlib.metadata import version

import pytest

import md4a
from md4a._extras import require_server_extra

# Run with the server dependencies hidden, as in a base install.
WITHOUT_SERVER_EXTRA = (
    "import sys\nfor name in ('httpx', 'uvicorn'):\n    sys.modules[name] = None\n"
)


def run(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", WITHOUT_SERVER_EXTRA + script], capture_output=True, text=True
    )


def test_middlewares_and_stores_work_without_the_server_extra() -> None:
    result = run(
        "from md4a import MarkdownForAgentsWSGIMiddleware, MemoryStore, add_md4a\n"
        "from md4a.middleware import MarkdownForAgentsMiddleware\n"
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("statement", "feature"),
    [
        ("import md4a.client", "md4a.client"),
        ("from md4a import MarkdownForAgentsClient", "md4a.client"),
        ("import md4a.app", "The standalone md4a service"),
    ],
)
def test_server_features_explain_how_to_install_the_extra(statement: str, feature: str) -> None:
    result = run(statement)
    assert result.returncode != 0
    assert f"ModuleNotFoundError: {feature} needs httpx" in result.stderr
    assert "pip install 'md4a-fastapi[server]'" in result.stderr


def test_md4a_command_prints_one_line_without_the_server_extra() -> None:
    result = run("from md4a.cli import main\nmain(['fetch', 'https://example.com/'])\n")
    assert result.returncode == 1
    assert result.stderr == (
        "md4a: The md4a command needs httpx, which is part of the optional server "
        "dependencies. Install them with: pip install 'md4a-fastapi[server]'\n"
    )


def test_other_import_errors_are_not_reworded() -> None:
    error = ImportError("broken", name="somethingelse")
    with pytest.raises(ImportError) as raised:
        require_server_extra("md4a.client", error)
    assert raised.value is error


def test_package_metadata_version_comes_from_the_module() -> None:
    assert version("md4a-fastapi") == md4a.__version__
