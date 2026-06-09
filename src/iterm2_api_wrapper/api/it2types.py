from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Tuple, cast, overload

from iterm2 import app, capabilities, profile, prompt, session, tab, window


if TYPE_CHECKING:
    from iterm2.api_pb2 import GetPromptResponse

    from iterm2_api_wrapper.connection import Connection


class Prompt(prompt.Prompt):
    _Prompt__proto: GetPromptResponse


type PromptEvent = Tuple[Literal[prompt.PromptMonitor.Mode.PROMPT], Prompt | None]
type PromptEventWithId = Tuple[Literal[prompt.PromptMonitor.Mode.PROMPT], Prompt | None, str | None]

type CommandStartEvent = Tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_START], str]
type CommandStartEventWithId = Tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_START], str, str | None]

type CommandEndEvent = Tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_END], int]
type CommandEndEventWithId = Tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_END], int, str | None]

type PromptMonitorEvent = PromptEvent | CommandStartEvent | CommandEndEvent
type PromptMonitorEventWithId = PromptEventWithId | CommandStartEventWithId | CommandEndEventWithId


class PromptMonitor(prompt.PromptMonitor):
    @overload
    async def async_get(self, include_id: Literal[False] = False, *, mode: None = None) -> PromptMonitorEvent: ...
    @overload
    async def async_get(self, include_id: Literal[True], *, mode: None = None) -> PromptMonitorEventWithId: ...

    @overload
    async def async_get(
        self, include_id: Literal[False] = False, *, mode: Literal[prompt.PromptMonitor.Mode.PROMPT]
    ) -> PromptEvent: ...
    @overload
    async def async_get(
        self, include_id: Literal[True], *, mode: Literal[prompt.PromptMonitor.Mode.PROMPT]
    ) -> PromptEventWithId: ...

    @overload
    async def async_get(
        self, include_id: Literal[False] = False, *, mode: Literal[prompt.PromptMonitor.Mode.COMMAND_START]
    ) -> CommandStartEvent: ...
    @overload
    async def async_get(
        self, include_id: Literal[True], *, mode: Literal[prompt.PromptMonitor.Mode.COMMAND_START]
    ) -> CommandStartEventWithId: ...

    @overload
    async def async_get(
        self, include_id: Literal[False] = False, *, mode: Literal[prompt.PromptMonitor.Mode.COMMAND_END]
    ) -> CommandEndEvent: ...
    @overload
    async def async_get(
        self, include_id: Literal[True], *, mode: Literal[prompt.PromptMonitor.Mode.COMMAND_END]
    ) -> CommandEndEventWithId: ...

    async def async_get(
        self, include_id: bool = False, *, mode: prompt.PromptMonitor.Mode | None = None
    ) -> PromptMonitorEvent | PromptMonitorEventWithId:
        while True:
            result = cast(PromptMonitorEvent | PromptMonitorEventWithId, await super().async_get(include_id))
            if mode is None or result[0] == mode:
                return result


class Profile(profile.Profile):
    guid: str  # pyright: ignore[reportIncompatibleMethodOverride]
    original_guid: str  # pyright: ignore[reportIncompatibleMethodOverride]

    @staticmethod
    async def async_get(connection: Connection, guids: list[str] | None = None) -> list[Profile]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Profile], await profile.Profile.async_get(connection, guids))

    @staticmethod
    async def async_get_default(connection: Connection) -> Profile:
        return cast(Profile, await profile.Profile.async_get_default(connection))


class PartialProfile(profile.PartialProfile):
    @staticmethod
    async def async_get(connection: Connection, guids: list[str] | None = None) -> list[PartialProfile]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[PartialProfile], await profile.PartialProfile.async_get(connection, guids))

    @staticmethod
    async def async_get_default(connection: Connection, properties: list[str] | None = None) -> PartialProfile:
        properties = properties or ["Guid", "Name"]
        return cast(PartialProfile, await profile.PartialProfile.async_get_default(connection, properties))

    @staticmethod
    async def async_query(  # pyright: ignore[reportIncompatibleMethodOverride]
        connection: Connection, guids: list[str] | None = None, properties: list[str] | None = None
    ) -> list[PartialProfile]:
        properties = properties or ["Guid", "Name"]
        return cast(list[PartialProfile], await profile.PartialProfile.async_query(connection, guids, properties))


class Session(session.Session):
    name: str

    async def async_get_profile(self) -> Profile:
        return cast(Profile, await super().async_get_profile())

    @property
    def tab(self) -> Tab | None:
        return cast(Tab | None, super().tab)


class Tab(tab.Tab):
    @property
    def all_sessions(self) -> list[Session]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Session], super().all_sessions)

    @property
    def sessions(self) -> list[Session]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Session], super().sessions)

    @property
    def current_session(self) -> Session | None:
        return cast(Session, super().current_session)


