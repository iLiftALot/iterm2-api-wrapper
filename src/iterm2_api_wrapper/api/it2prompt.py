from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast, overload

from iterm2 import capabilities, prompt

from .it2connection import Connection


if TYPE_CHECKING:
    from iterm2.api_pb2 import GetPromptResponse
    from iterm2.connection import Connection as IT2Connection


class Prompt(prompt.Prompt):
    _Prompt__proto: GetPromptResponse


type PromptEvent = tuple[Literal[prompt.PromptMonitor.Mode.PROMPT], Prompt | None]
type PromptEventWithId = tuple[Literal[prompt.PromptMonitor.Mode.PROMPT], Prompt | None, str | None]

type CommandStartEvent = tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_START], str]
type CommandStartEventWithId = tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_START], str, str | None]

type CommandEndEvent = tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_END], int]
type CommandEndEventWithId = tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_END], int, str | None]

type PromptMonitorEvent = PromptEvent | CommandStartEvent | CommandEndEvent
type PromptMonitorEventWithId = PromptEventWithId | CommandStartEventWithId | CommandEndEventWithId


class PromptMonitor(prompt.PromptMonitor):
    def __init__(self, connection: Connection, session_id: str, modes: list[prompt.PromptMonitor.Mode] | None = None):
        super().__init__(cast("IT2Connection", connection), session_id, modes)

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
    return cast(Prompt | None, await prompt.async_get_last_prompt(cast(IT2Connection, connection), session_id))


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
    return cast(
        Prompt | None,
        await prompt.async_get_prompt_by_id(cast(IT2Connection, connection), session_id, prompt_unique_id),
    )


def check_supports_prompt_monitor_modes(connection) -> None:
    """Die if you can't monitor multiple prompt monitor modes."""
    if not capabilities.supports_prompt_monitor_modes(connection):
        raise capabilities.AppVersionTooOld(
            "This version of iTerm2 is too old to monitor the "
            "prompt in different modes. You should upgrade to "
            "run this script."
        )
