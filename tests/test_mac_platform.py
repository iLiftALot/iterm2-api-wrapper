from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

import pytest

from iterm2_api_wrapper import pyobjc_adapter


if TYPE_CHECKING:
    from iterm2_api_wrapper.api.it2connection import Connection


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


class FakeApplication:
    def __init__(self) -> None:
        self.calls: list[object] = []
        self.active = False

    def isActive(self) -> bool:
        return self.active

    def activateWithOptions_(self, options: int) -> bool:
        self.calls.append(("activate", options))
        self.active = True
        return True

    def bundleIdentifier(self) -> str:
        return "com.googlecode.iterm2"

    def bundleURL(self) -> str:
        return "file:///Applications/iTerm.app/"

    def isFinishedLaunching(self) -> bool:
        return True


class FakeContainer:
    def __init__(self, app: FakeApplication) -> None:
        self.app = app
        self.running_iterm_apps: list[FakeApplication] = []

    def first_finished_application(self) -> FakeApplication | None:
        for application in self.running_iterm_apps:
            if application.isFinishedLaunching():
                return application
        return None

    def launch(self) -> None: ...

    def activate(self, running_app: FakeApplication) -> None: ...

    @classmethod
    def asPyObjc(cls, app: FakeApplication | None = None) -> pyobjc_adapter.PyObjcContainer:
        resolved_app = app or FakeApplication()
        return cast(pyobjc_adapter.PyObjcContainer, cls(resolved_app))


def test_async_ensure_iterm_app_running_launches_and_activates(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FakeApplication()

    class _FakeContainer(FakeContainer):
        def launch(self) -> None:
            app.calls.append("launch")
            self.running_iterm_apps = [app]

        def activate(self, running_app: FakeApplication) -> None:
            app.calls.append("container_activate")
            running_app.activateWithOptions_(3)

    container = _FakeContainer.asPyObjc(app)

    async def fake_wait_for_finished_application(app_container: FakeContainer, **kwargs) -> FakeApplication:
        app.calls.append(("wait", kwargs))
        assert app_container is container
        return app

    monkeypatch.setattr(pyobjc_adapter, "PyObjcContainer", lambda: container)
    monkeypatch.setattr(pyobjc_adapter, "_wait_for_finished_application", fake_wait_for_finished_application)

    result = asyncio.run(pyobjc_adapter.async_ensure_iterm_app_running(activate=True))

    assert result is app
    assert app.calls == [
        "launch",
        ("wait", {"timeout_s": pyobjc_adapter.ITERM_NEW_APP_TIMEOUT, "poll_interval_s": 0.5}),
        "container_activate",
        ("activate", 3),
    ]


def test_async_ensure_iterm_app_running_does_not_launch_running_app(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FakeApplication()
    container = FakeContainer.asPyObjc(app)

    async def fake_wait_for_finished_application(app_container: FakeContainer, **kwargs) -> FakeApplication:
        app.calls.append(("wait", kwargs))
        assert app_container is container
        return app

    monkeypatch.setattr(pyobjc_adapter, "PyObjcContainer", lambda: container)
    monkeypatch.setattr(pyobjc_adapter, "_wait_for_finished_application", fake_wait_for_finished_application)

    result = asyncio.run(pyobjc_adapter.async_ensure_iterm_app_running(activate=False))

    assert result is app
    assert app.calls == [("wait", {"timeout_s": pyobjc_adapter.ITERM_NEW_APP_TIMEOUT, "poll_interval_s": 0.5})]


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
    # running_app = SimpleNamespace(bundleIdentifier=lambda: "com.googlecode.iterm2", isFinishedLaunching=lambda: True)
    running_app = FakeApplication()
    pyobjc_adapter._log_launch_completion(cast(pyobjc_adapter.NSRunningApplication, running_app), None)
    assert any("launch callback completed: bundle=" in d for d in debugs)


def test_wait_for_finished_application_returns_first_ready() -> None:
    app = FakeApplication()
    container = FakeContainer.asPyObjc(app)
    cast(FakeContainer, container).running_iterm_apps = [app]
    result = asyncio.run(pyobjc_adapter._wait_for_finished_application(container, timeout_s=1.0))
    assert result is app


def test_wait_for_finished_application_times_out() -> None:
    with pytest.raises(RuntimeError, match="finished loading"):
        asyncio.run(pyobjc_adapter._wait_for_finished_application(FakeContainer.asPyObjc(), timeout_s=0.0))


class FakeConnection:
    loop: asyncio.AbstractEventLoop | None = None

    async def async_create(self) -> Connection:
        return cast("Connection", object())


def test_async_create_app_with_retry_launches_then_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    from iterm2_api_wrapper import gateway as gateway_module

    # calls: list[tuple[str, Any]] = []
    app = FakeApplication()

    async def fake_ensure(*, activate: bool) -> object:
        app.calls.append(("ensure", activate))
        return app

    async def fake_create_connection(connection_cls: object, *, timeout_s: float) -> str:
        app.calls.append(("connect", timeout_s))
        return "connection"

    monkeypatch.setattr(pyobjc_adapter, "async_ensure_iterm_app_running", fake_ensure)
    monkeypatch.setattr(gateway_module, "_async_create_connection_with_retry", fake_create_connection)

    result = asyncio.run(pyobjc_adapter.async_create_app_with_retry(FakeConnection, activate=True))

    assert result == "connection"
    assert app.calls == [("ensure", True), ("connect", pyobjc_adapter._CONNECTION_READY_TIMEOUT_S)]


def test_maybe_reveal_hotkey_window_requires_applescript_package() -> None:
    # The optional `applescript` dependency is not installed in the test env, so the
    # module exposes the fallback that raises a helpful ImportError.
    from iterm2_api_wrapper.mac import maybe_reveal_hotkey_window

    with pytest.raises(ImportError, match="applescript"):
        maybe_reveal_hotkey_window(True)
