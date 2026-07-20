from __future__ import annotations

import asyncio
import json
from types import CoroutineType, SimpleNamespace
from typing import Any, TypeVar, cast

import pytest

import iterm2_api_wrapper


T = TypeVar("T")


async def __(_: T = None) -> T:
    return _


NOOPT = __


class it2runtime:
    _BOOTSTRAPPED = False

    check_supports_prompt_monitor_modes = staticmethod(NOOPT)
    check_supports_get_default_profile = staticmethod(NOOPT)
    check_supports_prompt_id = staticmethod(NOOPT)

    bootstrap_iterm2_runtime = staticmethod(NOOPT)
    install_it2_connection_bridge = staticmethod(NOOPT)
    enhance_it2_imports = staticmethod(NOOPT)

    @classmethod
    def validate_iterm2_runtime(cls, _) -> None:
        if it2runtime._BOOTSTRAPPED is True:
            return

        async def scenario():
            await cls.check_supports_prompt_monitor_modes(_)
            await cls.check_supports_get_default_profile(_)
            await cls.check_supports_prompt_id(_)
            await cls.bootstrap_iterm2_runtime(_)
            await cls.install_it2_connection_bridge(_)
            await cls.enhance_it2_imports(_)

        asyncio.run(scenario())
        it2runtime._BOOTSTRAPPED = True


@pytest.fixture
def reset_bootstrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iterm2_api_wrapper, "_BOOTSTRAPPED", False)


def get_fake_connection(protocol_version: tuple[int, int] | None = None) -> type[iterm2_api_wrapper._Connection]:
    from iterm2_api_wrapper.api.it2connection import Connection

    class FakeConnection:
        iterm2_protocol_version = protocol_version or (1, 14)
        loop: asyncio.AbstractEventLoop | None = None

        @staticmethod
        def async_create() -> CoroutineType[Any, Any, Connection]:
            return cast(CoroutineType[Any, Any, Connection], NOOPT(FakeConnection()))

    return FakeConnection


def test_validate_app_version_checks_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    connection = SimpleNamespace(iterm2_protocol_version=(1, 14))

    monkeypatch.setattr(it2runtime, "check_supports_prompt_monitor_modes", lambda conn: NOOPT(calls.append("prompt")))
    monkeypatch.setattr(it2runtime, "check_supports_get_default_profile", lambda conn: NOOPT(calls.append("profile")))
    monkeypatch.setattr(it2runtime, "check_supports_prompt_id", lambda conn: NOOPT(calls.append("prompt_id")))

    it2runtime.validate_iterm2_runtime(connection)

    assert calls == ["prompt", "profile", "prompt_id"]


