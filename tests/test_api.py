from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from iterm2_api_wrapper.api import it2api as api_module
from iterm2_api_wrapper.api.it2api import create_iterm_state, iTermAPI


@dataclass
class FakeProfile:
    name: str
    guid: str
    original_guid: str | None = None


class FakeSession:
    def __init__(self, name: str, session_id: str, profile: FakeProfile, *, buried: bool = False) -> None:
        self.name = name
        self.session_id = session_id
        self.profile = profile
        self.buried = buried
        self.activation_args: tuple[bool, bool] | None = None

    async def async_get_profile(self) -> FakeProfile:
        return self.profile

    async def async_get_variable(self, variable: str) -> str | None:
        if variable == "profileName":
            return self.profile.name
        return None

    async def async_set_name(self, name: str) -> None:
        self.name = name

    async def async_activate(self, select_tab: bool, order_window_front: bool) -> None:
        self.activation_args = (select_tab, order_window_front)
        self.buried = False


class FakeTab:
    def __init__(self, tab_id: str, sessions: list[FakeSession], title: str | None = None) -> None:
        self.tab_id = tab_id
        self.all_sessions = sessions
        self.title = title or tab_id

    @property
    def current_session(self) -> FakeSession | None:
        return self.all_sessions[0] if self.all_sessions else None

    async def async_get_variable(self, variable: str) -> str | None:
        if variable == "currentSession.profileName" and self.current_session:
            return self.current_session.profile.name
        if variable == "title":
            return self.title
        return None

    async def async_set_title(self, title: str) -> None:
        self.title = title


class FakeWindow:
    def __init__(self, window_id: str, tabs: list[FakeTab], *, is_hotkey_window: bool = False) -> None:
        self.window_id = window_id
        self.tabs = tabs
        self.created_profiles: list[str] = []
        self.is_hotkey_window = is_hotkey_window

    async def async_create_tab(self, profile: str) -> FakeTab:
        self.created_profiles.append(profile)
        created_profile = FakeProfile(name=profile, guid=f"created-{profile}")
        created_session = FakeSession(
            name=f"created-{profile}", session_id=f"created-{profile}", profile=created_profile
        )
        created_tab = FakeTab(tab_id=f"created-{profile}", sessions=[created_session])
        self.tabs.append(created_tab)
        return created_tab

    async def async_get_variable(self, variable: str) -> bool | None:
        if variable == "isHotkeyWindow":
            return self.is_hotkey_window
        return None


class FakeApp:
    def __init__(self, windows: list[FakeWindow]) -> None:
        self.windows = windows
        self.current_window = windows[0] if windows else None
        self.app_active = True

    def get_session_by_id(self, session_id: str) -> FakeSession | None:
        for window in self.windows:
            for tab in window.tabs:
                for session in tab.all_sessions:
                    if session.session_id == session_id:
                        return session
        return None

    def get_tab_by_id(self, tab_id: str) -> FakeTab | None:
        for window in self.windows:
            for tab in window.tabs:
                if tab.tab_id == tab_id:
                    return tab
        return None

    def get_window_by_id(self, window_id: str) -> FakeWindow | None:
        for window in self.windows:
            if window.window_id == window_id:
                return window
        return None

    def get_window_and_tab_for_session(self, target_session: FakeSession) -> tuple[FakeWindow | None, FakeTab | None]:
        for window in self.windows:
            for tab in window.tabs:
                if target_session in tab.all_sessions:
                    return window, tab
        return None, None

    async def tab_delegate_get_window_by_id(self, window_id: str) -> FakeWindow | None:
        return self.get_window_by_id(window_id)

    async def window_delegate_get_tab_by_id(self, tab_id: str) -> FakeTab | None:
        return self.get_tab_by_id(tab_id)


