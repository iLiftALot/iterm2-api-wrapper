from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, Concatenate, Coroutine, ParamSpec, Unpack

from AppKit import (
    NSRunningApplication,       # ty:ignore[unresolved-import]
    NSWorkspace,                # ty:ignore[unresolved-import]
    NSWorkspaceLaunchAndHide,   # ty:ignore[unresolved-import]
)
from iterm2 import app, connection, profile, prompt, session, tab, window
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from iterm2_api_wrapper.param_types import (
    iTermSessionKwargs,
    iTermSetupKwargs,
    iTermTabKwargs,
)
from iterm2_api_wrapper.utils import pp, run_until_complete


P = ParamSpec("P")


def _validate_state[T](
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
    refresh_callback: Callable[[], Coroutine[Any, Any, iTermState]] | None = None
    is_hotkey_window: bool = False

    async def ensure_state(
        self,
        refresh_callback: Callable[[], Coroutine[Any, Any, iTermState]]
        | Coroutine[Any, Any, iTermState]
        | None = None,
    ) -> None:
        """Ensure the state is valid, refreshing if needed."""
        if await self.validated_state():
            return

        callback = refresh_callback or self.refresh_callback
        if callback is None:
            raise RuntimeError("No refresh callback provided to ensure_state")

        new_state: iTermState = await (callback() if callable(callback) else callback)

        self.connection = new_state.connection
        self.app = new_state.app
        self.window = new_state.window
        self.tab = new_state.tab
        self.session = new_state.session
        self.profile = new_state.profile
        self.is_hotkey_window = new_state.is_hotkey_window

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
            for key, value in self.__dict__.items()
            if key != "refresh_callback"
        }


async def get_connection() -> connection.Connection:
    conn: connection.Connection = await connection.Connection.async_create()
    return conn


async def get_default_profile(
    connection_instance: connection.Connection,
) -> profile.Profile:
    default_profile: profile.Profile = await profile.Profile.async_get_default(
        connection_instance
    )
    return default_profile


async def get_app(connection_instance: connection.Connection) -> app.App:
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
    iterm2_windows: list[window.Window] = app.windows
    selected_window: window.Window | None = app.current_window

    window_candidates: list[window.Window] = []
    for iterm2_window in iterm2_windows:
        # window_tab: tab.Tab = iterm2_window.current_tab or iterm2_window.tabs[0]
        window_tab: tab.Tab = await get_tab(
            window=iterm2_window, profile=profile, new_tab=False, order_window_front=False
        )
        # window_session: session.Session = window_tab.current_session or window_tab.all_sessions[0]
        window_session: session.Session = await get_session(
            tab=window_tab, select_tab=True, order_window_front=False
        )
        window_profile_name: str = await window_session.async_get_variable("profileName")
        is_hotkey_window: bool = bool(
            await iterm2_window.async_get_variable("isHotkeyWindow")
        )
        if window_profile_name == profile.name:
            if is_hotkey_window:
                selected_window = iterm2_window
                break
            window_candidates.append(iterm2_window)

    if selected_window is None:
        if window_candidates:
            selected_window = window_candidates[0]
        elif iterm2_windows:
            selected_window = iterm2_windows[0]
        else:
            selected_window = await window.Window.async_create(
                connection_instance, profile.name
            )

    assert selected_window is not None, "Could not get or create iTerm2 window"
    await selected_window.async_activate()
    return selected_window


async def get_tab(
    window: window.Window, profile: profile.Profile, **kwargs: Unpack[iTermTabKwargs]
) -> tab.Tab:
    new_tab: bool = kwargs.get("new_tab", False)
    iterm2_tabs: list[tab.Tab] = window.tabs
    selected_tab: tab.Tab | None = window.current_tab

    for iterm2_tab in iterm2_tabs:
        tab_session: session.Session = await get_session(
            tab=iterm2_tab, profile=profile, select_tab=True, order_window_front=False
        )
        tab_profile_name: str = await tab_session.async_get_variable("profileName")
        if tab_profile_name == profile.name:
            selected_tab = iterm2_tab
            break

    if not new_tab:
        selected_tab = selected_tab or window.tabs[0] if window.tabs else None
    if new_tab or selected_tab is None:
        selected_tab = await window.async_create_tab(profile=profile.name)

    assert selected_tab is not None, "Could not get or create iTerm2 tab"
    await selected_tab.async_activate(
        order_window_front=kwargs.get("order_window_front", False)
    )

    return selected_tab


