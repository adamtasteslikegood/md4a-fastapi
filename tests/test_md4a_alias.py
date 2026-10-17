"""The md4a distribution must install md4a-fastapi at exactly this release."""

import tomllib
from pathlib import Path

import pytest

import md4a

PYPROJECT = Path(__file__).parent.parent / "meta" / "md4a" / "pyproject.toml"

# The md4a-fastapi sdist ships the tests but not meta/.
pytestmark = pytest.mark.skipif(not PYPROJECT.exists(), reason="meta/md4a is not present")


def project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]


def test_alias_version_matches_the_package_version() -> None:
    assert project()["version"] == md4a.__version__


def test_alias_pins_md4a_fastapi_to_the_same_version() -> None:
    pinned = f"=={md4a.__version__}"
    requirements = project()["dependencies"] + [
        requirement
        for extra in project()["optional-dependencies"].values()
        for requirement in extra
    ]
    assert requirements
    for requirement in requirements:
        assert requirement.startswith("md4a-fastapi"), requirement
        assert requirement.endswith(pinned), requirement


def test_alias_offers_the_same_extras_as_md4a_fastapi() -> None:
    root = tomllib.loads((PYPROJECT.parents[2] / "pyproject.toml").read_text(encoding="utf-8"))
    public = set(root["project"]["optional-dependencies"]) - {"test"}
    assert set(project()["optional-dependencies"]) == public
