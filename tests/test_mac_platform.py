from __future__ import annotations

import pytest

from iterm2_api_wrapper.mac import platform_macos


def test_activate_iterm_app_does_nothing_when_app_is_already_running(monkeypatch: pytest.MonkeyPatch) -> None:
    launched: list[bool] = []

    class RunningApplication:
        @staticmethod
        def runningApplicationsWithBundleIdentifier_(bundle: str) -> list[object]:
            assert bundle == "com.googlecode.iterm2"
            return [object()]

    class WorkspaceInstance:
        def launchAppWithBundleIdentifier_options_additionalEventParamDescriptor_launchIdentifier_(self, *args):
            launched.append(True)
            return True, None

    class Workspace:
        @staticmethod
        def sharedWorkspace() -> WorkspaceInstance:
            return WorkspaceInstance()

    monkeypatch.setattr(platform_macos, "NSRunningApplication", RunningApplication)
    monkeypatch.setattr(platform_macos, "NSWorkspace", Workspace)

    platform_macos.activate_iterm_app()

    assert launched == []


def test_activate_iterm_app_raises_when_launch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class RunningApplication:
        @staticmethod
        def runningApplicationsWithBundleIdentifier_(bundle: str) -> list[object]:
            return []

    class WorkspaceInstance:
        def launchAppWithBundleIdentifier_options_additionalEventParamDescriptor_launchIdentifier_(self, *args):
            return False, None

    class Workspace:
        @staticmethod
        def sharedWorkspace() -> WorkspaceInstance:
            return WorkspaceInstance()

    monkeypatch.setattr(platform_macos, "NSRunningApplication", RunningApplication)
    monkeypatch.setattr(platform_macos, "NSWorkspace", Workspace)

    with pytest.raises(RuntimeError, match="Could not launch iTerm2 application"):
        platform_macos.activate_iterm_app()
