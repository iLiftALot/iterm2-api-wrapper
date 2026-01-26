from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol, TypeVar


if TYPE_CHECKING:
    from iterm2_api_wrapper.state import iTermState
    from iterm2.connection import Connection


class RefreshableState(Protocol):
    """
    Minimal protocol that `iTermClient` needs from a "state" object.

    This intentionally does *not* depend on iTerm2 concrete types so that unit
    tests can provide simple fakes without requiring a live iTerm2 runtime.
    """

    refresh_callback: Callable[[], Awaitable[Any]] | None

    async def ensure_state(
        self,
        refresh_callback: Callable[[], Awaitable[Any]] | Awaitable[Any] | None = None,
    ) -> None: ...
    def refresh_from(self, new_state: Any) -> None: ...


StateT = TypeVar("StateT", "iTermState", RefreshableState, covariant=True)


class ITermGateway(Protocol[StateT]):
    """
    Creates a fully-initialized state object.

    This is the main adapter seam: `iTermClient` depends on this protocol rather
    than importing iTerm2 directly.
    """

    async def create_state(self, **kwargs: Any) -> StateT: ...


class DefaultITermGateway(ITermGateway["iTermState"]):
    """
    Default gateway that uses the real iTerm2 Python API.

    Importantly, iTerm2/AppKit-specific imports happen lazily inside methods so
    importing `iterm2_api_wrapper` remains test-friendly in non-macOS contexts.
    """

    async def create_state(self, **kwargs: Any) -> "iTermState":  # noqa: UP037
        from iterm2.connection import Connection

        from iterm2_api_wrapper.setup import run_iterm_setup

        conn = await Connection.async_create()
        return await run_iterm_setup(conn, **kwargs)


class SetupCoroGateway(ITermGateway["iTermState"]):
    """
    Gateway that builds state using a provided setup coroutine.

    This preserves the older `iTermClient(coro=...)` customization point, while
    still allowing unit tests to supply a fully-fake gateway (no iTerm2 import).
    """

    def __init__(self, setup_coro: Callable[[Connection], Awaitable[iTermState]]) -> None:
        self._setup_coro: Callable[..., Awaitable[iTermState]] = setup_coro

    async def create_state(self, **kwargs: Any) -> iTermState:
        from iterm2.connection import Connection

        conn = await Connection.async_create()
        return await self._setup_coro(conn, **kwargs)