def make_api(profile: FakeProfile, windows: list[FakeWindow]) -> iTermAPI:
    api = object.__new__(iTermAPI)
    api.loop = None
    api.new_tab = False
    api.debug = None
    api.profile_name = profile.name
    api.conn = None
    api.app = FakeApp(windows)
    api.profile = profile
    api.state = None
    api.window = None
    api.tab = None
    api.session = None
    api._profile_cache = {profile.name: profile}
    api._context_profile = profile
    return api


def test_profile_guid_prefers_session_original_guid() -> None:
    session_local = FakeProfile(name="pyterm-mcp", guid="SESSION-LOCAL-GUID", original_guid="CONFIGURED-GUID")

    assert iTermAPI._profile_guid(session_local) == "CONFIGURED-GUID"


def test_sync_constructor_rejects_running_event_loop() -> None:
    async def scenario() -> None:
        with pytest.raises(RuntimeError, match=r"await iTermAPI\.async_create"):
            iTermAPI(profile_name="pyterm-mcp")

    asyncio.run(scenario())


def test_async_create_initializes_on_running_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        initialized: list[iTermAPI] = []

        async def initialize(api: iTermAPI) -> None:
            initialized.append(api)

        monkeypatch.setattr(iTermAPI, "_initialize", initialize)

        api = await iTermAPI.async_create(profile_name="pyterm-mcp")

        assert initialized == [api]
        assert api.profile_name == "pyterm-mcp"
        assert api.loop is asyncio.get_running_loop()
        assert api._owns_loop is False

    asyncio.run(scenario())


def test_sync_create_populates_from_api_owned_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = SimpleNamespace(loop=None)
    profile = FakeProfile(name="pyterm-mcp", guid="CONFIGURED-GUID")
    session = FakeSession("target", "session-1", profile)
    tab = FakeTab("tab-1", [session], title="tab-1")
    window = FakeWindow("window-1", [tab])
    app = FakeApp([window])
    activated: list[bool] = []
    configured: list[tuple[str | None, bool, bool | None]] = []
    get_app_calls = 0
    get_profile_calls: list[str | None] = []

    async def get_app(api: iTermAPI) -> FakeApp:
        nonlocal get_app_calls
        get_app_calls += 1
        return app

    async def get_profile(api: iTermAPI, profile_name: str | None = None) -> FakeProfile:
        get_profile_calls.append(profile_name)
        return profile

    monkeypatch.setattr(iTermAPI, "_iTermAPI__connection", None)
    monkeypatch.setattr(iTermAPI, "_iTermAPI__app", None)
    monkeypatch.setattr(api_module, "activate_iterm_app", lambda: activated.append(True))
    monkeypatch.setattr(iTermAPI, "_check_api_enabled", staticmethod(lambda: True))
    monkeypatch.setattr(
        iTermAPI, "_configure_logging", lambda api: configured.append((api.profile_name, api.new_tab, api.debug))
    )
    monkeypatch.setattr(iTermAPI, "get_app", get_app)
    monkeypatch.setattr(iTermAPI, "get_profile", get_profile)

    api = iTermAPI.create(profile_name="pyterm-mcp", connection_instance=conn, new_tab=True, debug=True)

    assert not hasattr(api_module, "run_iterm_setup")
    assert activated == [True]
    assert configured == [("pyterm-mcp", True, True)]
    assert get_profile_calls == [None]
    assert get_app_calls >= 1
    assert api.state is not None
    assert api.conn is conn
    assert api.app is app
    assert api.profile is profile
    assert api.window is window
    assert api.tab is window.tabs[-1]
    assert api.session is api.tab.current_session
    assert api.profile_name == "pyterm-mcp"
    assert api._context_profile is profile
    assert api.state.connection is conn
    assert api.state.app is app
    assert api.state.profile is profile
    assert api.state.window is window
    assert api.state.tab is api.tab
    assert api.state.session is api.session
    assert api.state.is_hotkey_window is False
    assert window.created_profiles == ["pyterm-mcp"]
    assert api.tab.title == "pyterm-session:pyterm-mcp"
    assert api.session is not None
    assert api.session.name == "pyterm-session:pyterm-mcp"


