from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

import pytest

from iterm2_api_wrapper.api import it2api as api_module
from iterm2_api_wrapper.api.it2api import contains_matching_term, create_iterm_state, iTermAPI
from iterm2_api_wrapper.errors import ProfileNotFoundError, TabNotFoundError


if TYPE_CHECKING:
    from iterm2_api_wrapper.api.it2app import App
    from iterm2_api_wrapper.api.it2connection import Connection
    from iterm2_api_wrapper.api.it2profile import PartialProfile, Profile
    from iterm2_api_wrapper.api.it2session import Session
    from iterm2_api_wrapper.api.it2tab import Tab
    from iterm2_api_wrapper.api.it2window import Window
else:
    App = Connection = PartialProfile = Profile = Session = Tab = Window = object


TProfile = TypeVar("TProfile", bound=Profile, covariant=True)
TApp = TypeVar("TApp", bound=App, covariant=True)


class _FakeProfile(Protocol[TProfile]):
    name: str
    guid: str
    original_guid: str | None = None


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

    async def async_set_buried(self, buried: bool) -> None:
        self.buried = buried

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


class _FakeApp(Protocol[TApp]): ...


class FakeApp(_FakeApp):
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


def as_connection(connection: object) -> Connection:
    return cast(Connection, connection)


def as_app(app: FakeApp) -> App:
    return cast(App, app)


def as_profile(profile: FakeProfile) -> Profile | PartialProfile:
    return cast(Profile | PartialProfile, profile)


def as_window(window: FakeWindow | None) -> Window | None:
    return cast(Window | None, window)


def as_tab(tab: FakeTab | None) -> Tab | None:
    return cast(Tab | None, tab)


def as_session(session: FakeSession | None) -> Session | None:
    return cast(Session | None, session)


def make_api(profile: FakeProfile, windows: list[FakeWindow]) -> iTermAPI:
    typed_profile = as_profile(profile)
    api = object.__new__(iTermAPI)
    api.loop = None  # type: ignore[assignment]
    api.new_tab = False
    api.debug = False
    api.profile_name = profile.name
    api.extra_id = None
    api._connection = None
    api._app = as_app(FakeApp(windows))
    api.profile = typed_profile
    api.window = None
    api.tab = None
    api.session = None
    api._profile_cache = {profile.name: typed_profile}
    api.service_name = "iterm-api"
    api.activate = False
    return api


def test_profile_guid_prefers_session_original_guid() -> None:
    session_local = FakeProfile(name="pyterm-mcp", guid="SESSION-LOCAL-GUID", original_guid="CONFIGURED-GUID")

    assert iTermAPI._profile_guid(as_profile(session_local)) == "CONFIGURED-GUID"


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
        assert api.activate is True

    asyncio.run(scenario())


def test_sync_constructor_populates_from_api_owned_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = as_connection(SimpleNamespace(loop=None, iterm2_protocol_version=(1, 14)))
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

    async def bootstrap_runtime() -> None:
        return None

    async def ensure_app_running(*, activate: bool) -> None:
        activated.append(activate)

    monkeypatch.setattr(iTermAPI, "_iTermAPI__connection", None)
    monkeypatch.setattr(iTermAPI, "_iTermAPI__app", None)
    monkeypatch.setattr(api_module, "bootstrap_iterm2_runtime", bootstrap_runtime)
    monkeypatch.setattr("iterm2_api_wrapper.pyobjc_adapter.async_ensure_iterm_app_running", ensure_app_running)
    monkeypatch.setattr(iTermAPI, "_check_api_enabled", staticmethod(lambda: True))
    monkeypatch.setattr(
        iTermAPI, "_configure_logging", lambda api: configured.append((api.profile_name, api.new_tab, api.debug))
    )
    monkeypatch.setattr(iTermAPI, "get_app", get_app)
    monkeypatch.setattr(iTermAPI, "get_profile", get_profile)

    async def create_tab(
        api: iTermAPI,
        target_window: FakeWindow | None = None,
        target_profile: FakeProfile | None = None,
        *,
        with_session: bool = False,
        timeout: float = 30.0,
    ) -> FakeTab | tuple[FakeTab, FakeSession]:
        del timeout
        assert target_window is not None
        assert target_profile is not None
        created_tab = await target_window.async_create_tab(profile=target_profile.name)
        if with_session:
            assert created_tab.current_session is not None
            return created_tab, created_tab.current_session
        return created_tab

    monkeypatch.setattr(iTermAPI, "create_tab", create_tab)
    # monkeypatch.setattr(conn, "iterm2_protocol_version=(1, 15)", property(fget=lambda _self: (1, 15)))

    api = iTermAPI(profile_name="pyterm-mcp", connection_instance=conn, new_tab=True, debug=True)

    assert not hasattr(api_module, "run_iterm_setup")
    assert activated == [True]
    assert configured == [("pyterm-mcp", True, True)]
    assert get_profile_calls == [None]
    assert get_app_calls >= 1
    assert api.connection is conn
    assert api.app is app
    assert api.profile is profile
    assert api.window is window
    assert api.tab is window.tabs[-1]
    assert api.tab is not None
    assert api.session is api.tab.current_session
    assert api.profile_name == "pyterm-mcp"
    assert window.created_profiles == ["pyterm-mcp"]
    assert window.tabs[-1].title == "iterm-api:pyterm-mcp"
    assert api.session is not None
    assert api.session.name == "iterm-api:pyterm-mcp"


