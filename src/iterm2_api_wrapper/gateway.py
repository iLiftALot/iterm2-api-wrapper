from __future__ import annotations

import asyncio
import errno
import os
import time
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Protocol


if TYPE_CHECKING:
    from .api.it2connection import Connection
    from .state import iTermState


class _Connection(Protocol):
    """Connection protocol for iTerm2's Python API."""

    loop: asyncio.AbstractEventLoop | None

    @classmethod
    async def async_create(cls) -> Connection: ...


class RefreshableState[StateT](Protocol):
    """
    Minimal protocol that `iTermClient` needs from a "state" object.

    This intentionally does **not** depend on iTerm2 concrete types so that unit
    tests can provide simple fakes without requiring a live iTerm2 runtime.
    """

    _refresh_callback: Callable[[], Awaitable[StateT]] | Awaitable[StateT] | None
    _event_loop: asyncio.AbstractEventLoop | None

    async def ensure_state(
        self, refresh_callback: Callable[[], Awaitable[StateT]] | Awaitable[StateT] | None = None
    ) -> None: ...
    def refresh_from(self, new_state: StateT) -> None: ...


_ENV_CONNECT_TIMEOUT = "ITERM_CONNECT_TIMEOUT"
_DEFAULT_CONNECT_TIMEOUT_S = 10.0

# Transient errors while iTerm2 is launching and its API socket isn't ready yet.
_TRANSIENT_CONNECT_ERRNOS = {errno.ENOENT, errno.ECONNREFUSED, errno.ECONNRESET}


async def _ensure_iterm_app_ready(*, activate: bool) -> None:
    from .pyobjc_adapter import async_ensure_iterm_app_running

    await async_ensure_iterm_app_running(activate=activate)


def _get_connect_timeout_s() -> float:
    """Connection timeout (seconds) for initial iTerm2 API handshake.

    This is intentionally *separate* from `iTermClient(timeout=...)` so we don't
    hang forever when iTerm2 isn't installed or its Python API is disabled.

    Override via the `ITERM_CONNECT_TIMEOUT` environment variable.
    """
    raw = os.getenv(_ENV_CONNECT_TIMEOUT)

    if raw is None:
        return _DEFAULT_CONNECT_TIMEOUT_S

    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_CONNECT_TIMEOUT_S

    return max(0.0, value)


async def _async_create_connection_with_retry(
    connection_cls: type[_Connection],
    *,
    timeout_s: float,
    initial_delay_s: float = 0.05,
    max_delay_s: float = 0.5,
    backoff: float = 1.6,
) -> Connection:
    """Create an iTerm2 `Connection`, retrying until its socket is ready."""
    deadline = time.monotonic() + timeout_s
    delay_s = initial_delay_s

    while True:
        try:
            return await connection_cls.async_create()
        except OSError as exc:
            # iTerm2 isn't ready yet (socket missing / refusing connections).
            if exc.errno not in _TRANSIENT_CONNECT_ERRNOS:
                raise

            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out after {timeout_s:.1f}s waiting for iTerm2's Python API socket.") from exc

            await asyncio.sleep(delay_s)
            delay_s = min(max_delay_s, delay_s * backoff)


@contextmanager
def _temporary_iterm_env(*, it2_suite: str | None = None, it2_app_path: str | None = None):
    managed = {"IT2_SUITE": it2_suite, "IT2_APP_PATH": it2_app_path}
    previous = {key: os.environ.get(key) for key in managed}

    try:
        for key, value in managed.items():
            if value:
                os.environ[key] = value
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


class ITermGateway[StateT: RefreshableState[Any]](Protocol):
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

    async def create_state(self, **kwargs: Any) -> iTermState:
        from .api.it2api import create_iterm_state
        from .api.it2connection import Connection
        from .api.it2runtime import bootstrap_iterm2_runtime

        it2_suite = kwargs.pop("it2_suite", None)
        it2_app_path = kwargs.pop("it2_app_path", None)
        activate = bool(kwargs.pop("activate", True))

        with _temporary_iterm_env(it2_suite=it2_suite, it2_app_path=it2_app_path):
            await bootstrap_iterm2_runtime()
            await _ensure_iterm_app_ready(activate=activate)

            connect_timeout_s = _get_connect_timeout_s()
            try:
                conn = await _async_create_connection_with_retry(Connection, timeout_s=connect_timeout_s)
            except TimeoutError as exc:
                raise ConnectionError(
                    "Could not connect to iTerm2's Python API. "
                    "Ensure iTerm2 is running and its Python API is enabled. "
                    f"(waited {connect_timeout_s:.1f}s; set {_ENV_CONNECT_TIMEOUT} to increase)"
                ) from exc

            return await create_iterm_state(conn, activate=False, **kwargs)


class SetupCoroGateway[StateT: RefreshableState[Any]](ITermGateway[StateT]):
    """
    Gateway that builds state using a provided setup coroutine.

    This preserves the older `iTermClient(coro=...)` customization point, while
    still allowing unit tests to supply a fully-fake gateway (no iTerm2 import).
    """

    def __init__(self, setup_coro: Callable[..., Awaitable[StateT]]) -> None:
        self._setup_coro: Callable[..., Awaitable[StateT]] = setup_coro

    async def create_state(self, **kwargs: Any) -> StateT:
        from .api.it2connection import Connection
        from .api.it2runtime import bootstrap_iterm2_runtime

        it2_suite = kwargs.pop("it2_suite", None)
        it2_app_path = kwargs.pop("it2_app_path", None)
        activate = bool(kwargs.pop("activate", True))

        with _temporary_iterm_env(it2_suite=it2_suite, it2_app_path=it2_app_path):
            await bootstrap_iterm2_runtime()
            await _ensure_iterm_app_ready(activate=activate)

            connect_timeout_s = _get_connect_timeout_s()
            try:
                conn = await _async_create_connection_with_retry(Connection, timeout_s=connect_timeout_s)
            except TimeoutError as exc:
                raise ConnectionError(
                    "Could not connect to iTerm2's Python API. "
                    "Ensure iTerm2 is running and its Python API is enabled. "
                    f"(waited {connect_timeout_s:.1f}s; set {_ENV_CONNECT_TIMEOUT} to increase)"
                ) from exc

            return await self._setup_coro(conn, **kwargs)
