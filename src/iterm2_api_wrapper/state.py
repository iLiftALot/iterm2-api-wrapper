from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Concatenate, Coroutine

from iterm2 import app, connection, profile, prompt, session, tab, window
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from iterm2_api_wrapper.utils import pp


def _validate_state[**P, T](
    method: Callable[Concatenate[iTermState, P], Coroutine[Any, Any, T]],
) -> Callable[Concatenate[iTermState, P], Coroutine[Any, Any, T]]:
    """Decorator that validates and refreshes state before method execution."""

    @wraps(method)
    async def async_wrapper(self: iTermState, *args: P.args, **kwargs: P.kwargs) -> T:
        try:
            await self.ensure_state()
            return await method(self, *args, **kwargs)
        except (ConnectionClosed, ConnectionClosedError):
            pp("Connection closed, refreshing state and retrying...")
            await self.ensure_state()
            return await method(self, *args, **kwargs)

    if not asyncio.iscoroutinefunction(method):
        raise TypeError(
            "The _validate_state decorator can only be applied to async methods. "
            f"iTermState.{method!r} is not asynchronous."
        )

    return async_wrapper


@dataclass
class iTermState:
    """Global iTerm2 state."""

    connection: connection.Connection
    app: app.App
    window: window.Window
    tab: tab.Tab
    session: session.Session
    profile: profile.Profile

    # refresh_callback is set in client.py after initialization
    refresh_callback: Callable[[], Awaitable[Any]] | None = None
    is_hotkey_window: bool = False

    def refresh_from(self, new_state: Any) -> None:
        """
        Refresh this state in-place from another state instance.

        `iTermClient` uses this to preserve the identity of `client.state` while
        still updating all underlying iTerm2 objects after a reconnect.
        """
        if not isinstance(new_state, iTermState):
            raise TypeError(
                f"refresh_from expects an iTermState; got {type(new_state).__name__!r}"
            )

        self.connection = new_state.connection
        self.app = new_state.app
        self.window = new_state.window
        self.tab = new_state.tab
        self.session = new_state.session
        self.profile = new_state.profile
        self.is_hotkey_window = new_state.is_hotkey_window
        self.refresh_callback = new_state.refresh_callback

    async def ensure_state(
        self,
        refresh_callback: Callable[[], Awaitable[Any]] | Awaitable[Any] | None = None,
    ) -> None:
        """Ensure the state is valid, refreshing if needed."""
        if await self.validated_state():
            return

        callback = refresh_callback or self.refresh_callback
        if callback is None:
            raise RuntimeError("No refresh callback provided to ensure_state")

        new_state = await (callback() if callable(callback) else callback)
        self.refresh_from(new_state)

    async def validated_state(self) -> bool:
        """Validate state by checking if iTerm2 objects are still active."""
        try:
            # Check connection is alive
            if not self.online:
                return False

            # Check app still responds
            current_app: None | app.App = await app.async_get_app(
                self.connection, create_if_needed=False
            )
            if current_app is None:
                return False
            self.app = current_app

            # Check session still exists
            if (
                new_session := current_app.get_session_by_id(
                    self.session.session_id, include_buried=False
                )
            ) is None:
                return False
            self.session = new_session

            # Refresh owning window/tab from the session
            new_window, new_tab = current_app.get_window_and_tab_for_session(new_session)
            if new_window is None or new_tab is None:
                return False
            self.window = new_window
            self.tab = new_tab

            return True
        except Exception:
            return False

    @property
    def online(self) -> bool:
        """Check if connection is online."""
        return getattr(self.connection.websocket, "open", False)

    @property
    def debug(self) -> bool:
        """Check if connection is in debug mode."""
        loop = self.connection.loop
        if loop is None:
            return False
        return loop.get_debug()

    @_validate_state
    async def get_cwd(self) -> str | None:
        """Get current working directory of the last active session."""
        last_prompt: None | prompt.Prompt = await prompt.async_get_last_prompt(
            connection=self.connection, session_id=self.session.session_id
        )
        return getattr(last_prompt, "working_directory", None)

    @_validate_state
    async def get_tab_title(self) -> str:
        """Get tab title."""
        tab_title: str = await self.tab.async_get_variable("title")
        return tab_title

    @_validate_state
    async def get_session_profile(self) -> profile.Profile:
        """Get session profile."""
        session_profile: profile.Profile = await self.session.async_get_profile()
        return session_profile

    @_validate_state
    async def send_command(self, command: str, broadcast: bool = False) -> None:
        """Send a command to the iTerm2 session."""
        broadcast = not broadcast
        await self.session.async_send_text(command + "\n", suppress_broadcast=broadcast)

    def asdict(self) -> dict[str, Any]:
        """Convert iTermState to dictionary."""
        return {
            key: {k: v for k, v in value.__dict__.items()}
            if hasattr(value, "__dict__")
            else value
            for key, value in self.__dict__.items()
            if key != "refresh_callback"
        }
