"""Runtime and static contracts for cached environment lookups."""

import os
from typing import Literal, assert_type
from unittest.mock import patch

import pytest

from iterm2_api_wrapper.utils.env import Env
from iterm2_api_wrapper.utils.logger import get_logger
from iterm2_api_wrapper.utils.sentinel import MISSING


logger = get_logger()
patch_env = pytest.mark.usefixtures("patch_environ")


@pytest.fixture
def patch_environ(request: pytest.FixtureRequest):
    func: pytest.Function = request.node
    marker = next((m for m in func.iter_markers("usefixtures") if "patch_environ" in m.args), None)
    env = marker.kwargs.get("env") if marker is not None else None

    with patch.dict(os.environ, env or {}, clear=True):
        yield


@patch_env
def test_missing_value_is_cached() -> None:
    lookup = Env.get("WRAPPER_TEST_ENV")
    assert lookup is None
    os.environ["WRAPPER_TEST_ENV"] = "later"
    assert lookup is None


@patch_env
def test_present_value_is_cached_lazily() -> None:
    lookup = Env("WRAPPER_TEST_ENV", "fallback")
    os.environ["WRAPPER_TEST_ENV"] = "first"
    assert lookup.value == "first"
    os.environ["WRAPPER_TEST_ENV"] = "second"
    assert lookup.value == "first"


@patch_env(env={"WRAPPER_TEST_ENV": ""})
def test_empty_value_overrides_default_and_is_cached() -> None:
    with patch.dict(os.environ, {"WRAPPER_TEST_ENV": ""}, clear=True):
        lookup = Env("WRAPPER_TEST_ENV", "fallback")
        assert lookup.value == ""
        del os.environ[lookup.key]
        assert lookup.value == ""


@patch_env
def test_defaults_and_explicit_missing() -> None:
    assert Env("WRAPPER_TEST_ENV").value is None
    assert Env("WRAPPER_TEST_ENV", None).value is None
    assert Env("WRAPPER_TEST_ENV", MISSING).value is None
    assert Env.get("WRAPPER_TEST_ENV", MISSING) is None
    assert Env.get(key="WRAPPER_TEST_ENV", default="fallback") == "fallback"
    assert Env.get("WRAPPER_TEST_ENV", "") == ""


@patch_env
def test_boolean_and_environment_checks() -> None:
    for value in ("1", "true", "TRUE"):
        assert Env("WRAPPER_TEST_ENV", value).isTrue()
    for value in (None, "", "0", "false", "FALSE"):
        assert Env("WRAPPER_TEST_ENV", value).isFalse()
    with patch.dict(os.environ, {"ENV": "PROD"}, clear=True):
        assert Env.isProd()
        assert not Env.isDev()
    with patch.dict(os.environ, {}, clear=True):
        assert Env.isDev()
        assert not Env.isProd()


@patch_env
def test_type_inference() -> None:
    assert_type(Env("WRAPPER_TEST_ENV").value, str | None)
    assert_type(Env("WRAPPER_TEST_ENV", None).value, str | None)
    assert_type(Env("WRAPPER_TEST_ENV", MISSING).value, str | None)
    assert_type(Env("WRAPPER_TEST_ENV", "fallback").value, str)
    assert_type(Env.get("WRAPPER_TEST_ENV"), str | None)
    assert_type(Env.get("WRAPPER_TEST_ENV", None), str | None)
    assert_type(Env.get("WRAPPER_TEST_ENV", MISSING), str | None)
    assert_type(Env.get("WRAPPER_TEST_ENV", "fallback"), str)
    key: Literal["WRAPPER_TEST_ENV"] = "WRAPPER_TEST_ENV"
    assert_type(Env.get(key), str | None)
    typed_lookup = Env(key, "fallback")
    assert_type(typed_lookup.value, str)
    default: str | None = os.environ.get("ANOTHER_WRAPPER_TEST_ENV")
    assert_type(Env(key, default).value, str | None)
    assert_type(Env.get(key, default), str | None)


@patch_env(env={"WRAPPER_TEST_ENV": "value"})
class TestMeta:
    def test_getitem(self) -> None:
        assert Env["WRAPPER_TEST_ENV"] == "value"

    def test_setitem(self) -> None:
        Env["WRAPPER_TEST_ENV"] = "new"
        assert os.environ["WRAPPER_TEST_ENV"] == "new"

    def test_del(self) -> None:
        assert "WRAPPER_TEST_ENV" in os.environ
        del Env["WRAPPER_TEST_ENV"]
        assert "WRAPPER_TEST_ENV" not in os.environ
