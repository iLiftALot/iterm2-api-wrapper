from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, overload

from iterm2 import api_pb2, broadcast, rpc
from typing_extensions import override


if TYPE_CHECKING:
    from iterm2 import Session as UpstreamSession

    from ..core.gateway import Connection
    from .it2session import Session


class BroadcastDomain(broadcast.BroadcastDomain):
    def __init__(self):
        self.__sessions: list[Session] = []
        self.__unresolved: list[Callable[..., Session | None]] = []

    @overload
    def add_session(self, session: Session) -> None: ...
    @overload
    def add_session(self, session: UpstreamSession) -> None: ...
    def add_session(self, session: Any) -> None:
        """Adds a session to the broadcast domain.

        :param session: The :class:`Session` to add.
        """
        self.__sessions.append(session)

    @property
    @override
    def sessions(self) -> list[Session]:  # type: ignore
        resolved_callbacks: list[Session | None] = [cb() for cb in self.__unresolved]
        filtered_sessions: list[Session] = [session for session in resolved_callbacks if isinstance(session, Session)]
        return [*filtered_sessions, *self.__sessions]


async def async_set_broadcast_domains(connection: Connection, broadcast_domains: list[BroadcastDomain]) -> None:
    """Sets the current set of broadcast domains.

    :param connection: The connection to iTerm2.
    :param broadcast_domains: The new collection of broadcast domains.

    .. seealso:: Example ":ref:`enable_broadcasting_example`"
    """
    list_of_sessionid_lists: list[list[str]] = [[s.session_id for s in d.sessions] for d in broadcast_domains]
    response: api_pb2.ServerOriginatedMessage = await rpc.async_set_broadcast_domains(
        connection, list_of_sessionid_lists
    )

    if response.set_broadcast_domains_response.status != api_pb2.SetBroadcastDomainsResponse.Status.Value("OK"):
        raise rpc.RPCException(
            api_pb2.SetBroadcastDomainsResponse.Status.Name(response.set_broadcast_domains_response.status)
        )
