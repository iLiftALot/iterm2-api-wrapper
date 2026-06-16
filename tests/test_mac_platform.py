from __future__ import annotations

import asyncio

import pytest

from iterm2_api_wrapper import pyobjc_adapter


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