def test_create_iterm_state_builds_state_from_api_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        calls: list[dict[str, object]] = []
        conn = as_connection(SimpleNamespace(loop=None))
        profile = FakeProfile(name="pyterm-mcp", guid="CONFIGURED-GUID")
        session = FakeSession("target", "session-1", profile)
        tab = FakeTab("tab-1", [session], title="tab-1")
        window = FakeWindow("window-1", [tab])
        app = FakeApp([window])

        async def async_create(**kwargs: object) -> iTermAPI:
            calls.append(kwargs)
            api = make_api(profile, [window])
            api._connection = conn
            api._app = as_app(app)
            api.window = as_window(window)
            api.tab = as_tab(tab)
            api.session = as_session(session)
            return api

        monkeypatch.setattr(iTermAPI, "async_create", staticmethod(async_create))

        state = await create_iterm_state(
            conn, dedicated_profile_name="fallback-profile", new_tab=True, debug=True, activate=False
        )
        assert state.connection is conn
        assert state.app is app
        assert state.window is window
        assert state.tab is tab
        assert state.session is session
        assert state.profile is profile
        assert calls == [
            {
                "connection_instance": conn,
                "profile_name": "fallback-profile",
                "service_name": None,
                "extra_id": None,
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
        assert api.window is None
        assert api.tab is None
        assert api.session is None

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
        api.window = as_window(default_window)
        api.tab = as_tab(default_tab)
        api.session = as_session(default_session)
        api._profile_cache[work_profile.name] = as_profile(work_profile)

        selected_window = await api.get_window(profile_name="Work")

        assert selected_window is work_window
        assert api.window is default_window
        assert api.tab is default_tab
        assert api.session is default_session
        assert api.profile is default_profile
        assert api.profile_name == "Default"

    asyncio.run(scenario())


def test_get_tab_uses_live_session_profile_identity_without_creating() -> None:
    async def scenario() -> None:
        target = FakeProfile(name="pyterm-mcp", guid="CONFIGURED-GUID")
        unrelated_same_name = FakeProfile(name="pyterm-mcp", guid="OTHER-GUID")
        unrelated_session = FakeSession("wrong", "session-1", unrelated_same_name)
        wrong_tab = FakeTab("tab-1", [unrelated_session])
        window = FakeWindow("window-1", [wrong_tab])
        api = make_api(target, [window])
        api.window = as_window(window)

        with pytest.raises(TabNotFoundError):
            await api.get_tab()

        assert window.created_profiles == []
        assert api.tab is None
        assert api.session is None

    asyncio.run(scenario())


def test_get_session_by_id_disinters_without_updating_context() -> None:
    async def scenario() -> None:
        target = FakeProfile(name="pyterm-mcp", guid="CONFIGURED-GUID")
        session = FakeSession("target", "session-1", target, buried=True)
        tab = FakeTab("tab-1", [session])
        window = FakeWindow("window-1", [tab])
        api = make_api(target, [window])

        assert await api.get_session(session_id="session-1") is session
        assert session.buried is False
        assert api.window is None
        assert api.tab is None
        assert api.session is None

    asyncio.run(scenario())


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------


def test_contains_matching_term_detects_any_match() -> None:
    pattern = re.compile(re.escape("iterm-api:pyterm-mcp"))

    assert contains_matching_term(pattern, "other", "iterm-api:pyterm-mcp tab") is True
    assert contains_matching_term(pattern, "nope", "nothing") is False


def test_profile_guid_handles_dict_object_and_none() -> None:
    assert iTermAPI._profile_guid(None) is None
    assert iTermAPI._profile_guid({"guid": "G1"}) == "G1"
    assert iTermAPI._profile_guid({"original_guid": "O1", "guid": "G1"}) == "O1"
    assert iTermAPI._profile_guid(as_profile(FakeProfile(name="x", guid="G2"))) == "G2"


def test_profile_guid_falls_back_to_all_properties() -> None:
    class PropsOnlyProfile:
        def __init__(self) -> None:
            self.name = "props"
            self.all_properties = {"Guid": "FROM-PROPS"}

    assert iTermAPI._profile_guid(cast("Profile", PropsOnlyProfile())) == "FROM-PROPS"


def test_profile_name_handles_dict_object_and_none() -> None:
    assert iTermAPI._profile_name(None) is None
    assert iTermAPI._profile_name({"name": "DictName"}) == "DictName"
    assert iTermAPI._profile_name(as_profile(FakeProfile(name="ObjName", guid="g"))) == "ObjName"


def test_profiles_match_compares_resolved_guids() -> None:
    a = FakeProfile(name="A", guid="SAME")
    b = FakeProfile(name="B", guid="SAME")
    c = FakeProfile(name="C", guid="DIFFERENT")

    assert iTermAPI._profiles_match(as_profile(a), as_profile(b)) is True
    assert iTermAPI._profiles_match(as_profile(a), as_profile(c)) is False


def test_build_tag_name_includes_service_and_optional_extra_id() -> None:
    api = make_api(FakeProfile(name="pyterm-mcp", guid="G"), [])
    profile = as_profile(FakeProfile(name="pyterm-mcp", guid="G"))

    assert api._build_tag_name(profile) == "iterm-api:pyterm-mcp"

    api.extra_id = "session-a"
    assert api._build_tag_name(profile) == "iterm-api:pyterm-mcp:session-a"
    assert api._build_tag_regex(profile).search("iterm-api:pyterm-mcp:session-a tab")


def test_current_context_matches_respects_require_flags() -> None:
    profile = FakeProfile(name="pyterm-mcp", guid="GUID")
    api = make_api(profile, [])

    typed_profile = as_profile(profile)

    # Matching profile, no required handles set.
    assert api._current_context_matches(typed_profile) is True

    # Requiring window/tab/session that are unset returns False.
    assert api._current_context_matches(typed_profile, require_window=True) is False
    assert api._current_context_matches(typed_profile, require_tab=True) is False
    assert api._current_context_matches(typed_profile, require_session=True) is False

    # Mismatched profile returns False even when handles are present.
    other = as_profile(FakeProfile(name="other", guid="OTHER"))
    assert api._current_context_matches(other) is False


def test_check_api_enabled_reads_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        recorded.append(cmd)
        return SimpleNamespace(returncode=0, stdout="1\n")

    monkeypatch.setattr(api_module.subprocess, "run", fake_run)
    assert iTermAPI._check_api_enabled() is True
    assert recorded[0][:2] == ["defaults", "read"]

    monkeypatch.setattr(api_module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="0"))
    assert iTermAPI._check_api_enabled() is False

    def raises(*a: object, **k: object) -> SimpleNamespace:
        raise OSError("boom")

    monkeypatch.setattr(api_module.subprocess, "run", raises)
    assert iTermAPI._check_api_enabled() is False


def test_enable_api_writes_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_module.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    assert iTermAPI._enable_api() is True

    def raises(*a: object, **k: object) -> SimpleNamespace:
        raise OSError("boom")

    monkeypatch.setattr(api_module.subprocess, "run", raises)
    assert iTermAPI._enable_api() is False


def test_iter_sessions_walks_all_windows_tabs_sessions() -> None:
    async def scenario() -> None:
        profile = FakeProfile(name="p", guid="G")
        sessions = [FakeSession(f"s{i}", f"sid-{i}", profile) for i in range(3)]
        tab_a = FakeTab("tab-a", sessions[:2])
        tab_b = FakeTab("tab-b", sessions[2:])
        window = FakeWindow("window-1", [tab_a, tab_b])
        api = make_api(profile, [window])

        collected = [session.session_id async for _, _, session in api._iter_sessions()]
        assert collected == ["sid-0", "sid-1", "sid-2"]

        scoped = [session.session_id async for _, _, session in api._iter_sessions(as_window(window))]
        assert scoped == ["sid-0", "sid-1", "sid-2"]

    asyncio.run(scenario())


def test_version_property_formats_protocol_tuple() -> None:
    api = make_api(FakeProfile(name="p", guid="G"), [])
    api._connection = as_connection(SimpleNamespace(iterm2_protocol_version=(3, 5)))

    assert api.version == "3.5"


def test_get_profile_returns_current_then_cached() -> None:
    async def scenario() -> None:
        profile = FakeProfile(name="pyterm-mcp", guid="G")
        api = make_api(profile, [])

        # target_is_current short-circuits to the live profile.
        assert await api.get_profile() is api.profile

        cached = as_profile(FakeProfile(name="Work", guid="WORK"))
        api._profile_cache["Work"] = cached
        assert await api.get_profile(target_profile_name="Work") is cached

    asyncio.run(scenario())


def test_get_profile_fetches_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        api = make_api(FakeProfile(name="seed", guid="G"), [])
        api.profile = None
        api.profile_name = None
        api._profile_cache = {}

        default_profile = FakeProfile(name="Default", guid="DEF")

        async def async_get_default(connection: object) -> FakeProfile:
            return default_profile

        monkeypatch.setattr(api_module.Profile, "async_get_default", staticmethod(async_get_default))

        result = await api.get_profile()
        assert result is default_profile
        assert api._profile_cache["Default"] is default_profile

    asyncio.run(scenario())


def test_get_profile_raises_when_named_profile_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        api = make_api(FakeProfile(name="seed", guid="G"), [])
        api.profile = None
        api.profile_name = None
        api._profile_cache = {}

        async def async_get(connection: object) -> list[FakeProfile]:
            return [FakeProfile(name="Default", guid="DEF")]

        monkeypatch.setattr(api_module.Profile, "async_get", staticmethod(async_get))

        with pytest.raises(ProfileNotFoundError):
            await api.get_profile(target_profile_name="Nonexistent")

    asyncio.run(scenario())


def test_get_window_by_window_id_uses_app_lookup() -> None:
    async def scenario() -> None:
        profile = FakeProfile(name="pyterm-mcp", guid="GUID")
        session = FakeSession("s", "sid", profile)
        tab = FakeTab("tab-1", [session])
        window = FakeWindow("window-1", [tab])
        api = make_api(profile, [window])

        assert await api.get_window(window_id="window-1") is window

    asyncio.run(scenario())


def test_json_serializes_context_snapshot() -> None:
    profile = FakeProfile(name="pyterm-mcp", guid="GUID")
    api = make_api(profile, [])
    api._connection = as_connection(SimpleNamespace(iterm2_protocol_version=(1, 5)))
    api._app = as_app(
        cast(
            FakeApp,
            SimpleNamespace(windows=[object(), object()], broadcast_domains=[], buried_sessions=[object()]),
        )
    )
    api.window = as_window(cast(FakeWindow, SimpleNamespace(tabs=[object()], window_id="window-1", window_number=1)))
    api.tab = as_tab(cast(FakeTab, SimpleNamespace(tab_id="tab-1", all_sessions=[object()], active_session_id="sid")))
    api.session = as_session(cast(FakeSession, SimpleNamespace(session_id="sid", name="iterm-api:pyterm-mcp")))

    payload = json.loads(api.json())

    assert payload["profile"] == {"name": "pyterm-mcp", "guid": "GUID"}
    assert payload["iterm2_protocol_version"] == "1.5"
    assert payload["app"] == {"windows": 2, "broadcast_domains": 0, "buried_sessions": 1}
    assert payload["window"]["id"] == "window-1"
    assert payload["tab"]["sessions"] == 1
    assert payload["session"] == {"id": "sid", "name": "iterm-api:pyterm-mcp"}


def test_create_window_delegates_to_window_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        api = make_api(FakeProfile(name="p", guid="G"), [])
        api._connection = as_connection(SimpleNamespace())
        created = object()
        calls: list[tuple[object, str | None, str | None]] = []

        async def async_create(connection: object, profile_name: str | None, command: str | None) -> object:
            calls.append((connection, profile_name, command))
            return created

        monkeypatch.setattr(api_module.Window, "async_create", staticmethod(async_create))

        result = await api.create_window(profile_name="Work", command="ls")
        assert result is created
        assert calls == [(api._connection, "Work", "ls")]

    asyncio.run(scenario())
