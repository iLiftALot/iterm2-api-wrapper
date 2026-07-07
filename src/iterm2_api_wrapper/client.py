from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import sys
import threading
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from threading import Thread
from types import TracebackType
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from .gateway import DefaultITermGateway, ITermGateway, SetupCoroGateway


if sys.version_info >= (3, 12):
    from typing import Unpack
else:
    from typing_extensions import Unpack

if TYPE_CHECKING:
    from .gateway import RefreshableState, _Connection
    from .state import iTermState
    from .typings import iTermStateSetupKwargs


StateT = TypeVar("StateT", bound="RefreshableState[Any]")


class iTermClient(Generic[StateT]):
    def __init__(
        self,
        coro: Callable[[_Connection], Awaitable[iTermState]] | None = None,
        *,
        gateway: ITermGateway[StateT] | None = None,
        timeout: float | None = None,
        **kwargs: Unpack[iTermStateSetupKwargs],
    ) -> None:
        self._setup(coro=coro, gateway=gateway, timeout=timeout, **kwargs)
        self._state: StateT = asyncio.run_coroutine_threadsafe(self._init_async(), self._loop).result(
            timeout=self._timeout
        )

    def _setup(
        self,
        coro: Callable[[_Connection], Awaitable[iTermState]] | None = None,
        *,
        gateway: ITermGateway[StateT] | None = None,
        timeout: float | None = None,
        **kwargs: Unpack[iTermStateSetupKwargs],
    ) -> None:
        """Non-blocking initialization of loop, thread, and gateway."""
        if gateway is not None:
            self._gateway = gateway
        elif coro is not None:
            self._gateway = cast(ITermGateway[StateT], SetupCoroGateway(coro))
        else:
            self._gateway = cast(ITermGateway[StateT], DefaultITermGateway())

        self._kwargs = kwargs
        self._timeout = timeout
        self._loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._lock = asyncio.Lock()

    @classmethod
    async def create(
        cls,
        coro: Callable[[_Connection], Awaitable[iTermState]] | None = None,
        *,
        gateway: ITermGateway[StateT] | None = None,
        timeout: float | None = None,
        **kwargs: Unpack[iTermStateSetupKwargs],
    ) -> iTermClient[StateT]:
        """Async factory — never blocks the calling event loop."""
        instance = object.__new__(cls)
        instance._setup(coro=coro, gateway=gateway, timeout=timeout, **kwargs)
        future = asyncio.run_coroutine_threadsafe(instance._init_async(), instance._loop)
        instance._state = await asyncio.get_running_loop().run_in_executor(None, lambda: future.result(timeout=timeout))
        return instance

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Get the event loop used by the iTermClient."""
        return self._loop

    @property
    def state(self) -> StateT:
        """
        Get the current iTermState without ensuring its validity.

        Recommended to use ``get_state()`` or ``get_state_async()`` instead.

        ---

        :return: The current iTermState without ensuring its validity.
        :rtype: ``iTermState``
        """
        return self._state

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _on_client_loop(self) -> bool:
        """Check if currently running on the client's internal event loop."""
        try:
            running = asyncio.get_running_loop()
            return running is self._loop
        except RuntimeError:
            return False

    async def _init_async(self) -> StateT:
        state: StateT = await self._gateway.create_state(**self._kwargs)
        state._refresh_callback = self._init_async
        state._event_loop = self._loop

        connection: _Connection | None = getattr(state, "connection", None)
        if connection is not None:
            connection.loop = self._loop

        return state

    async def _refresh_async(self) -> None:
        async with self._lock:
            new_state = await self._init_async()
            try:
                self._state.refresh_from(new_state)
            except Exception:
                # As a fallback, replace state entirely. This can break code that
                # holds a reference to the old state, but is safer than leaving
                # the client in a broken state.
                self._state = new_state

    def close(self) -> None:
        # Don't try to join if we're on the client's own thread
        current_thread = threading.current_thread()
        is_own_thread = current_thread is self._thread

        if self._loop.is_running() and not is_own_thread:
            connection: _Connection | None = getattr(getattr(self, "_state", None), "connection", None)
            async_close: Coroutine[Any, Any, None] | None = getattr(connection, "async_close", None)
            if inspect.iscoroutinefunction(async_close):
                try:
                    asyncio.run_coroutine_threadsafe(async_close(), self._loop).result(timeout=self._timeout or 5.0)
                except (TimeoutError, RuntimeError, concurrent.futures.CancelledError):
                    pass

        if self._loop.is_running():
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except RuntimeError:
                # Loop might already be stopping or have pending callbacks
                pass

        # Only join if we're not on the client's thread
        if not is_own_thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)  # Add timeout to prevent hangs

        if not self._loop.is_closed():
            try:
                self._loop.close()
            except RuntimeError:
                # Loop might still have pending callbacks if we couldn't join
                pass

    def get_state(self) -> StateT:
        """
        Ensure that the iTermState is valid, refreshing it if necessary.

        Only call this method from outside of the event loop.

        ---

        :return: The current iTermState, refreshed if necessary.
        :rtype: ``iTermState``
        """
        return self._ensure_state()

    async def get_state_async(self) -> StateT:
        """
        Ensure that the client's state is valid, refreshing it if necessary.

        This method auto-detects the current event loop and routes to the
        client's internal loop if necessary.

        ---

        :return: The current iTermState, refreshed if necessary.
        :rtype: ``iTermState``
        """
        if self._on_client_loop():
            return await self._ensure_state_async()
        # We're on a different loop; schedule on the client's loop
        future = asyncio.run_coroutine_threadsafe(self._ensure_state_async(), self._loop)
        return await asyncio.get_running_loop().run_in_executor(None, future.result)

    def _ensure_state(self) -> StateT:
        """Internal method. Use get_state instead."""

        async def _invoke() -> StateT:
            try:
                async with self._lock:
                    await self._state.ensure_state(refresh_callback=self._init_async)
            except Exception:
                await self._refresh_async()

            return self._state

        return asyncio.run_coroutine_threadsafe(_invoke(), self._loop).result(timeout=self._timeout)

    async def _ensure_state_async(self) -> StateT:
        """Internal method. Use get_state_async instead."""

        try:
            async with self._lock:
                await self._state.ensure_state(refresh_callback=self._init_async)
        except Exception:
            await self._refresh_async()

        return self._state

    def __enter__(self) -> iTermClient[StateT]:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        if not self._loop.is_closed():
            self.close()

    async def __aenter__(self) -> iTermClient[StateT]:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        if not self._loop.is_closed():
            self.close()

    def __del__(self) -> None:
        if hasattr(self, "_loop") and not self._loop.is_closed():
            try:
                if self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass


