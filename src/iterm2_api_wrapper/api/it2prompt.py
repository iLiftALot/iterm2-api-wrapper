from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Generic, Literal, TypeVar, cast, overload

from iterm2 import api_pb2, capabilities, prompt, rpc

from .it2connection import Connection
from .it2measurement import CoordRange


if TYPE_CHECKING:
    from iterm2 import Connection as IT2Connection

    from ..gateway import _Connection


class Prompt(prompt.Prompt):
    _Prompt__proto: api_pb2.GetPromptResponse

    def __init__(self, proto: api_pb2.GetPromptResponse) -> None:
        super().__init__(proto)
        self.__proto = proto

    @property
    def output_range(self) -> CoordRange:
        return CoordRange.from_proto(self.__proto.output_range)

    @property
    def prompt_range(self) -> CoordRange:
        return CoordRange.from_proto(self.__proto.prompt_range)

    @property
    def command_range(self) -> CoordRange:
        return CoordRange.from_proto(self.__proto.command_range)


PromptEvent = tuple[Literal[prompt.PromptMonitor.Mode.PROMPT], Prompt | None]
PromptEventWithId = tuple[Literal[prompt.PromptMonitor.Mode.PROMPT], Prompt | None, str | None]

CommandStartEvent = tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_START], str]
CommandStartEventWithId = tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_START], str, str | None]

CommandEndEvent = tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_END], int]
CommandEndEventWithId = tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_END], int, str | None]

PromptMonitorEvent = PromptEvent | CommandStartEvent | CommandEndEvent
PromptMonitorEventWithId = PromptEventWithId | CommandStartEventWithId | CommandEndEventWithId

SnapshotT = TypeVar("SnapshotT")


class PromptMonitor(prompt.PromptMonitor, Generic[SnapshotT]):
    initial_snapshot: SnapshotT
    current_snapshot: SnapshotT
    snapshot_provider: Callable[[], Awaitable[SnapshotT]] | None

    @overload
    def __init__(
        self: PromptMonitor[None],
        connection: _Connection,
        session_id: str,
        modes: list[prompt.PromptMonitor.Mode] | None = None,
        *,
        snapshot_provider: None = None,
    ) -> None: ...
    @overload
    def __init__(
        self: PromptMonitor[SnapshotT],  # pyright: ignore[reportInvalidTypeVarUse]
        connection: _Connection,
        session_id: str,
        modes: list[prompt.PromptMonitor.Mode] | None = None,
        *,
        snapshot_provider: Callable[[], Awaitable[SnapshotT]] = ...,
    ) -> None: ...

    def __init__(
        self,
        connection: _Connection,
        session_id: str,
        modes: list[prompt.PromptMonitor.Mode] | None = None,
        *,
        snapshot_provider: Callable[[], Awaitable[SnapshotT]] | None = None,
    ):
        super().__init__(cast("IT2Connection", connection), session_id, modes)
        self.snapshot_provider = snapshot_provider
        self.initial_snapshot = cast(SnapshotT, None)
        self.current_snapshot = cast(SnapshotT, None)

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

    async def __aenter__(self) -> PromptMonitor[SnapshotT]:
        if self.snapshot_provider is not None:
            self.initial_snapshot = self.current_snapshot = await self.snapshot_provider()
        return cast(PromptMonitor[SnapshotT], await super().__aenter__())

    async def refresh_snapshot(self) -> SnapshotT:
        if self.snapshot_provider is None:
            raise RuntimeError("PromptMonitor.snapshot_provider was not passed during initialization.")

        self.current_snapshot = await self.snapshot_provider()
        return self.current_snapshot


async def async_get_prompt(
    connection: Connection, session_id: str | None = None, prompt_id: str | None = None
) -> Prompt | None:
    """Fetches a :class:`Prompt` by its unique ID if provided, or the most recent prompt.

    ---

    :param connection: The connection to iTerm2.
    :type connection: :class:`Connection`
    :param session_id: The Session ID the prompt belongs to.
    :type session_id: `str` | `None`, default=None
    :param prompt_id: The unique ID of the prompt.
    :type prompt_id: `str | None`, default=None
    :return: The prompt if one exists or else `None`.
    :rtype: :class:`Prompt` | `None`
    :raises :class:`rpc.RPCException`: _description_
    """

    if prompt_id:
        capabilities.check_supports_prompt_id(connection)

    response: api_pb2.ServerOriginatedMessage = await rpc.async_get_prompt(connection, session_id, prompt_id)
    status: api_pb2.GetPromptResponse._Status.ValueType = response.get_prompt_response.status
    if status == api_pb2.GetPromptResponse.Status.Value("OK"):  # 0
        return Prompt(response.get_prompt_response)

    if status == api_pb2.GetPromptResponse.Status.Value("PROMPT_UNAVAILABLE"):  # 3
        return None

    raise rpc.RPCException(api_pb2.GetPromptResponse.Status.Name(status))


def check_supports_prompt_monitor_modes(connection: _Connection) -> None:
    """Die if you can't monitor multiple prompt monitor modes."""
    if not capabilities.supports_prompt_monitor_modes(connection):
        raise capabilities.AppVersionTooOld(
            "This version of iTerm2 is too old to monitor the "
            "prompt in different modes. You should upgrade to "
            "run this script."
        )
