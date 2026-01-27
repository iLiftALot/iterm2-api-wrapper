from __future__ import annotations

from typing import Unpack

from iterm2 import app, connection, profile, session, tab, window

from iterm2_api_wrapper.mac.platform_macos import activate_iterm_app
from iterm2_api_wrapper.param_types import iTermSetupKwargs
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
    window: window.Window,
    profile: profile.Profile,
    new_tab: bool = False,
    order_window_front: bool = False,
) -> tab.Tab:
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
    await selected_tab.async_activate(order_window_front=order_window_front)

    return selected_tab


async def get_session(
    tab: tab.Tab,
    profile: profile.Profile | None = None,
    select_tab: bool = True,
    order_window_front: bool = False,
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
        select_tab=select_tab, order_window_front=order_window_front
    )
    return selected_session


async def setup_iterm(
    connection_instance: connection.Connection, **kwargs: Unpack[iTermSetupKwargs]
) -> iTermState:
    """Setup window."""
    activate_iterm_app()
    app_instance: app.App = await get_app(connection_instance=connection_instance)
    profile_instance: profile.Profile = await get_default_profile(
        connection_instance=connection_instance
    )
    window_instance: window.Window = await get_window(
        app_instance, connection_instance, profile_instance
    )
    tab_instance: tab.Tab = await get_tab(
        window=window_instance,
        profile=profile_instance,
        new_tab=kwargs.get("new_tab", False),
        order_window_front=kwargs.get("order_window_front", False),
    )
    session_instance: session.Session = await get_session(
        tab=tab_instance,
        profile=profile_instance,
        select_tab=kwargs.get("select_tab", True),
        order_window_front=kwargs.get("order_window_front", False),
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
