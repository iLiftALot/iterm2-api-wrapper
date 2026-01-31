from __future__ import annotations

from typing import Unpack
import subprocess
from iterm2 import app, connection, profile, session, tab, window

from iterm2_api_wrapper.mac.platform_macos import activate_iterm_app
from iterm2_api_wrapper.typings import iTermSetupKwargs
from iterm2_api_wrapper.state import iTermState
from iterm2_api_wrapper.utils import pp


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


async def _get_app(connection_instance: connection.Connection) -> app.App:
    app_instance: None | app.App = await app.async_get_app(
        connection_instance, create_if_needed=True
    )
    if app_instance is None:
        raise RuntimeError("Could not get iTerm2 app")
    return app_instance


async def _get_window(
    app: app.App, connection_instance: connection.Connection, profile: profile.Profile
) -> window.Window:
    selected_window: window.Window | None = app.current_window
    if selected_window is None:
        selected_window = await window.Window.async_create(
            connection_instance, profile.name
        )

    assert selected_window is not None, "Could not get or create iTerm2 window"
    return selected_window


async def _get_tab(window: window.Window, profile: profile.Profile) -> tab.Tab:
    selected_tab: tab.Tab | None = window.current_tab
    if selected_tab is None:
        selected_tab = await window.async_create_tab(profile=profile.name)

    assert selected_tab is not None, "Could not get or create iTerm2 tab"
    return selected_tab


async def _get_session(tab: tab.Tab) -> session.Session:
    selected_session: session.Session | None = tab.current_session
    if selected_session is None:
        raise RuntimeError("Could not find matching session in tab")

    return selected_session


def _check_api_enabled():
    """Check if the Python API is enabled in iTerm2 preferences."""
    try:
        result = subprocess.run(
            ["defaults", "read", "com.googlecode.iterm2", "EnableAPIServer"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "1"
    except Exception:
        return False


def _enable_api():
    """Enable the Python API in iTerm2 preferences."""
    try:
        subprocess.run(
            [
                "defaults",
                "write",
                "com.googlecode.iterm2.plist",
                "EnableAPIServer",
                "-bool",
                "true",
            ],
            check=True,
            capture_output=True,
        )
        return True
    except Exception:
        return False


async def _setup_iterm(
    connection_instance: connection.Connection, **kwargs: Unpack[iTermSetupKwargs]
) -> iTermState:
    activate_iterm_app()
    if not _check_api_enabled():
        raise RuntimeError(
            "iTerm2 Python API is not enabled. Please enable it in iTerm2 Preferences > General > Magic."
        )

    app_instance: app.App = await _get_app(connection_instance=connection_instance)
    profile_instance: profile.Profile = await get_default_profile(
        connection_instance=connection_instance
    )
    window_instance: window.Window = await _get_window(
        app_instance, connection_instance, profile_instance
    )
    tab_instance: tab.Tab = await _get_tab(
        window=window_instance, profile=profile_instance
    )
    session_instance: session.Session = await _get_session(tab=tab_instance)

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

    global_iterm_state: iTermState = await _setup_iterm(
        connection_instance=connection_instance, **kwargs
    )

    if global_iterm_state.debug or kwargs.get("debug", False):
        pp("Initialized iTermState:")
        pp(global_iterm_state.asdict())

    return global_iterm_state
