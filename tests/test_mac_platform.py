from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest

from iterm2_api_wrapper import iTermConnection, pyobjc_adapter


def test_iterm_not_open_reports_false_when_app_is_running(monkeypatch: pytest.MonkeyPatch) -> None:
    class RunningApplication:
        @staticmethod
        def runningApplicationsWithBundleIdentifier_(bundle: str) -> list[object]:
            assert bundle == "com.googlecode.iterm2"
            return [object()]

    monkeypatch.setattr(pyobjc_adapter, "NSRunningApplication", RunningApplication)

    assert pyobjc_adapter.is_iterm_app_running() is True
    assert pyobjc_adapter.iterm_not_open() is False


def test_iterm_not_open_reports_true_when_app_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class RunningApplication:
        @staticmethod
        def runningApplicationsWithBundleIdentifier_(bundle: str) -> list[object]:
            assert bundle == "com.googlecode.iterm2"
            return []

    monkeypatch.setattr(pyobjc_adapter, "NSRunningApplication", RunningApplication)

    assert pyobjc_adapter.is_iterm_app_running() is False
    assert pyobjc_adapter.iterm_not_open() is True


def test_async_ensure_iterm_app_running_launches_and_activates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    class FakeApplication:
        def __init__(self) -> None:
            self.active = False

        def isActive(self) -> bool:
            return self.active

        def activateWithOptions_(self, options: int) -> bool:
            calls.append(("activate", options))
            self.active = True
            return True

        def bundleIdentifier(self) -> str:
            return "com.googlecode.iterm2"

        def bundleURL(self) -> str:
            return "file:///Applications/iTerm.app/"

    app = FakeApplication()

    class FakeContainer:
        def __init__(self) -> None:
            self.running_iterm_apps: list[FakeApplication] = []

        def launch(self) -> None:
            calls.append("launch")
            self.running_iterm_apps = [app]

        def activate(self, running_app: FakeApplication) -> None:
            calls.append("container_activate")
            running_app.activateWithOptions_(3)

    container = FakeContainer()

    async def fake_wait_for_finished_application(app_container: FakeContainer, **kwargs) -> FakeApplication:
        calls.append(("wait", kwargs))
        assert app_container is container
        return app

    monkeypatch.setattr(pyobjc_adapter, "PyObjcContainer", lambda: container)
    monkeypatch.setattr(pyobjc_adapter, "_wait_for_finished_application", fake_wait_for_finished_application)

    result = asyncio.run(pyobjc_adapter.async_ensure_iterm_app_running(activate=True))

    assert result is app
    assert calls == [
        "launch",
        ("wait", {"timeout_s": pyobjc_adapter.ITERM_NEW_APP_TIMEOUT, "poll_interval_s": 0.5}),
        "container_activate",
        ("activate", 3),
    ]


