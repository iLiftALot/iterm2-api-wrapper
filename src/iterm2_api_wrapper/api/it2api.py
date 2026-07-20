from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from collections.abc import AsyncGenerator
from types import NoneType
from typing import TYPE_CHECKING, Literal, cast, overload

from async_timeout import timeout as _timeout

from .._logging import PrettyLog
from ..errors import ProfileNotFoundError, SessionNotFoundError, TabNotFoundError, WindowNotFoundError
from .it2app import App, async_get_app
from .it2connection import Connection
from .it2lifecycle import NewSessionMonitor
from .it2profile import LocalWriteOnlyProfile, Profile, ProfileProperties
from .it2prompt import PromptMonitor
from .it2window import Window


if sys.version_info >= (3, 12):
    from typing import Unpack
else:
    from typing_extensions import Unpack

if TYPE_CHECKING:
    from ..state import iTermState
    from ..typings import iTermStateSetupKwargs
    from .it2lifecycle import NewSessionMonitor
    from .it2profile import PartialProfile
    from .it2session import Session
    from .it2tab import Tab


log = PrettyLog.get_logger(__name__)


def contains_matching_term(regex_pattern: re.Pattern[str], *terms: str) -> bool:
    matches = list(filter(bool, [regex_pattern.search(term) for term in terms]))
    return len(matches) > 0