if TYPE_CHECKING:
    ITermClient = iTermClient[iTermState]
else:
    ITermClient = iTermClient


def create_iterm_client(*, timeout: float | None = None, **kwargs: Unpack[iTermStateSetupKwargs]) -> ITermClient:
    """
    Convenience factory that provides strong type inference for the default state type.

    Some editors/linters struggle to infer `StateT` defaults for generic classes;
    this helper gives you a concrete `iTermClient[iTermState]` without needing an
    explicit annotation at the call site.
    """
    return iTermClient(timeout=timeout, **kwargs)


@dataclass(frozen=True)
class SharedClientKey:
    service_name: str = "iterm-api"
    dedicated_profile_name: str | None = None
    extra_id: str | None = None

    @classmethod
    def from_kwargs(cls, **kwargs: Unpack[iTermStateSetupKwargs]) -> SharedClientKey:
        return cls(
            service_name=kwargs.get("service_name") or "iterm-api",
            dedicated_profile_name=kwargs.get("dedicated_profile_name") or None,
            extra_id=kwargs.get("extra_id") or None,
        )


def _shared_client_key(**kwargs: Unpack[iTermStateSetupKwargs]) -> SharedClientKey:
    return SharedClientKey.from_kwargs(**kwargs)


_shared_clients: dict[SharedClientKey, ITermClient] = {}
_shared_lock = asyncio.Lock()


async def get_shared_client(**kwargs: Unpack[iTermStateSetupKwargs]) -> ITermClient:
    """Return a shared client resolved by service/profile/extra identifiers.

    Calls without identifiers still behave like the old singleton and reuse the
    default key: ``SharedClientKey(service_name="iterm-api")``.

    Calls with identifiers, for example
    ``service_name="pyterm-mcp", extra_id=ctx.session_id``, get a distinct
    cached client for those identifiers.
    """
    key = _shared_client_key(**kwargs)

    if (client := _shared_clients.get(key)) is not None:
        return client

    async with _shared_lock:
        if (client := _shared_clients.get(key)) is not None:
            return client

        client = await iTermClient.create(**kwargs)
        _shared_clients[key] = client
        return client


async def close_shared_client(**kwargs: Unpack[iTermStateSetupKwargs]) -> None:
    """Close and remove one shared client by identifier, if it exists."""
    key = _shared_client_key(**kwargs)

    async with _shared_lock:
        client = _shared_clients.pop(key, None)

    if client is not None:
        client.close()


async def close_all_shared_clients() -> None:
    """Close and clear all shared clients."""
    async with _shared_lock:
        clients = list(_shared_clients.values())
        _shared_clients.clear()

    for client in clients:
        client.close()
