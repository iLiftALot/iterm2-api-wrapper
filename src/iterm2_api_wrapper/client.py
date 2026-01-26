from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager, contextmanager
from threading import Thread
from typing import Any, AsyncGenerator, Callable, Coroutine, Generator, Unpack

from iterm2.connection import Connection

from iterm2_api_wrapper.main import iTermState, run_iterm_setup
from iterm2_api_wrapper.param_types import iTermSetupKwargs


class iTermClient:
    def __init__(
        self,
        coro: Callable[[Connection, iTermSetupKwargs], Coroutine[Any, Any, iTermState]]
        | None = None,
        *,
        timeout: float | None = None,
        **kwargs: Unpack[iTermSetupKwargs],
    ) -> None:
        self._coro = coro or run_iterm_setup
        self._kwargs = kwargs
        self._timeout = timeout
        self._loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._lock = asyncio.Lock()
        self._state: iTermState = asyncio.run_coroutine_threadsafe(
            self._init_async(), self._loop
        ).result(timeout=self._timeout)

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Get the event loop used by the iTermClient."""
        return self._loop

    @property
    def state(self) -> iTermState:
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

    async def _init_async(self) -> iTermState:
        conn: Connection = await Connection.async_create()
        state: iTermState = await self._coro(conn, **self._kwargs)
        state.refresh_callback = self._init_async
        return state

    async def _refresh_async(self) -> None:
        async with self._lock:
            new_state: iTermState = await self._init_async()
            for attr in (
                "connection",
                "app",
                "window",
                "tab",
                "session",
                "profile",
                "is_hotkey_window",
                "refresh_callback",
            ):
                setattr(self._state, attr, getattr(new_state, attr))

    def close(self) -> None:
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        self._thread.join()

        if not self._loop.is_closed():
            self._loop.close()

    @contextmanager
    def state_manager(self) -> Generator[iTermState]:
        """
        Context manager to ensure that the iTermState is valid,
        refreshing it if necessary.

        Useful when accessing multiple raw state attributes.

        ---

        :yield: The current iTermState, refreshed if necessary.
        :rtype: ``iTermState``
        """
        state = self.get_state()
        try:
            yield state
        finally:
            self.close()

    @asynccontextmanager
    async def state_manager_async(self) -> AsyncGenerator[iTermState]:
        """
        Async context manager to ensure that the iTermState is valid,
        refreshing it if necessary.

        Useful when accessing multiple raw state attributes.

        ---

        :yield: The current iTermState, refreshed if necessary.
        :rtype: ``iTermState``
        """
        state = await self.get_state_async()
        try:
            yield state
        finally:
            self.close()

    def get_state(self) -> iTermState:
        """
        Ensure that the iTermState is valid, refreshing it if necessary.

        Only call this method from outside of the event loop.

        ---

        :return: The current iTermState, refreshed if necessary.
        :rtype: ``iTermState``
        """
        return self._ensure_state()

    async def get_state_async(self) -> iTermState:
        """
        Ensure that the iTermState is valid, refreshing it if necessary.
        return await self._ensure_state_async()

        Only call this method from within the event loop.

        ---

        :return: The current iTermState, refreshed if necessary.
        :rtype: ``iTermState``
        """
        return await self._ensure_state_async()

    def _ensure_state(self) -> iTermState:
        """Internal method. Use get_state instead."""

        async def _invoke() -> iTermState:
            try:
                async with self._lock:
                    await self._state.ensure_state(refresh_callback=self._init_async)
            except Exception:
                await self._refresh_async()

            return self._state

        return asyncio.run_coroutine_threadsafe(_invoke(), self._loop).result(
            timeout=self._timeout
        )

    async def _ensure_state_async(self) -> iTermState:
        """Internal method. Use get_state_async instead."""

        try:
            async with self._lock:
                await self._state.ensure_state(refresh_callback=self._init_async)
        except Exception:
            await self._refresh_async()

        return self._state

    def __enter__(self) -> iTermClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if not self._loop.is_closed():
            self.close()

    def __del__(self) -> None:
        if not self._loop.is_closed():
            self.close()
