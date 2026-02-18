from __future__ import annotations

import os
import subprocess
from typing import Unpack

from iterm2 import app, connection, profile, session, tab, window

from iterm2_api_wrapper.logging import PrettyLog
from iterm2_api_wrapper.mac.platform_macos import activate_iterm_app
from iterm2_api_wrapper.state import iTermState
from iterm2_api_wrapper.typings import iTermSetupKwargs


log = PrettyLog(__name__)


async def get_connection() -> connection.Connection:
    conn: connection.Connection = await connection.Connection.async_create()
    return conn


async def get_profile(
    connection_instance: connection.Connection, profile_name: str | None = None
) -> profile.Profile:
    async def get_default_profile() -> profile.Profile:
        default_profile: profile.Profile = await profile.Profile.async_get_default(
            connection_instance
        )
        return default_profile

    if profile_name is None:
        return await get_default_profile()

    profiles = await profile.Profile.async_get(connection=connection_instance)
    for p in profiles:
        if p.name == profile_name:
            return p

    raise ValueError(f"Profile with name '{profile_name}' not found")


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


async def _get_tab_with_session(
    window: window.Window, profile: profile.Profile, new_tab: bool = False
) -> tuple[tab.Tab, session.Session]:
    log.debug(f"Looking for existing tab with profile: {profile.name}")
    iterm_mcp_tag = f"pyterm-session:{profile.name}"

    async def default_tab_with_session(
        override_new_tab: bool = False,
    ) -> tuple[tab.Tab, session.Session]:
        selected_tab, selected_session = None, None

        if not new_tab and not override_new_tab:
            for t in window.tabs:
                current_session = t.current_session
                if current_session is None:
                    continue
                tab_title = await t.async_get_variable("title")
                session_name = current_session.name
                if iterm_mcp_tag in [tab_title, session_name]:
                    selected_tab, selected_session = t, current_session
                    break

        if new_tab is True or override_new_tab is True or (not selected_tab or not selected_session):
            selected_tab = await window.async_create_tab(profile=profile.name)

        assert selected_tab is not None, "Could not get or create iTerm2 tab"
        selected_session = selected_tab.current_session
        assert selected_session is not None, "Could not get current session in tab"
        return selected_tab, selected_session

    if new_tab is True:
        log.debug("Creating new tab due to new_tab=True")
        return await default_tab_with_session()

    for t in window.tabs:
        current_session = t.current_session
        if current_session is None:
            continue
        # profile_name = (await current_session.async_get_profile()).name
        profile_name = await current_session.async_get_variable("profileName")
        session_name = current_session.name
        # log.debug(f"Checking tab: {session_name=} - {profile_name=}")
        tab_title = await t.async_get_variable("title")
        if profile.name == profile_name and iterm_mcp_tag in [tab_title, session_name]:
            log.debug(f"Found match: {session_name=} - {profile.name=} - {profile_name=}")
            selected_tab, selected_session = t, current_session
            break
    else:
        log.debug("No matching tab found; creating new tab")
        selected_tab, selected_session = await default_tab_with_session(
            override_new_tab=True
        )

    tab_title = await selected_tab.async_get_variable("title")
    session_name = selected_session.name
    if iterm_mcp_tag not in [tab_title, session_name]:
        log.debug(f"Renaming tab and session to '{iterm_mcp_tag}'")
        await selected_tab.async_set_title(iterm_mcp_tag)
        await selected_session.async_set_name(iterm_mcp_tag)

    return selected_tab, selected_session


def _check_api_enabled():
    """Check if the Python API is enabled in iTerm2 preferences."""
    try:
        result = subprocess.run(
            [
                "defaults",
                "read",
                "com.googlecode.iterm2",
                # "com.googlecode.iterm2.plist",
                "EnableAPIServer",
            ],
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
                "com.googlecode.iterm2",
                # "com.googlecode.iterm2.plist",
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
            "iTerm2 Python API is not enabled. Enable it in iTerm2 Preferences > General > Magic."
        )

    app_instance: app.App = await _get_app(connection_instance=connection_instance)
    dedicated_profile_name = kwargs.get("dedicated_profile_name") or os.getenv(
        "ITERM2_DEDICATED_PROFILE", None
    )
    profile_instance: profile.Profile = await get_profile(
        connection_instance=connection_instance, profile_name=dedicated_profile_name
    )
    window_instance: window.Window = await _get_window(
        app_instance, connection_instance, profile_instance
    )
    tab_instance, session_instance = await _get_tab_with_session(
        window=window_instance,
        profile=profile_instance,
        new_tab=kwargs.get("new_tab", False),
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

    global_iterm_state: iTermState = await _setup_iterm(
        connection_instance=connection_instance, **kwargs
    )

    if global_iterm_state.debug or kwargs.get("debug", False):
        log.debug("Initialized iTermState:")
        log.debug(global_iterm_state.asdict())

    return global_iterm_state