async def get_session(
    tab: tab.Tab,
    profile: profile.Profile | None = None,
    **kwargs: Unpack[iTermSessionKwargs],
) -> session.Session:
    iterm2_sessions: list[session.Session] = tab.all_sessions
    selected_session: session.Session | None = tab.current_session
    profile_name: str = getattr(profile, "name", None) or await tab.async_get_variable(
        "profileName"
    )

    for iterm2_session in iterm2_sessions:
        session_profile_name: str = await iterm2_session.async_get_variable("profileName")
        if session_profile_name == profile_name:
            selected_session = iterm2_session
            break

    if selected_session is None:
        raise RuntimeError("Could not find matching session in tab")

    await selected_session.async_activate(
        select_tab=kwargs.get("select_tab", True),
        order_window_front=kwargs.get("order_window_front", False),
    )
    return selected_session


def _activate_iterm_app() -> None:
    """Activate iTerm2 application using pyobjc (AppKit)."""
    bundle = "com.googlecode.iterm2"
    ws = NSWorkspace.sharedWorkspace()
    if not NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle):
        ok, _ = (
            ws.launchAppWithBundleIdentifier_options_additionalEventParamDescriptor_launchIdentifier_(
                bundle,
                # NSWorkspaceLaunchDefault,
                NSWorkspaceLaunchAndHide,
                # NSWorkspaceLaunchAndPrint,
                # NSWorkspaceLaunchNewInstance,
                None,
                None,
            )
        )
        if not ok:
            raise RuntimeError("Could not launch iTerm2 application")


async def setup_iterm(
    connection_instance: connection.Connection, **kwargs: Unpack[iTermSetupKwargs]
) -> iTermState:
    """Setup window."""
    _activate_iterm_app()
    app_instance: app.App = await get_app(connection_instance=connection_instance)
    profile_instance: profile.Profile = await get_default_profile(
        connection_instance=connection_instance
    )
    window_instance: window.Window = await get_window(
        app_instance, connection_instance, profile_instance
    )
    tab_instance: tab.Tab = await get_tab(
        window=window_instance, profile=profile_instance, **kwargs
    )
    session_instance: session.Session = await get_session(
        tab=tab_instance, profile=profile_instance, **kwargs
    )

    # Check hotkey window status here (we're already async on the correct loop)
    is_hotkey_window = bool(await window_instance.async_get_variable("isHotkeyWindow"))

    return iTermState(
        connection=connection_instance,
        app=app_instance,
        profile=profile_instance,
        window=window_instance,
        tab=tab_instance,
        session=session_instance,
        is_hotkey_window=is_hotkey_window,
    )


async def run_iterm_setup(
    connection_instance: connection.Connection, **kwargs: Unpack[iTermSetupKwargs]
) -> iTermState:
    """Run iTerm2 setup. This can also be called directly."""
    global_iterm_state: iTermState = await setup_iterm(
        connection_instance=connection_instance, **kwargs
    )

    if global_iterm_state.debug or kwargs.get("debug", False):
        pp("Initialized iTermState:")
        pp(global_iterm_state.asdict())

    return global_iterm_state


def init(retry: bool, **kwargs: Unpack[iTermSetupKwargs]) -> iTermState:
    """Main function to run iTerm2 setup."""

    global_state: iTermState = run_until_complete(run_iterm_setup, retry, **kwargs)
    return global_state


if __name__ == "__main__":
    debug = "--debug" in sys.argv[1:]
    global_state: iTermState = init(
        retry=True, debug=debug, new_tab=False, select_tab=True, order_window_front=False
    )
