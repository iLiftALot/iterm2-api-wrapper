from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from iterm2_api_wrapper.api import it2api as api_module
from iterm2_api_wrapper import runtime_setup


class FakeProfile:
    def __init__(self, name: str) -> None:
        self.name = name


def test_check_api_enabled_reads_defaults_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime_setup.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="1\n")
    )
    assert runtime_setup._check_api_enabled() is True

    monkeypatch.setattr(
        runtime_setup.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="0\n")
    )
    assert runtime_setup._check_api_enabled() is False

    def raise_error(*args: Any, **kwargs: Any) -> None:
        raise OSError("defaults unavailable")

    monkeypatch.setattr(runtime_setup.subprocess, "run", raise_error)
    assert runtime_setup._check_api_enabled() is False


def test_enable_api_returns_subprocess_status(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runtime_setup.subprocess, "run", fake_run)
    assert runtime_setup._enable_api() is True
    assert calls[0][:4] == ["defaults", "write", "com.googlecode.iterm2", "EnableAPIServer"]

    def raise_error(*args: Any, **kwargs: Any) -> None:
        raise OSError("defaults unavailable")

    monkeypatch.setattr(runtime_setup.subprocess, "run", raise_error)
    assert runtime_setup._enable_api() is False


def test_get_profile_returns_default_or_named_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        default = FakeProfile("Default")
        profiles = [default, FakeProfile("Work")]

        class ProfileAPI:
            @staticmethod
            async def async_get_default(connection: object) -> FakeProfile:
                return default

            @staticmethod
            async def async_get(connection: object) -> list[FakeProfile]:
                return profiles

        monkeypatch.setattr(runtime_setup, "Profile", ProfileAPI)

        assert await runtime_setup.get_profile("connection") is default
        assert (await runtime_setup.get_profile("connection", "Work")).name == "Work"
        with pytest.raises(ValueError, match="Profile with name 'Missing' not found"):
            await runtime_setup.get_profile("connection", "Missing")

    asyncio.run(scenario())


def test_get_app_requires_iterm_app(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        app_instance = object()

        async def get_app(connection: object, *, create_if_needed: bool) -> object:
            assert create_if_needed is True
            return app_instance

        monkeypatch.setattr(runtime_setup, "async_get_app", get_app)
        assert await runtime_setup._get_app("connection") is app_instance

        async def get_none(connection: object, *, create_if_needed: bool) -> None:
            return None

        monkeypatch.setattr(runtime_setup, "async_get_app", get_none)
        with pytest.raises(RuntimeError, match="Could not get iTerm2 app"):
            await runtime_setup._get_app("connection")

    asyncio.run(scenario())


def test_get_window_uses_current_window_or_creates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        current_window = object()
        app_with_window = SimpleNamespace(current_window=current_window)
        assert await runtime_setup._get_window(app_with_window, "connection", FakeProfile("Default")) is current_window

        created_window = object()

        class WindowAPI:
            @staticmethod
            async def async_create(connection: object, profile_name: str) -> object:
                assert connection == "connection"
                assert profile_name == "Default"
                return created_window

        monkeypatch.setattr(runtime_setup, "Window", WindowAPI)
        app_without_window = SimpleNamespace(current_window=None)
        assert (
            await runtime_setup._get_window(app_without_window, "connection", FakeProfile("Default")) is created_window
        )

    asyncio.run(scenario())


class FakeSession:
    def __init__(self, name: str, profile_name: str = "Default") -> None:
        self.name = name
        self.profile_name = profile_name

    async def async_get_variable(self, variable: str) -> str:
        assert variable == "profileName"
        return self.profile_name

    async def async_set_name(self, name: str) -> None:
        self.name = name


class FakeTab:
    def __init__(self, title: str, session: FakeSession | None) -> None:
        self.title = title
        self.current_session = session

    async def async_get_variable(self, variable: str) -> str:
        assert variable == "title"
        return self.title

    async def async_set_title(self, title: str) -> None:
        self.title = title


class FakeWindow:
    def __init__(self, tabs: list[FakeTab]) -> None:
        self.tabs = tabs
        self.created_profiles: list[str] = []

    async def async_create_tab(self, profile: str) -> FakeTab:
        self.created_profiles.append(profile)
        tab = FakeTab("new title", FakeSession("new session"))
        self.tabs.append(tab)
        return tab


def test_get_tab_with_session_reuses_matching_tagged_tab() -> None:
    async def scenario() -> None:
        profile = FakeProfile("Default")
        session = FakeSession("pyterm-session:Default", profile_name="Default")
        tab = FakeTab("pyterm-session:Default", session)
        window = FakeWindow([tab])

        selected_tab, selected_session = await runtime_setup._get_tab_with_session(window, profile)

        assert selected_tab is tab
        assert selected_session is session
        assert window.created_profiles == []

    asyncio.run(scenario())


def test_get_tab_with_session_creates_and_renames_when_no_match() -> None:
    async def scenario() -> None:
        profile = FakeProfile("Default")
        window = FakeWindow([])

        selected_tab, selected_session = await runtime_setup._get_tab_with_session(window, profile)

        assert window.created_profiles == ["Default"]
        assert selected_tab.title == "pyterm-session:Default"
        assert selected_session.name == "pyterm-session:Default"

    asyncio.run(scenario())


def test_run_iterm_setup_sets_debug_level_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = object()
        levels: list[tuple[str, bool]] = []

        async def setup(connection_instance: object, **kwargs: Any) -> object:
            assert connection_instance == "connection"
            assert kwargs == {"debug": False}
            return state

        def set_level(level: str, *, propagate: bool) -> None:
            levels.append((level, propagate))

        monkeypatch.setenv("ITERM_DEBUG", "true")
        monkeypatch.setattr(runtime_setup, "_setup_iterm", setup)
        monkeypatch.setattr(runtime_setup.log.parent, "set_level", set_level)

        assert await runtime_setup.run_iterm_setup("connection", debug=False) is state
        assert levels == [("DEBUG", True)]

    asyncio.run(scenario())


def test_setup_iterm_delegates_to_api_create_iterm_state(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = object()
        calls: list[tuple[object, dict[str, object]]] = []

        async def create_iterm_state(connection_instance: object, **kwargs: object) -> object:
            calls.append((connection_instance, kwargs))
            return state

        monkeypatch.setattr(api_module, "create_iterm_state", create_iterm_state)

        assert (
            await runtime_setup._setup_iterm(
                "connection", dedicated_profile_name="pyterm-mcp", new_tab=True, debug=True
            )
            is state
        )
        assert calls == [
            (
                "connection",
                {"profile_name": "pyterm-mcp", "dedicated_profile_name": "pyterm-mcp", "new_tab": True, "debug": True},
            )
        ]

    asyncio.run(scenario())