def test_async_ensure_iterm_app_running_does_not_launch_running_app(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    class FakeApplication:
        def bundleIdentifier(self) -> str:
            return "com.googlecode.iterm2"

        def bundleURL(self) -> str:
            return "file:///Applications/iTerm.app/"

    app = FakeApplication()

    class FakeContainer:
        def __init__(self) -> None:
            self.running_iterm_apps = [app]

        def launch(self) -> None:
            calls.append("launch")

        def activate(self, running_app: FakeApplication) -> None:
            calls.append(("activate", running_app))

    container = FakeContainer()

    async def fake_wait_for_finished_application(app_container: FakeContainer, **kwargs) -> FakeApplication:
        calls.append(("wait", kwargs))
        assert app_container is container
        return app

    monkeypatch.setattr(pyobjc_adapter, "PyObjcContainer", lambda: container)
    monkeypatch.setattr(pyobjc_adapter, "_wait_for_finished_application", fake_wait_for_finished_application)

    result = asyncio.run(pyobjc_adapter.async_ensure_iterm_app_running(activate=False))

    assert result is app
    assert calls == [("wait", {"timeout_s": pyobjc_adapter.ITERM_NEW_APP_TIMEOUT, "poll_interval_s": 0.5})]


def test_get_new_app_timeout_parses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITERM_NEW_APP_TIMEOUT", "5.5")
    assert pyobjc_adapter._get_new_app_timeout_s() == 5.5

    # Negative values clamp to zero.
    monkeypatch.setenv("ITERM_NEW_APP_TIMEOUT", "-3")
    assert pyobjc_adapter._get_new_app_timeout_s() == 0.0

    # Invalid values fall back to the default.
    monkeypatch.setenv("ITERM_NEW_APP_TIMEOUT", "not-a-number")
    monkeypatch.setattr(pyobjc_adapter.log, "warning", lambda *a, **k: None)
    assert pyobjc_adapter._get_new_app_timeout_s() == pyobjc_adapter._DEFAULT_NEW_APP_TIMEOUT_S


def test_activation_options_combines_flags() -> None:
    expected = pyobjc_adapter.NSApplicationActivateAllWindows | pyobjc_adapter.NSApplicationActivateIgnoringOtherApps
    assert pyobjc_adapter._activation_options() == expected


def test_log_launch_completion_handles_all_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[str] = []
    debugs: list[str] = []
    monkeypatch.setattr(pyobjc_adapter.log, "warning", lambda msg, *a, **k: warnings.append(str(msg)))
    monkeypatch.setattr(pyobjc_adapter.log, "debug", lambda msg, *a, **k: debugs.append(str(msg)))

    # Error branch.
    pyobjc_adapter._log_launch_completion(None, RuntimeError("bad"))
    assert any("error" in w for w in warnings)

    # No-application branch.
    pyobjc_adapter._log_launch_completion(None, None)
    assert any("without a running application" in d for d in debugs)

    # Success branch.
    running_app = SimpleNamespace(bundleIdentifier=lambda: "com.googlecode.iterm2", isFinishedLaunching=lambda: True)
    pyobjc_adapter._log_launch_completion(cast(pyobjc_adapter.NSRunningApplication, running_app), None)
    assert any("launch callback completed: bundle=" in d for d in debugs)


def test_wait_for_finished_application_returns_first_ready() -> None:
    app = object()

    class FakeContainer:
        def first_finished_application(self) -> object:
            return app

    result = asyncio.run(
        pyobjc_adapter._wait_for_finished_application(
            cast(pyobjc_adapter.PyObjcContainer, FakeContainer()), timeout_s=1.0
        )
    )
    assert result is app


def test_wait_for_finished_application_times_out() -> None:
    class FakeContainer:
        def first_finished_application(self) -> None:
            return None

    with pytest.raises(RuntimeError, match="finished loading"):
        asyncio.run(
            pyobjc_adapter._wait_for_finished_application(
                cast(pyobjc_adapter.PyObjcContainer, FakeContainer()), timeout_s=0.0
            )
        )


def test_async_create_app_with_retry_launches_then_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    from iterm2_api_wrapper import gateway as gateway_module

    calls: list[tuple[str, Any]] = []

    async def fake_ensure(*, activate: bool) -> object:
        calls.append(("ensure", activate))
        return object()

    async def fake_create_connection(connection_cls: object, *, timeout_s: float) -> str:
        calls.append(("connect", timeout_s))
        return "connection"

    monkeypatch.setattr(pyobjc_adapter, "async_ensure_iterm_app_running", fake_ensure)
    monkeypatch.setattr(gateway_module, "_async_create_connection_with_retry", fake_create_connection)

    result = asyncio.run(pyobjc_adapter.async_create_app_with_retry(cast("iTermConnection", object), activate=True))

    assert result == "connection"
    assert calls == [("ensure", True), ("connect", pyobjc_adapter._CONNECTION_READY_TIMEOUT_S)]


def test_maybe_reveal_hotkey_window_requires_applescript_package() -> None:
    # The optional `applescript` dependency is not installed in the test env, so the
    # module exposes the fallback that raises a helpful ImportError.
    from iterm2_api_wrapper.mac import maybe_reveal_hotkey_window

    with pytest.raises(ImportError, match="applescript"):
        maybe_reveal_hotkey_window(True)