def test_create_iterm_state_unwraps_api_owned_state(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = object()
        calls: list[dict[str, object]] = []

        async def async_create(**kwargs: object) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(state=state)

        monkeypatch.setattr(iTermAPI, "async_create", staticmethod(async_create))

        conn = SimpleNamespace(loop=None)
        assert (
            await create_iterm_state(
                conn,
                profile_name="pyterm-mcp",
                dedicated_profile_name="fallback-profile",
                new_tab=True,
                debug=True,
                activate=False,
            )
            is state
        )
        assert calls == [
            {
                "connection_instance": conn,
                "profile_name": "pyterm-mcp",
                "dedicated_profile_name": "fallback-profile",
                "new_tab": True,
                "debug": True,
                "activate": False,
            }
        ]

    asyncio.run(scenario())


def test_get_window_matches_session_local_profile_original_guid() -> None:
    async def scenario() -> None:
        target = FakeProfile(name="pyterm-mcp", guid="CONFIGURED-GUID")
        session_profile = FakeProfile(name="pyterm-mcp", guid="SESSION-LOCAL-GUID", original_guid="CONFIGURED-GUID")
        session = FakeSession("target", "session-1", session_profile)
        tab = FakeTab("tab-1", [session])
        window = FakeWindow("window-1", [tab])
        api = make_api(target, [window])

        assert await api.get_window() is window
        assert api.tab is tab
        assert api.session is session

    asyncio.run(scenario())


def test_get_window_local_profile_override_does_not_reuse_stale_context() -> None:
    async def scenario() -> None:
        default_profile = FakeProfile(name="Default", guid="DEFAULT-GUID")
        work_profile = FakeProfile(name="Work", guid="WORK-GUID")

        default_session = FakeSession("default", "default-session", default_profile)
        default_tab = FakeTab("default-tab", [default_session])
        default_window = FakeWindow("default-window", [default_tab])

        work_session = FakeSession("work", "work-session", work_profile)
        work_tab = FakeTab("work-tab", [work_session])
        work_window = FakeWindow("work-window", [work_tab])

        api = make_api(default_profile, [default_window, work_window])
        api.window = default_window
        api.tab = default_tab
        api.session = default_session
        api._profile_cache[work_profile.name] = work_profile

        selected_window = await api.get_window(profile_name="Work")

        assert selected_window is work_window
        assert api.window is work_window
        assert api.tab is work_tab
        assert api.session is work_session
        assert api.profile is work_profile
        assert api.profile_name == "Work"
        assert api._context_profile is work_profile

    asyncio.run(scenario())


def test_get_tab_uses_live_session_profile_identity_before_profile_name_cache() -> None:
    async def scenario() -> None:
        target = FakeProfile(name="pyterm-mcp", guid="CONFIGURED-GUID")
        unrelated_same_name = FakeProfile(name="pyterm-mcp", guid="OTHER-GUID")
        unrelated_session = FakeSession("wrong", "session-1", unrelated_same_name)
        wrong_tab = FakeTab("tab-1", [unrelated_session])
        window = FakeWindow("window-1", [wrong_tab])
        api = make_api(target, [window])
        api.window = window

        selected_tab = await api.get_tab()

        assert selected_tab is not wrong_tab
        assert selected_tab is window.tabs[-1]
        assert window.created_profiles == ["pyterm-mcp"]

    asyncio.run(scenario())


def test_get_session_by_id_updates_context_and_disinters() -> None:
    async def scenario() -> None:
        target = FakeProfile(name="pyterm-mcp", guid="CONFIGURED-GUID")
        session = FakeSession("target", "session-1", target, buried=True)
        tab = FakeTab("tab-1", [session])
        window = FakeWindow("window-1", [tab])
        api = make_api(target, [window])

        assert await api.get_session(session_id="session-1") is session
        assert session.activation_args == (False, False)
        assert api.window is window
        assert api.tab is tab
        assert api.session is session

    asyncio.run(scenario())
