from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from iterm2_api_wrapper.api import it2runtime


def test_validate_app_version_checks_capabilities(monkeypatch) -> None:
    calls: list[str] = []
    connection = SimpleNamespace(iterm2_protocol_version=(1, 14))

    monkeypatch.setattr(it2runtime, "check_supports_prompt_monitor_modes", lambda conn: calls.append("prompt"))
    monkeypatch.setattr(it2runtime, "check_supports_get_default_profile", lambda conn: calls.append("profile"))
    monkeypatch.setattr(it2runtime, "check_supports_prompt_id", lambda conn: calls.append("prompt_id"))

    it2runtime._validate_app_version(connection)  # pyright: ignore[reportArgumentType]

    assert calls == ["prompt", "profile", "prompt_id"]


def test_bootstrap_and_validate_runtime_can_be_called_sequentially(monkeypatch) -> None:
    calls: list[object] = []

    async def bootstrap() -> None:
        calls.append("bootstrap")

    monkeypatch.setattr(it2runtime, "bootstrap_iterm2_runtime", bootstrap)
    monkeypatch.setattr(
        it2runtime, "validate_iterm2_runtime", lambda connection: calls.append(("validate", connection))
    )

    async def scenario() -> None:
        bootstrap_result = await it2runtime.bootstrap_iterm2_runtime()
        validate_result = it2runtime.validate_iterm2_runtime("connection")  # pyright: ignore[reportArgumentType]

        assert bootstrap_result is None
        assert validate_result is None

    asyncio.run(scenario())
    assert calls == ["bootstrap", ("validate", "connection")]


def test_bootstrap_runs_once_and_skips_enhance_by_default(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(it2runtime, "_BOOTSTRAPPED", False)
    monkeypatch.setattr(it2runtime, "_install_iterm2_connection_bridge", lambda: calls.append("install"))
    monkeypatch.setattr(it2runtime, "_enhance_iterm2_imports", lambda: calls.append("enhance"))
    monkeypatch.delenv("IT2_ENHANCE_IMPORTS", raising=False)

    asyncio.run(it2runtime.bootstrap_iterm2_runtime())
    # Second call is a no-op because the module flag is now set.
    asyncio.run(it2runtime.bootstrap_iterm2_runtime())

    assert calls == ["install"]
    assert it2runtime._BOOTSTRAPPED is True


def test_bootstrap_enhances_imports_when_env_enabled(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(it2runtime, "_BOOTSTRAPPED", False)
    monkeypatch.setattr(it2runtime, "_install_iterm2_connection_bridge", lambda: calls.append("install"))
    monkeypatch.setattr(it2runtime, "_enhance_iterm2_imports", lambda: calls.append("enhance"))
    monkeypatch.setenv("IT2_ENHANCE_IMPORTS", "true")

    asyncio.run(it2runtime.bootstrap_iterm2_runtime())

    assert calls == ["install", "enhance"]


def test_install_connection_bridge_points_upstream_at_wrapper() -> None:
    import iterm2
    import iterm2.connection as upstream_connection

    from iterm2_api_wrapper.api.it2connection import Connection, run_forever, run_until_complete

    saved = {
        "upstream_conn": upstream_connection.Connection,
        "upstream_ruc": upstream_connection.run_until_complete,
        "upstream_rf": upstream_connection.run_forever,
        "pkg_conn": iterm2.Connection,
        "pkg_ruc": iterm2.run_until_complete,
        "pkg_rf": iterm2.run_forever,
    }
    try:
        it2runtime._install_iterm2_connection_bridge()

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


def test_enhance_iterm2_imports_returns_early_when_all_present(monkeypatch) -> None:
    import iterm2

    # When __all__ already exists, the function must not attempt a file write.
    monkeypatch.setattr(iterm2, "__all__", ["already", "present"], raising=False)

    def fail_read_text(self) -> str:  # pragma: no cover - guard against accidental write path
        raise AssertionError("_enhance_iterm2_imports should not touch the package file")

    monkeypatch.setattr("pathlib.Path.read_text", fail_read_text)

    assert it2runtime._enhance_iterm2_imports() is None


def test_enhance_iterm2_imports_writes_sorted_public_exports(tmp_path, monkeypatch) -> None:
    import iterm2

    package_root = tmp_path / "__init__.py"
    package_root.write_text("# package root\n", encoding="utf-8")
    monkeypatch.delattr(iterm2, "__all__", raising=False)
    monkeypatch.setattr(iterm2, "__file__", str(package_root))
    monkeypatch.setattr(iterm2, "testing_manager_export", object(), raising=False)
    monkeypatch.setattr(iterm2, "_testing_manager_private", object(), raising=False)

    it2runtime._enhance_iterm2_imports()

    contents = package_root.read_text(encoding="utf-8")
    encoded_exports = contents.split("__all__ = ", 1)[1]
    exports = json.loads(encoded_exports)
    assert exports == sorted(exports)
    assert "testing_manager_export" in exports
    assert "_testing_manager_private" in exports
    assert "__file__" not in exports


def test_validate_app_version_logs_protocol_version(monkeypatch) -> None:
    connection = SimpleNamespace(iterm2_protocol_version=(1, 5))

    monkeypatch.setattr(it2runtime, "check_supports_prompt_monitor_modes", lambda conn: None)
    monkeypatch.setattr(it2runtime, "check_supports_get_default_profile", lambda conn: None)
    monkeypatch.setattr(it2runtime, "check_supports_prompt_id", lambda conn: None)

    logged: list[str] = []
    monkeypatch.setattr(it2runtime.log, "debug", lambda *args, **kwargs: logged.append(" ".join(map(str, args))))

    it2runtime._validate_app_version(connection)  # pyright: ignore[reportArgumentType]

    assert any("1.5" in entry for entry in logged)
