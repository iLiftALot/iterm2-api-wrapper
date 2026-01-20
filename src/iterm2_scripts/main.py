from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Concatenate, ParamSpec

from iterm2 import (
    app,
    connection,
    profile,
    prompt,
    run_until_complete,
    session,
    tab,
    window,
)

P = ParamSpec("P")

_STATE_REFRESH_LOCK = asyncio.Lock()


def validate_state[T](
    method: Callable[Concatenate[GlobaliTermState, P], Awaitable[T]],
) -> Callable[Concatenate[GlobaliTermState, P], Awaitable[T]]:
    """Decorator that validates and refreshes state before method execution."""

    @wraps(method)
    async def async_wrapper(
        self: GlobaliTermState, *args: P.args, **kwargs: P.kwargs
    ) -> T:
        """Wrapper that validates state before method execution."""
        await self.ensure_state()
        return await method(self, *args, **kwargs)

    if not asyncio.iscoroutinefunction(method):
        raise TypeError(
            "The validate_state decorator can only be applied to async methods. "
            f"GlobaliTermState.{method!r} is not asynchronous."
        )

    return async_wrapper


@dataclass
class GlobaliTermState:
    """Global iTerm2 state."""

    connection: connection.Connection
    app: app.App
    window: window.Window
    tab: tab.Tab
    session: session.Session
    profile: profile.Profile

    async def ensure_state(self) -> None:
        """Ensure the state is valid, refreshing if needed."""
        if await self.validated_state():
            return
        async with _STATE_REFRESH_LOCK:
            if await self.validated_state():
                return
            if self.connection is None:
                raise RuntimeError(
                    "iTerm2 connection unavailable; restart the script to reconnect."
                )
            new_state: GlobaliTermState = await run_iterm_setup(self.connection)
            self.connection = new_state.connection
            self.app = new_state.app
            self.window = new_state.window
            self.tab = new_state.tab
            self.session = new_state.session
            self.profile = new_state.profile

    async def validated_state(self) -> bool:
        """Validate state by checking if iTerm2 objects are still active."""
        try:
            # Check connection is alive
            if self.connection is None:
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
            # Refresh session reference
            self.session = new_session

            # Refresh owning window/tab from the session
            new_window, new_tab = current_app.get_window_and_tab_for_session(
                new_session
            )
            if new_window is None or new_tab is None:
                return False
            self.window = new_window
            self.tab = new_tab

            return True
        except Exception:
            return False

    @validate_state
    async def get_cwd(self) -> str | None:
        """Get current working directory."""
        last_prompt: None | prompt.Prompt = await prompt.async_get_last_prompt(
            connection=self.connection, session_id=self.session.session_id
        )
        return last_prompt.working_directory if last_prompt else None

    @validate_state
    async def get_current_tab(self) -> tab.Tab | None:
        """Get current profile."""
        return self.window.current_tab

    @validate_state
    async def get_session_profile(self) -> profile.Profile:
        """Get session profile."""
        session_profile: profile.Profile = await self.session.async_get_profile()
        return session_profile


async def get_default_profile(
    connection_instance: connection.Connection,
) -> profile.Profile:
    """Get default profile."""
    default_profile: profile.Profile = await profile.Profile.async_get_default(
        connection_instance
    )
    return default_profile


async def get_connection() -> connection.Connection:
    """Get REPL connection to iTerm2."""
    iterm2_connection: connection.Connection = (
        await connection.Connection().async_create()
    )
    return iterm2_connection


async def get_app(connection_instance: connection.Connection) -> app.App:
    """Get iTerm2 app."""
    app_instance: None | app.App = await app.async_get_app(
        connection_instance, create_if_needed=True
    )
    if app_instance is None:
        raise RuntimeError("Could not get iTerm2 app")
    await app_instance.async_activate(raise_all_windows=True, ignoring_other_apps=True)
    return app_instance


async def get_window(
    app: app.App, connection_instance: connection.Connection, profile: profile.Profile
) -> window.Window:
    """Get current window."""
    iterm2_window: window.Window | None = (
        app.current_window or app.windows[-1] if app.windows else None
    )

    if iterm2_window is None:
        iterm2_window: window.Window | None = await window.Window.async_create(
            connection_instance, profile.name
        )

    iterm2_window: window.Window = (
        app.windows[-1] if not iterm2_window else iterm2_window
    )
    await iterm2_window.async_activate()

    return iterm2_window


async def get_tab(
    window: window.Window, profile: profile.Profile, *, new_tab: bool = False
) -> tab.Tab:
    """Get current tab."""

    if not new_tab:
        tab_instance: tab.Tab | None = (
            window.current_tab or window.tabs[-1] if window.tabs else None
        )
    if new_tab or tab_instance is None:
        tab_instance: tab.Tab | None = await window.async_create_tab(
            profile=profile.name
        )

    tab_instance: tab.Tab = window.tabs[-1] if not tab_instance else tab_instance
    await tab_instance.async_activate(order_window_front=True)

    return tab_instance


async def get_session(tab: tab.Tab) -> session.Session:
    """Get current session."""
    session_instance: session.Session | None = (
        tab.current_session or tab.all_sessions[-1] if tab.all_sessions else None
    )
    if session_instance is None:
        raise RuntimeError("Could not get iTerm2 session")
    await session_instance.async_activate(select_tab=True, order_window_front=True)
    return session_instance


async def setup_iterm(connection_instance: connection.Connection) -> GlobaliTermState:
    """Setup window."""
    app_instance: app.App = await get_app(connection_instance=connection_instance)
    profile_instance: profile.Profile = await get_default_profile(
        connection_instance=connection_instance
    )
    window_instance: window.Window = await get_window(
        app_instance, connection_instance, profile_instance
    )
    tab_instance: tab.Tab = await get_tab(
        window=window_instance, profile=profile_instance, new_tab=True
    )
    session_instance: session.Session = await get_session(tab=tab_instance)

    return GlobaliTermState(
        connection=connection_instance,
        app=app_instance,
        profile=profile_instance,
        window=window_instance,
        tab=tab_instance,
        session=session_instance,
    )


async def run_iterm_setup(
    connection_instance: connection.Connection | None,
    *,
    allow_repl_connection: bool = False,
) -> GlobaliTermState:
    if connection_instance is None:
        if not allow_repl_connection:
            raise RuntimeError(
                "Connection is required when running under iterm2.run_until_complete."
            )
        connection_instance = await get_connection()
    global_iterm_state: GlobaliTermState = await setup_iterm(connection_instance)
    return global_iterm_state


async def main(connection_instance: connection.Connection):
    return await run_iterm_setup(connection_instance)


if __name__ == "__main__":
    debug = "--debug" in sys.argv
    global_state = run_until_complete(coro=main, retry=True, debug=debug)

    if debug and global_state:
        print("iTerm2 Global State:")
        print(global_state)
