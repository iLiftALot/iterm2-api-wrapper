from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from iterm2_api_wrapper._logging import PrettyLog
from iterm2_api_wrapper.connection import Connection
from iterm2_api_wrapper.errors import ProfileNotFoundError, SessionNotFoundError
from iterm2_api_wrapper.typings import App, PartialProfile, Session, Tab, Window, async_get_app


if TYPE_CHECKING:
    from iterm2 import session, tab
    from iterm2_api_wrapper.typings import Profile


log = PrettyLog.get_logger(__name__)


class iTermAPI:
    def __init__(self, profile_name: str | None = None) -> None:
        self.loop = asyncio.new_event_loop()
        self.profile_name = profile_name
        self.conn: Connection | None = None
        self.app: App | None = None
        self.window: Window | None = None
        self.tab: Tab | None = None
        self.session: Session | None = None
        self.__profile_data: dict[str, PartialProfile] = {}
        self.loop.run_until_complete(self._initialize())

    async def _initialize(self) -> None:
        conn = self.conn = await self.get_connection()
        self.app = await self.get_app(conn)
        self.profile = await self.get_profile()
        self.window = await self.get_window()  # Potentially sets tab and session
        self.tab = self.tab or await self.get_tab()
        self.session = self.session or await self.get_session()

    @staticmethod
    async def get_connection() -> Connection:
        conn: Connection = await Connection.async_create()
        return conn

    @staticmethod
    async def get_app(conn: Connection | None = None) -> App:
        if conn is None:
            conn = await iTermAPI.get_connection()

        app_instance: App | None = await async_get_app(conn, create_if_needed=True)

        if app_instance is None:
            raise RuntimeError("Could not get iTerm2 app")

        return app_instance

    async def get_profile(self, profile_name: str | None = None) -> PartialProfile:
        if not self.conn:
            self.conn = await self.get_connection()

        profile: PartialProfile | None = None
        profile_name = profile_name or self.profile_name

        if profile_name is None:
            profile = await PartialProfile.async_get_default(self.conn)

        profile_entries: list[PartialProfile] = await PartialProfile.async_get(self.conn)

        for profile_obj in profile_entries:
            p_name = profile_obj.name
            self.__profile_data[p_name] = profile_obj

            if not profile and p_name == profile_name:
                profile = profile_obj

        if not profile:
            raise ProfileNotFoundError(target_profile_name=f"{profile_name}", profile_data=self.__profile_data)

        return profile

    async def get_window(self, *, profile_name: str | None = None, window_id: str | None = None) -> Window:
        """Finds or creates a new window.

        :param connection: A :class:`Connection`.
        :param profile: The name of the :class:`PartialProfile` to use for the new window.
        :param command: A command to run in lieu of the shell in the new
            session. Mutually exclusive with profile_customizations.
        :param profile_customizations: :class:`~iterm2.LocalWriteOnlyProfile` giving changes to
            make in profile. Mutually exclusive with command.

        :return: Returns a new :class:`Window` or `None` if the session ended right away.
        :rtype: :class:`Window` | `None`

        :raises CreateWindowException: Raises :class:`~iterm2.CreateWindowException` if something went wrong.
        """
        if not self.app:
            conn = self.conn

            if not conn:
                conn = self.conn = await self.get_connection()

            self.app = await self.get_app(conn)

        window: Window | None = None

        if window_id and (window := await self.app.tab_delegate_get_window_by_id(window_id)):
            return window

        profile_name = profile_name or self.profile.name
        profile_guid = self._profile_guid(self.__profile_data[profile_name])

        for w in self.app.windows:
            for t in w.tabs:
                for s in t.all_sessions:
                    session_profile = await s.async_get_profile()
                    session_profile_guid = self._profile_guid(session_profile)
                    # profile_name = await s.async_get_variable("profileName")

                    if session_profile_guid == profile_guid:
                        log.debug(
                            f"PROFILE FOUND: '{profile_name}' ({profile_guid}) in window '{w.window_id}' for session '{s.name}' ({s.session_id})"
                        )
                        self.tab, self.session = t, s
                        return w
                    log.debug(
                        f"PROFILE SKIPPED: '{session_profile.name}' ({session_profile_guid}) != '{profile_name}' ({profile_guid}) from session '{s.name}' ({s.session_id})"
                    )

        log.debug(f"Profile with name '{profile_name}' ({profile_guid}) not found.")
        return self.app.windows[0]

    async def get_tab(self, profile_name: str | None = None, tab_id: str | None = None) -> Tab:
        if not self.app:
            conn = self.conn

            if not conn:
                conn = self.conn = await self.get_connection()

            self.app = await self.get_app()

        tab: tab.Tab | None = None

        if tab_id and (tab := await self.app.window_delegate_get_tab_by_id(tab_id)):
            return tab

        profile_name = profile_name or self.profile.name
        profile_guid = self._profile_guid(self.__profile_data[profile_name])

        if not self.window:
            self.window = await self.get_window(profile_name=profile_name)

        for t in self.window.tabs:
            tab_profile_name = await t.async_get_variable("currentSession.profileName")
            tab_profile = self.__profile_data[tab_profile_name]
            tab_profile_guid = self._profile_guid(tab_profile)

            if tab_profile_guid == profile_guid:
                tab = t
                break
        else:
            tab = await self.window.async_create_tab(profile=profile_name)

        if tab is None:
            raise RuntimeError(f"Unable to find or create a new tab with profile '{profile_name}'.")

        return tab

    async def get_session(self, profile_name: str | None = None, session_id: str | None = None) -> Session:
        if not self.app:
            conn = self.conn

            if not conn:
                conn = self.conn = await self.get_connection()

            self.app = await self.get_app()

        session: session.Session | None = None

        if session_id and (session := self.app.get_session_by_id(session_id)):
            if session.buried:
                await session.async_activate(False, False)

            return session

        profile_name = profile_name or self.profile.name
        profile_guid = self._profile_guid(self.__profile_data[profile_name])

        if not self.tab:
            self.tab = await self.get_tab(profile_name=profile_name)

        for s in self.tab.all_sessions:
            session_profile = await s.async_get_profile()
            session_guid = self._profile_guid(session_profile)

            if session_guid == profile_guid:
                session = s
                break
        else:
            raise SessionNotFoundError(f"{profile_name} ({profile_guid})")

        return session

    @staticmethod
    def _profile_guid(profile: Profile | PartialProfile) -> str | None:
        return profile.original_guid or profile.guid

    def __str__(self) -> str:
        return json.dumps(
            {
                "profile": {"name": self.profile_name, "guid": self._profile_guid(self.profile)},
                "iterm2_protocol_version": ".".join([str(v) for v in self.conn.iterm2_protocol_version]),  # type: ignore
                "app": {"windows": len(self.app.windows), "active": self.app.app_active},  # type: ignore
                "window": {"tabs": len(self.window.tabs), "id": self.window.window_id},  # type: ignore
                "tab": {"id": self.tab.tab_id, "sessions": len(self.tab.all_sessions)},  # type: ignore
                "session": {"id": self.session.session_id, "name": self.session.name},  # type: ignore
                "connection": str(self.conn.websocket),  # type: ignore
            },
            indent=4,
        )
