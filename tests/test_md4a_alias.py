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


def test_alias_depends_on_md4a_fastapi_at_the_same_version() -> None:
    assert project()["dependencies"] == [f"md4a-fastapi=={md4a.__version__}"]


def test_each_alias_extra_installs_the_same_md4a_fastapi_extra() -> None:
    for extra, requirements in project()["optional-dependencies"].items():
        assert requirements == [f"md4a-fastapi[{extra}]=={md4a.__version__}"], extra


def test_alias_offers_the_same_extras_as_md4a_fastapi() -> None:
    root = tomllib.loads((PYPROJECT.parents[2] / "pyproject.toml").read_text(encoding="utf-8"))
    public = set(root["project"]["optional-dependencies"]) - {"test"}
    assert set(project()["optional-dependencies"]) == public