class Window(window.Window):
    """Represents a terminal window.

    Do not create an instance of `Window` by calling the initializer yourself.
    To get a reference to an existing window, use :class:`~iterm2.app.App` and
    query its `windows` property. To create a new window, use
    :meth:`async_create`.
    """

    @property
    def tabs(self) -> list[Tab]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Tab], super().tabs)

    @property
    def current_tab(self) -> Tab | None:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(Tab | None, super().current_tab)

    @staticmethod
    async def async_create(  # pyright: ignore[reportIncompatibleMethodOverride]
        connection: Connection,
        profile: str | None = None,
        command: str | None = None,
        profile_customizations: profile.LocalWriteOnlyProfile | None = None,
    ) -> Window | None:
        return cast(
            Window | None, await window.Window.async_create(connection, profile, command, profile_customizations)
        )

    async def async_create_tab(
        self,
        profile: str | None = None,
        command: str | None = None,
        index: int | None = None,
        profile_customizations: profile.LocalWriteOnlyProfile | None = None,
    ) -> Tab | None:
        return cast(Tab | None, await super().async_create_tab(profile, command, index, profile_customizations))


class App(app.App):
    @property
    def windows(self) -> list[Window]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Window], super().windows)

    @property
    def current_window(self) -> Window | None:
        return cast(Window | None, super().current_window)

    def get_window_by_id(self, window_id: str) -> Window | None:
        return cast(Window | None, super().get_window_by_id(window_id))

    def get_session_by_id(self, session_id: str, include_buried: bool = True) -> Session | None:
        return cast(Session | None, super().get_session_by_id(session_id, include_buried))

    def get_tab_by_id(self, tab_id: str) -> Tab | None:
        return cast(Tab | None, super().get_tab_by_id(tab_id))

    def get_window_for_tab(self, tab_id: str) -> Window | None:
        return cast(Window | None, super().get_window_for_tab(tab_id))

    def get_window_and_tab_for_session(self, session: Session) -> Tuple[None, None] | Tuple[Window, Tab]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(Tuple[Window, Tab] | Tuple[None, None], super().get_window_and_tab_for_session(session))

    async def window_delegate_get_tab_by_id(self, tab_id: str) -> Tab | None:
        return cast(Tab | None, await super().window_delegate_get_tab_by_id(tab_id))

    async def tab_delegate_get_window_by_id(self, window_id: str) -> Window | None:
        return cast(Window | None, await super().tab_delegate_get_window_by_id(window_id))

    def session_delegate_get_tab(self, session) -> Tab | None:
        return cast(Tab | None, super().session_delegate_get_tab(session))


@overload
async def async_get_app(connection: Connection, create_if_needed: Literal[True]) -> App: ...
@overload
async def async_get_app(connection: Connection, create_if_needed: Literal[False]) -> App | None: ...
async def async_get_app(connection: Connection, create_if_needed: bool = True) -> App | None:
    """Returns the app singleton, creating it if needed.

    :param connection: The connection to iTerm2.
    :type connection: :class:`Connection`
    :param create_if_needed: If `True`, create the global :class:`App` instance
      if one does not already exists. If `False`, do not create it.

    :returns: The global :class:`App` instance. If :param:`create_if_needed` is False,
    then this may return `None` if no such instance exists.
    :rtype: :class:`App` | None
    """
    return cast(App, await app.async_get_app(connection, create_if_needed))


async def async_get_last_prompt(connection: Connection, session_id: str) -> Prompt | None:
    """
    Fetches info about the last prompt in a session.

    :param connection: The connection to iTerm2.
    :type connection: :class:`Connection`
    :param session_id: The session ID for which to fetch the most recent prompt.

    :returns: The prompt if one exists, or else `None`.
    :rtype: :class:`iterm2.prompt.Prompt` | None

    :raises: :class:`iterm2.rpc.RPCException` if something goes wrong.
    """
    return cast(Prompt | None, await prompt.async_get_last_prompt(connection, session_id))


async def async_get_prompt_by_id(connection: Connection, session_id: str, prompt_unique_id: str) -> Prompt | None:
    """
    Fetches a Prompt by its unique ID.

    :param connection: The connection to iTerm2.
    :type connection: :class:`Connection`
    :param session_id: The Session ID the prompt belongs to.
    :param prompt_unique_id: The unique ID of the prompt.

    :returns: The prompt if one exists or else `None`.
    :rtype: :class:`iterm2.prompt.Prompt` | None

    :raises: :class:`iterm2.rpc.RPCException` if something goes wrong.
    """
    return cast(Prompt | None, await prompt.async_get_prompt_by_id(connection, session_id, prompt_unique_id))


def check_supports_prompt_monitor_modes(connection):
    """Die if you can't monitor multiple prompt monitor modes."""
    if not capabilities.supports_prompt_monitor_modes(connection):
        raise capabilities.AppVersionTooOld(
            "This version of iTerm2 is too old to monitor the "
            "prompt in different modes. You should upgrade to "
            "run this script."
        )