def test_bootstrap_and_validate_runtime_can_be_called_sequentially(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    monkeypatch.setattr(it2runtime, "bootstrap_iterm2_runtime", lambda conn: NOOPT(calls.append("bootstrap")))
    monkeypatch.setattr(
        it2runtime, "validate_iterm2_runtime", lambda connection: calls.append(("validate", connection))
    )

    async def scenario() -> None:
        bootstrap_result = await it2runtime.bootstrap_iterm2_runtime(None)
        validate_result = it2runtime.validate_iterm2_runtime("connection")

        assert bootstrap_result is None
        assert validate_result is None

    asyncio.run(scenario())
    assert calls == ["bootstrap", ("validate", "connection")]


def test_bootstrap_runs_once_and_skips_enhance_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(it2runtime, "_BOOTSTRAPPED", False)

    monkeypatch.setattr(it2runtime, "install_it2_connection_bridge", lambda _: NOOPT(calls.append("install")))
    it2runtime.validate_iterm2_runtime(None)

    # Second call is a no-op because the module flag is now set.
    monkeypatch.setattr(it2runtime, "enhance_it2_imports", lambda _: NOOPT(calls.append("enhance")))
    it2runtime.validate_iterm2_runtime(None)

    assert calls == ["install"]
    assert it2runtime._BOOTSTRAPPED is True


def test_install_connection_bridge_points_upstream_at_wrapper(
    monkeypatch: pytest.MonkeyPatch, reset_bootstrapped: None
) -> None:
    import iterm2
    import iterm2.connection as upstream_connection

    from iterm2_api_wrapper.api.it2connection import Connection, run_forever, run_until_complete

    # Keep enhance_it2_imports from appending __all__ to the installed iterm2 package.
    monkeypatch.setattr(iterm2, "__all__", ["sentinel"], raising=False)

    saved = {
        "upstream_conn": upstream_connection.Connection,
        "upstream_ruc": upstream_connection.run_until_complete,
        "upstream_rf": upstream_connection.run_forever,
        "pkg_conn": iterm2.Connection,
        "pkg_ruc": iterm2.run_until_complete,
        "pkg_rf": iterm2.run_forever,
    }

    try:
        connection = (get_fake_connection())()
        iterm2_api_wrapper.validate_iterm2_runtime(connection)

        assert upstream_connection.Connection is Connection
        assert upstream_connection.run_until_complete is run_until_complete
        assert upstream_connection.run_forever is run_forever
        assert iterm2.Connection is Connection
    finally:
        upstream_connection.Connection = saved["upstream_conn"]
        upstream_connection.run_until_complete = saved["upstream_ruc"]
        upstream_connection.run_forever = saved["upstream_rf"]
        iterm2.Connection = saved["pkg_conn"]
        iterm2.run_until_complete = saved["pkg_ruc"]
        iterm2.run_forever = saved["pkg_rf"]


def test_enhance_it2_imports_returns_early_when_all_present(monkeypatch: pytest.MonkeyPatch) -> None:
    import pathlib

    import iterm2

    # When __all__ already exists, the function must not attempt a file write.
    monkeypatch.setattr(iterm2, "__all__", ["already", "present"], raising=False)

    def fail_read_text(self) -> str:
        raise AssertionError("enhance_it2_imports should not touch the package file")

    monkeypatch.setattr("pathlib.Path.read_text", fail_read_text)
    monkeypatch.setattr(
        it2runtime,
        "enhance_it2_imports",
        lambda _: NOOPT(
            None if getattr(iterm2, "__all__", None) is not None else pathlib.Path(iterm2.__file__).read_text()
        ),
    )

    assert asyncio.run(it2runtime.enhance_it2_imports(None)) is None


def test_enhance_iterm2_imports_writes_sorted_public_exports(
    tmp_path, monkeypatch: pytest.MonkeyPatch, reset_bootstrapped: None
) -> None:
    import iterm2

    connection = (get_fake_connection())()
    package_root = tmp_path / "__init__.py"
    package_root.write_text("# package root\n", encoding="utf-8")

    monkeypatch.delattr(iterm2, "__all__", raising=False)
    monkeypatch.setattr(iterm2, "__file__", str(package_root))
    monkeypatch.setattr(iterm2, "testing_manager_export", object(), raising=False)
    monkeypatch.setattr(iterm2, "_testing_manager_private", object(), raising=False)

    iterm2_api_wrapper.validate_iterm2_runtime(connection)

    contents = package_root.read_text(encoding="utf-8")
    encoded_exports = contents.split("__all__ = ", 1)[1]
    exports = json.loads(encoded_exports)

    assert exports == sorted(exports)
    assert "testing_manager_export" in exports
    assert "_testing_manager_private" in exports
    assert "__file__" not in exports


def test_validate_app_version_logs_protocol_version(monkeypatch: pytest.MonkeyPatch, reset_bootstrapped: None) -> None:
    import iterm2

    # Keep enhance_it2_imports from appending __all__ to the installed iterm2 package.
    monkeypatch.setattr(iterm2, "__all__", ["sentinel"], raising=False)
    connection = (get_fake_connection((1, 5)))()

    logged: list[str] = []
    monkeypatch.setattr(
        iterm2_api_wrapper.logger, "debug", lambda *args, **kwargs: logged.append(" ".join(map(str, args)))
    )

    iterm2_api_wrapper.validate_iterm2_runtime(connection)

    assert any("1.5" in entry for entry in logged)
