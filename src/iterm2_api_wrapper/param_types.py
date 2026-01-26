from typing import Any, Callable, Coroutine, Self, TypedDict

from iterm2 import app, connection, profile, session, tab, window


class iTermTabKwargs(TypedDict, total=False):
    new_tab: bool
    """Whether to open a new tab for the session."""
    order_window_front: bool
    """Whether the window this session is in should be brought to the front and given keyboard focus."""


class iTermSessionKwargs(TypedDict, total=False):
    select_tab: bool
    """Whether the tab this session is in should be selected."""
    order_window_front: bool
    """Whether the window this session is in should be brought to the front and given keyboard focus."""


class iTermSetupKwargs(iTermTabKwargs, iTermSessionKwargs, total=False):
    debug: bool
    """Whether to enable debug logging."""


class iTermStateKwargs(TypedDict, total=True):
    connection: connection.Connection
    app: app.App
    window: window.Window
    tab: tab.Tab
    session: session.Session
    profile: profile.Profile

    refresh_callback: Callable[[], Coroutine[Any, Any, Self]] | None
    """A callback to refresh the iTermState."""
    is_hotkey_window: bool
    """Whether the current window is a hotkey window."""