class iTermAPI:
    __connection: Connection | None = None
    __app: App | None = None

    def __init__(
        self,
        profile_name: str | None = None,
        service_name: str | None = None,
        extra_id: str | None = None,
        *,
        connection_instance: Connection | None = None,
        auto_initialize: bool = True,
        new_tab: bool = False,
        debug: bool | None = None,
        activate: bool = True,
        profile_properties: ProfileProperties | None = None,
    ) -> None:
        self._connection: Connection | None = connection_instance
        self._app: App | None = None
        self._profile_cache: dict[str, Profile | PartialProfile] = {}

        self.profile_name = profile_name or os.getenv("IT2_DEFAULT_PROFILE", None)
        self.service_name = service_name or "iterm-api"
        self.extra_id = extra_id
        self.new_tab = new_tab
        self.debug = debug or os.getenv("IT2_DEBUG", "false").strip().lower() in {"1", "true"}
        self.activate = activate
        self.profile_properties = profile_properties

        self.window: Window | None = None
        self.tab: Tab | None = None
        self.session: Session | None = None
        self._profile: Profile | PartialProfile | None = None

        if connection_instance is not None:
            type(self).__connection = connection_instance

        if not auto_initialize:
            return

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None:
            raise RuntimeError(
                "iTermAPI cannot be synchronously initialized while an event loop is running. "
                "Use 'await iTermAPI.async_create(...)' inside async code."
            )

        self.loop = asyncio.new_event_loop()
        self.loop.run_until_complete(self._initialize())

    @property
    def app(self) -> App:
        if not self._app:
            if not self.__app:
                raise RuntimeError("iTermAPI._app not set.")
            self._app = self.__app
        return self._app

    @property
    def connection(self) -> Connection:
        if not self._connection:
            if not self.__connection:
                raise RuntimeError("iTermAPI._connection not set.")
            self._connection = self.__connection
        return self._connection

    @classmethod
    async def async_create(
        cls,
        profile_name: str | None = None,
        service_name: str | None = None,
        extra_id: str | None = None,
        *,
        connection_instance: Connection | None = None,
        new_tab: bool = False,
        debug: bool | None = None,
        activate: bool = True,
        profile_properties: ProfileProperties | None = None,
    ) -> iTermAPI:
        api = cls(
            profile_name=profile_name,
            service_name=service_name,
            extra_id=extra_id,
            connection_instance=connection_instance,
            auto_initialize=False,
            new_tab=new_tab,
            debug=debug,
            activate=activate,
            profile_properties=profile_properties,
        )
        api.loop = asyncio.get_running_loop()
        await api._initialize()
        return api

    async def _initialize(self) -> None:
        self._configure_logging()

        from .. import validate_iterm2_runtime
        from ..pyobjc_adapter import async_ensure_iterm_app_running

        await async_ensure_iterm_app_running(activate=self.activate)

        if not self._check_api_enabled():
            raise RuntimeError("iTerm2 Python API is not enabled. Enable it in iTerm2 Preferences > General > Magic.")

        self._connection = await self.get_connection()
        validate_iterm2_runtime(self._connection)

        self._app = await self.get_app()
        self.profile = await self.get_profile()

        selected_window: Window
        selected_tab: Tab
        selected_session: Session

        if not self.new_tab:
            tagged_context = await self._find_tagged_context(self.profile)
        else:
            tagged_context = None

        if tagged_context is not None:
            selected_window, selected_tab, selected_session = tagged_context
        else:
            if self.new_tab:
                selected_window = (
                    self.app.current_window
                    or self.app.windows[0]
                    or await self.create_window(profile_name=self.profile_name)
                )
                if selected_window is None:
                    raise WindowNotFoundError(f"{self.profile_name} ({self._profile_guid(self.profile)})")
            else:
                selected_window = await self.get_window()
            selected_tab, selected_session = await self._get_tagged_tab_with_session(
                selected_window, self.profile, new_tab=self.new_tab
            )

        self.window, self.tab, self.session = selected_window, selected_tab, selected_session

    async def get_connection(self) -> Connection:
        if self._connection is None:
            if type(self).__connection is None:
                type(self).__connection = await Connection.async_create()
            self._connection = type(self).__connection
        return cast(Connection, self._connection)

    async def get_app(self) -> App:
        if self._app is None:
            if type(self).__app is None:
                conn = await self.get_connection()
                type(self).__app = await async_get_app(conn, create_if_needed=True)
            self._app = type(self).__app
        return cast(App, self._app)

    async def get_profile(self, *, target_profile_name: str | None = None) -> Profile | PartialProfile:
        target_profile_name = target_profile_name or self.profile_name or self._profile_name(self._profile)
        target_is_current = self._profile is not None and (
            target_profile_name is None or target_profile_name == self._profile.name
        )
        target_in_cache = target_profile_name in self._profile_cache

        if target_is_current:
            return cast(Profile, self.profile)

        if target_in_cache:
            profile = self._profile_cache[target_profile_name]
            return profile

        conn = await self.get_connection()

        if target_profile_name is None:
            profile = await Profile.async_get_default(conn)
            self._profile_cache[profile.name] = profile
            return profile

        profile_entries: dict[str, Profile] = {p.name: p for p in await Profile.async_get(conn)}
        profile = profile_entries.get(target_profile_name)

        if profile is None:
            raise ProfileNotFoundError(target_profile_name=f"{target_profile_name}", profile_data=profile_entries)

        self._profile_cache[profile.name] = profile
        return profile

    @classmethod
    async def configure_profile(cls, session: Session, properties: ProfileProperties) -> Profile:
        new_profile = LocalWriteOnlyProfile(properties)
        await session.async_set_profile_properties(new_profile)
        return await session.async_get_profile()

    @property
    def profile(self) -> Profile | PartialProfile:
        if self._profile is None:
            raise RuntimeError("iTermAPI.profile is not set.")
        return self._profile

    @profile.setter
    def profile(self, value: Profile | PartialProfile | None) -> None:
        if not value and self._profile is not None:
            self._profile_cache.pop(self._profile.name)
        elif value:
            self._profile_cache[value.name] = value
        self._profile = value
        self.profile_name = value.name if value else None

    @overload
    async def get_window(self, *, window_id: str | None = None) -> Window: ...
    @overload
    async def get_window(self, *, profile_name: str | None = None) -> Window: ...
    @overload
    async def get_window(self, *, tab_id: str | None = None) -> Window: ...
    async def get_window(
        self, *, window_id: str | None = None, profile_name: str | None = None, tab_id: str | None = None
    ) -> Window:
        app = await self.get_app()
        profile = await self.get_profile(target_profile_name=profile_name)
        window: Window | None = None

        async def from_window_id(_window_id: str) -> Window | None:
            if self.window and self.window.window_id == _window_id:
                return self.window

            _window = app.get_window_by_id(_window_id) or await app.tab_delegate_get_window_by_id(_window_id)
            return _window

        async def from_profile() -> Window | None:
            if self.window and self._current_context_matches(profile, require_window=True):
                return self.window

            profile_guid = self._profile_guid(profile)

            async for _window, _, session in self._iter_sessions():
                session_profile = await session.async_get_profile()

                if self._profiles_match(session_profile, profile):
                    log.debug(
                        f"PROFILE FOUND: '{profile.name}' ({profile_guid}) in window "
                        f"'{_window.window_id}' for session '{session.name}' ({session.session_id})"
                    )
                    return _window

                session_profile_guid = self._profile_guid(session_profile)
                log.debug(
                    f"PROFILE SKIPPED: '{self._profile_name(session_profile)}' "
                    f"({session_profile_guid}) != '{profile.name}' ({profile_guid}) "
                    f"from session '{session.name}' ({session.session_id})"
                )

            log.debug(f"No existing window has a session for profile '{profile.name}' ({profile_guid}).")
            return None

        async def from_tab_id(_tab_id: str) -> Window | None:
            _window = app.get_window_for_tab(_tab_id)
            if _window is not None:
                return _window

            for window_obj in app.windows:
                for tab in window_obj.tabs:
                    if _tab_id == tab.tab_id:
                        return window_obj

            return None

        async def from_none() -> Window | None:
            if self.window and (self.profile_name or self.profile):
                _window = await from_profile()
            else:
                _window = app.current_window or app.windows[0] or await self.create_window(profile_name=profile.name)

            return _window

        if window_id:
            window = await from_window_id(window_id)
        elif profile_name:
            window = await from_profile()
        elif tab_id:
            window = await from_tab_id(tab_id)
        else:
            window = await from_none()

        if window is None:
            raise WindowNotFoundError(f"{profile.name} ({self._profile_guid(profile)})")

        return window

    @overload
    async def get_tab(self, *, tab_id: str | None = None) -> Tab: ...
    @overload
    async def get_tab(self, *, profile_name: str | None = None) -> Tab: ...
    @overload
    async def get_tab(self, *, window_id: str | None = None) -> Tab: ...
    async def get_tab(
        self,
        *,
        tab_id: str | None = None,
        profile_name: str | None = None,
        window_id: str | None = None,
        session_id: str | None = None,
    ) -> Tab:
        app = await self.get_app()
        profile = await self.get_profile(target_profile_name=profile_name)
        # TODO: update this if get_window gets updated
        window = await self.get_window(**{"window_id": window_id, "profile_name": profile_name, "tab_id": tab_id})
        tab: Tab | None = None

        async def from_tab_id(_tab_id: str) -> Tab | None:
            if self.tab and self.tab.tab_id == _tab_id:
                return self.tab
            _tab = app.get_tab_by_id(_tab_id) or await app.window_delegate_get_tab_by_id(_tab_id)
            return _tab

        async def from_profile() -> Tab | None:
            if self.tab and self._current_context_matches(profile, require_tab=True):
                return self.tab

            profile_guid = self._profile_guid(profile)

            async for _, _tab, session in self._iter_sessions():
                session_profile = await session.async_get_profile()

                if self._profiles_match(session_profile, profile):
                    log.debug(
                        f"PROFILE FOUND: '{profile.name}' ({profile_guid}) in tab "
                        f"'{_tab.tab_id}' for session '{session.name}' ({session.session_id})"
                    )
                    return _tab

                session_profile_guid = self._profile_guid(session_profile)
                log.debug(
                    f"PROFILE SKIPPED: '{self._profile_name(session_profile)}' "
                    f"({session_profile_guid}) != '{profile.name}' ({profile_guid}) "
                    f"from session '{session.name}' ({session.session_id})"
                )

            log.debug(f"No existing tab has a session for profile '{profile.name}' ({profile_guid}).")
            return None

        async def from_window_id() -> Tab | None:
            tagged_ctx = await self._find_tagged_context(profile, window)
            return tagged_ctx[1] if tagged_ctx else None

        async def from_session_id(_tab_id: str) -> Tab | None:
            session = await self.get_session(session_id=_tab_id)
            _tab = session.tab or app.session_delegate_get_tab(session)
            return _tab

        async def from_none() -> Tab | None:
            if self.profile_name or self.profile:
                _tab = await from_profile()
            else:
                candidate_tab = window.current_tab or (window.tabs[0] if window.tabs else None)
                if candidate_tab is not None and candidate_tab.current_session is not None:
                    candidate_profile = await candidate_tab.current_session.async_get_profile()
                    if self._profiles_match(candidate_profile, profile):
                        return candidate_tab

                _tab = candidate_tab

            return _tab

        if tab_id:
            tab = await from_tab_id(tab_id)
        elif profile_name:
            tab = await from_profile()
        elif window_id:
            tab = await from_window_id()
        elif session_id:
            tab = await from_session_id(session_id)
        else:
            tab = await from_none()

        if tab is None:
            raise TabNotFoundError(f"{profile.name} ({self._profile_guid(profile)})")

        return tab

    @overload
    async def get_session(self, *, session_id: str | None = None) -> Session: ...
    @overload
    async def get_session(self, *, profile_name: str | None = None) -> Session: ...
    @overload
    async def get_session(self, *, tab_id: str | None = None) -> Session: ...
    @overload
    async def get_session(self, *, window_id: str | None = None) -> Session: ...
    async def get_session(
        self,
        *,
        session_id: str | None = None,
        profile_name: str | None = None,
        tab_id: str | None = None,
        window_id: str | None = None,
    ) -> Session:
        app = await self.get_app()
        profile = await self.get_profile(target_profile_name=profile_name)
        tab = await self.get_tab(tab_id=tab_id)
        window = await self.get_window(window_id=window_id)
        session: Session | None = None

        async def from_session_id(_tab_id: str) -> Session | None:
            if self.session and self.session.session_id == _tab_id:
                return self.session

            _session = app.get_session_by_id(_tab_id)
            return _session

        async def from_profile() -> Session | None:
            if self.session and self._current_context_matches(profile, require_tab=True):
                return self.session

            profile_guid = self._profile_guid(profile)

            async for _, _tab, _session in self._iter_sessions():
                session_profile = await _session.async_get_profile()

                if self._profiles_match(session_profile, profile):
                    log.debug(
                        f"PROFILE FOUND: '{profile.name}' ({profile_guid}) in tab "
                        f"'{_tab.tab_id}' for session '{_session.name}' ({_session.session_id})"
                    )
                    return _session

                session_profile_guid = self._profile_guid(session_profile)
                log.debug(
                    f"PROFILE SKIPPED: '{self._profile_name(session_profile)}' "
                    f"({session_profile_guid}) != '{profile.name}' ({profile_guid}) "
                    f"from session '{_session.name}' ({_session.session_id})"
                )

            log.debug(f"No existing session has a session for profile '{profile.name}' ({profile_guid}).")
            return None

        async def from_tab_id() -> Session:
            _session = tab.current_session or tab.all_sessions[0]
            return _session

        async def from_window_id() -> Session | None:
            tagged_ctx = await self._find_tagged_context(profile, window)
            return tagged_ctx[2] if tagged_ctx else None

        async def from_none() -> Session | None:
            if self.session and (self.profile_name or self.profile):
                _session = await from_profile()
            else:
                _session = tab.current_session or tab.all_sessions[0]

            return _session

        if session_id:
            session = await from_session_id(session_id)
        elif profile_name:
            session = await from_profile()
        elif tab_id:
            session = await from_tab_id()
        elif window_id:
            session = await from_window_id()
        else:
            session = await from_none()

        if session is None:
            raise SessionNotFoundError(f"{profile.name} ({self._profile_guid(profile)})")

        if session.buried:
            await session.async_set_buried(False)
            await session.async_activate(select_tab=False, order_window_front=False)

        async def _configure_profile(session: Session) -> None:
            if self.profile_properties is not None:
                log.debug("Configuring custom profile properties:", self.profile_properties)
                self.profile = await self.configure_profile(session, self.profile_properties)
                self.profile_name = self.profile.name
                self._profile_cache[self.profile_name] = self.profile

        await _configure_profile(session)
        return session

    async def create_window(self, *, profile_name: str | None = None, command: str | None = None) -> Window | None:
        connection = await self.get_connection()
        window = await Window.async_create(connection, profile_name, command)
        return window

    @overload
    async def create_tab(
        self,
        window: Window | None = None,
        profile: Profile | PartialProfile | None = None,
        *,
        with_session: Literal[True],
        timeout: float = 10.0,
    ) -> tuple[Tab, Session]: ...
    @overload
    async def create_tab(
        self,
        window: Window | None = None,
        profile: Profile | PartialProfile | None = None,
        *,
        with_session: Literal[False],
        timeout: float = 10.0,
    ) -> Tab: ...
    @overload
    async def create_tab(
        self,
        window: Window | None = None,
        profile: Profile | PartialProfile | None = None,
        *,
        with_session: bool = False,
        timeout: float = 10.0,
    ) -> Tab: ...
    async def create_tab(
        self,
        window: Window | None = None,
        profile: Profile | PartialProfile | None = None,
        *,
        with_session: bool = False,
        timeout: float = 10.0,
    ) -> tuple[Tab, Session] | Tab:
        tab, session = await self._create_tab_get_with_session(window, profile, timeout=timeout)
        if with_session is True:
            return tab, session
        return tab

    async def _create_tab_get_with_session(
        self, window: Window | None = None, profile: Profile | PartialProfile | None = None, *, timeout: float = 10.0
    ) -> tuple[Tab, Session]:
        connection = await self.get_connection()
        window = window or await self.get_window()
        profile = profile or await self.get_profile()

        def session_in_tab(tab: Tab, session_id: str) -> Session | None:
            current_session = tab.current_session

            if current_session and current_session.session_id == session_id:
                return current_session

            for session_obj in tab.all_sessions:
                if session_obj.session_id == session_id:
                    return session_obj

            return None

        def expected_session_id(tab: Tab) -> str | None:
            current_session = tab.current_session

            if current_session is not None:
                return current_session.session_id

            sessions = tab.all_sessions

            if len(sessions) == 1:
                return sessions[0].session_id

            return None

        async def wait_for_created_session_id(monitor: NewSessionMonitor, created_tab: Tab) -> str:
            expected_id = expected_session_id(created_tab)

            async with _timeout(timeout):
                while True:
                    session_id = await monitor.async_get()

                    if expected_id is None or session_id == expected_id:
                        return session_id

                    log.debug(
                        "Ignoring unrelated iTerm2 session creation",
                        {"expected_session_id": expected_id, "received_session_id": session_id},
                    )

        async def wait_for_tab_loaded(session_id: str) -> None:
            """Wait until the session is settled: past the first prompt AND past
            any profile "Initial Text" command, so its COMMAND_START/END events
            can't bleed into the first run_command's monitor."""
            Mode = PromptMonitor.Mode
            modes = [Mode.PROMPT, Mode.COMMAND_START, Mode.COMMAND_END]
            quiescence = 0.6  # quiescence == 'inactivity/dormancy' 😂

            async with PromptMonitor(connection, session_id, modes) as monitor:
                try:
                    event = await asyncio.wait_for(monitor.async_get(include_id=True), timeout=timeout)
                except (asyncio.TimeoutError, TimeoutError):
                    # No marks: profile without working shell integration. The tab
                    # exists; snapshot-based fallback owns it from here.
                    log.debug("New tab produced no prompt marks; treating as loaded", {"session_id": session_id})
                    return

                log.debug(
                    "New iTerm2 tab session is prompt-ready",
                    {
                        "session_id": session_id,
                        "mode": event[0],
                        "working_directory": event[1].working_directory
                        if not isinstance(event[1], (str, int, NoneType))
                        else "",
                        "prompt_id": event[2],
                    },
                )

                if not str(profile.all_properties.get("Initial Text") or "").strip():
                    return

                # Drain Initial Text / startup activity until quiet.
                with log.scoped_context(start_event_drain="Draining session-start command output..."):
                    while True:
                        try:
                            event = await asyncio.wait_for(monitor.async_get(include_id=True), timeout=quiescence)
                            log.debug({"mode": event[0], "command": event[1], "prompt_id": event[2]})
                        except (asyncio.TimeoutError, TimeoutError):
                            return

        async with NewSessionMonitor(connection) as monitor:
            created_tab = await window.async_create_tab(profile=profile.name)
            if created_tab is None:
                raise RuntimeError(f"Unable to create a new tab with profile '{profile.name}'.")

            session_id = await wait_for_created_session_id(monitor, created_tab)

        await wait_for_tab_loaded(session_id)
        app = await self.get_app()
        session_obj = session_in_tab(created_tab, session_id) or app.get_session_by_id(session_id)

        if session_obj is None:
            raise RuntimeError(f"New iTerm2 tab loaded, but session '{session_id}' could not be resolved.")

        return created_tab, session_obj

    def _configure_logging(self) -> None:
        log_level: Literal["DEBUG", "INFO"] = "DEBUG" if self.debug else "INFO"
        log.parent.set_level(log_level, propagate=True)

    @staticmethod
    def _check_api_enabled() -> bool:
        """Check if the Python API is enabled in iTerm2 preferences."""
        try:
            result = subprocess.run(
                ["defaults", "read", "com.googlecode.iterm2", "EnableAPIServer"], capture_output=True, text=True
            )
            return result.returncode == 0 and result.stdout.strip() == "1"
        except Exception:
            return False

    @staticmethod
    def _enable_api() -> bool:
        """Enable the Python API in iTerm2 preferences."""
        try:
            subprocess.run(
                ["defaults", "write", "com.googlecode.iterm2", "EnableAPIServer", "-bool", "true"],
                check=True,
                capture_output=True,
            )
            return True
        except Exception:
            return False

    def _build_tag_regex(self, profile: Profile | PartialProfile) -> re.Pattern[str]:
        tag_regex = re.compile(re.escape(self._build_tag_name(profile)))
        return tag_regex

    def _build_tag_name(self, profile: Profile | PartialProfile) -> str:
        tag = f"{self.service_name}:{profile.name}{f':{self.extra_id}' if self.extra_id else ''}"
        return tag

    async def _find_tagged_context(
        self, profile: Profile | PartialProfile, window: Window | None = None
    ) -> tuple[Window, Tab, Session] | None:
        tag_regex = self._build_tag_regex(profile)

        log.add_context(status=f"Searching for tagged context for {profile.name}")
        async for window_obj, tab_obj, session_obj in self._iter_sessions(window):
            current_session = session_obj
            if current_session is None:
                continue

            session_profile = await current_session.async_get_profile()
            session_name = current_session.name
            tab_title = await tab_obj.async_get_variable("title")

            if self._profiles_match(session_profile, profile) and contains_matching_term(
                tag_regex, session_name, tab_title
            ):
                log.remove_context("status")
                log.debug(
                    "Found tagged iTermAPI context:"
                    f"\n- {session_name=}\n- {tab_title=}\n- {profile.name=}\n- {session_profile.name=}"
                )
                return window_obj, tab_obj, current_session

            log.debug(f"Skipping session '{session_name}' in tab '{tab_title}' with profile '{session_profile.name}'.")

        log.remove_context("status")
        return None

    async def _get_tagged_tab_with_session(
        self, window: Window, profile: Profile | PartialProfile, new_tab: bool = False
    ) -> tuple[Tab, Session]:
        """Select or create a tagged tab/session for this API context."""
        tag_regex = self._build_tag_regex(profile)
        new_tag = self._build_tag_name(profile)

        async def default_tab_with_session(override_new_tab: bool = False) -> tuple[Tab, Session]:
            selected_tab: Tab | None = None
            selected_session: Session | None = None

            if not new_tab and not override_new_tab:
                for tab_obj in window.tabs:
                    current_session = tab_obj.current_session

                    if current_session is None:
                        continue

                    tab_title = await tab_obj.async_get_variable("title")
                    session_name = current_session.name

                    if contains_matching_term(tag_regex, tab_title, session_name):
                        selected_tab, selected_session = tab_obj, current_session
                        break

            if new_tab or override_new_tab or selected_tab is None or selected_session is None:
                selected_tab, selected_session = await self.create_tab(window, profile, with_session=True)

            if selected_tab is None:
                raise RuntimeError("Could not get or create iTerm2 tab")

            if selected_session is None:
                raise RuntimeError("Could not get current session in tab")

            return selected_tab, selected_session

        if new_tab:
            log.debug("Creating new tab due to new_tab=True")
            selected_tab, selected_session = await default_tab_with_session()
        else:
            for tab_obj in window.tabs:
                current_session = tab_obj.current_session

                if current_session is None:
                    continue

                session_profile = await current_session.async_get_profile()
                session_name = current_session.name
                tab_title = await tab_obj.async_get_variable("title")

                if self._profiles_match(session_profile, profile) and contains_matching_term(
                    tag_regex, tab_title, session_name
                ):
                    selected_tab, selected_session = tab_obj, current_session
                    break
            else:
                selected_tab, selected_session = await default_tab_with_session(override_new_tab=True)

        tab_title = await selected_tab.async_get_variable("title")
        session_name = selected_session.name

        if contains_matching_term(tag_regex, tab_title, session_name) is False:
            log.debug(f"Renaming tab and session to '{new_tag}'")
            # PartialProfile("", self.connection, []) # TODO
            await selected_session.async_set_name(new_tag)
            await selected_tab.async_set_title(new_tag)

        return selected_tab, selected_session

    async def _iter_sessions(self, window: Window | None = None) -> AsyncGenerator[tuple[Window, Tab, Session]]:
        app = await self.get_app()
        windows = [window] if window is not None else app.windows

        for window in windows:
            for tab in window.tabs:
                for session in tab.all_sessions:
                    yield window, tab, session

    def _current_context_matches(
        self,
        profile: Profile | PartialProfile,
        *,
        require_window: bool = False,
        require_tab: bool = False,
        require_session: bool = False,
    ) -> bool:
        if require_window and self.window is None:
            return False

        if require_tab and self.tab is None:
            return False

        if require_session and self.session is None:
            return False

        ctx_profile = self.profile
        if ctx_profile is not None and self._profiles_match(ctx_profile, profile):
            return True

        return False

    @overload
    @staticmethod
    def _profile_guid(profile: None) -> None: ...
    @overload
    @staticmethod
    def _profile_guid(profile: Profile | PartialProfile | dict[str, str]) -> str: ...
    @staticmethod
    def _profile_guid(profile: Profile | PartialProfile | dict[str, str] | None) -> str | None:
        if profile is None:
            return None

        if isinstance(profile, dict):
            return profile.get("original_guid", None) or profile.get("guid")

        return (
            getattr(profile, "original_guid", None)
            or getattr(profile, "guid", None)
            or profile.all_properties.get("Guid")
        )

    @overload
    @staticmethod
    def _profile_name(profile: None) -> None: ...
    @overload
    @staticmethod
    def _profile_name(profile: Profile | PartialProfile | dict[str, str]) -> str: ...
    @staticmethod
    def _profile_name(profile: Profile | PartialProfile | dict[str, str] | None) -> str | None:
        if profile is None:
            return None

        if isinstance(profile, dict):
            return profile.get("name")

        return getattr(profile, "name", None)

    @classmethod
    def _profiles_match(
        cls, candidate_profile: Profile | PartialProfile, target_profile: Profile | PartialProfile
    ) -> bool:
        candidate_guid = cls._profile_guid(candidate_profile)
        target_guid = cls._profile_guid(target_profile)
        return candidate_guid == target_guid

    @property
    def version(self) -> str:
        connection = self.connection
        return ".".join(str(v) for v in connection.iterm2_protocol_version)

    def json(self) -> str:
        return json.dumps(
            {
                "profile": {"name": self._profile_name(self.profile), "guid": self._profile_guid(self.profile)},
                "iterm2_protocol_version": self.version,
                "app": {
                    "windows": len(self.app.windows),
                    "broadcast_domains": len(self.app.broadcast_domains),
                    "buried_sessions": len(self.app.buried_sessions),
                }
                if self.app
                else None,
                "window": {
                    "tabs": len(self.window.tabs),
                    "id": self.window.window_id,
                    "number": self.window.window_number,
                }
                if self.window
                else None,
                "tab": {
                    "id": self.tab.tab_id,
                    "sessions": len(self.tab.all_sessions),
                    "active_session_id": self.tab.active_session_id,
                }
                if self.tab
                else None,
                "session": {"id": self.session.session_id, "name": self.session.name} if self.session else None,
                "connection": repr(self.connection) if self.connection else None,
            },
            indent=4,
        )


async def create_iterm_state(
    connection_instance: Connection | None = None, **kwargs: Unpack[iTermStateSetupKwargs]
) -> iTermState:
    """Create and return a fully populated :class:`iTermState` using :class:`iTermAPI`.

    This is the coroutine adapter for call sites that historically expected a
    ``run_iterm_setup(connection, **kwargs) -> iTermState`` shape. The enhanced
    class owns all setup logic; this helper only unwraps the populated state.
    """
    api = await iTermAPI.async_create(
        profile_name=kwargs.get("dedicated_profile_name"),
        service_name=kwargs.get("service_name"),
        extra_id=kwargs.get("extra_id"),
        connection_instance=connection_instance,
        new_tab=kwargs.get("new_tab", False),
        debug=kwargs.get("debug"),
        activate=kwargs.get("activate", False),
        profile_properties=kwargs.get("profile_properties"),
    )

    from iterm2_api_wrapper.state import iTermState

    state = iTermState(
        connection=await api.get_connection(),
        app=await api.get_app(),
        window=await api.get_window(),
        tab=await api.get_tab(),
        session=await api.get_session(),
        profile=await api.get_profile(),
        is_hotkey_window=bool(await (await api.get_window()).async_get_variable("isHotkeyWindow")),
    )

    return state
