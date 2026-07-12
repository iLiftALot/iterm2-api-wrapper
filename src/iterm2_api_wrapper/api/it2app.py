from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast, overload

from iterm2 import app, rpc, session, tab, tmux, window

from .._logging import PrettyLog
from .it2connection import add_disconnect_callback


if TYPE_CHECKING:
    from iterm2.api_pb2 import ListSessionsResponse, ServerOriginatedMessage
    from iterm2.connection import Connection as IT2Connection

    from .it2connection import Connection
    from .it2session import Session
    from .it2tab import Tab
    from .it2window import Window


log = PrettyLog.get_logger(__name__)


class App(app.App):
    """Typed/safe wrapper for upstream iTerm2 App.

    The upstream App focus refresh path can recurse indefinitely when iTerm2
    reports a selected tab/session that is not present in the freshly fetched
    layout. This wrapper adds a small re-entrancy guard around focus refresh.
    """

    def __init__(self, connection, windows, buried_sessions):
        super().__init__(connection, windows, buried_sessions)
        self._focus_refresh_in_progress = False
        self._nested_focus_refresh_skips = 0

    @staticmethod
    async def async_construct(connection: Connection) -> App:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Construct a wrapper App instead of upstream iterm2.app.App."""
        response: ServerOriginatedMessage = await rpc.async_list_sessions(cast("IT2Connection", connection))
        list_sessions_response: ListSessionsResponse = response.list_sessions_response

        windows = app.App._windows_from_list_sessions_response(connection, list_sessions_response)
        buried_sessions = app.App._buried_sessions_from_list_sessions_response(connection, list_sessions_response)

        wrapper_app = App(connection, windows, buried_sessions)

        session.Session.delegate = wrapper_app
        tab.Tab.delegate = wrapper_app
        window.Window.delegate = wrapper_app
        tmux.DELEGATE = wrapper_app

        await wrapper_app._async_listen()
        await wrapper_app.async_refresh_focus()
        await wrapper_app.async_refresh_broadcast_domains()

        return wrapper_app

    async def async_refresh_focus(self) -> None:
        """Update focus state, suppressing recursive focus→layout→focus refresh loops."""
        if self._focus_refresh_in_progress:
            self._nested_focus_refresh_skips += 1
            return

        self._focus_refresh_in_progress = True
        self._nested_focus_refresh_skips = 0

        try:
            await super().async_refresh_focus()
        finally:
            skipped = self._nested_focus_refresh_skips
            self._focus_refresh_in_progress = False
            self._nested_focus_refresh_skips = 0

            if skipped:
                log.debug(
                    "Skipped nested iTerm2 focus refresh call(s) to avoid upstream App recursion.",
                    {"skipped": skipped},
                )

    @property
    def windows(self) -> list[Window]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list["Window"], super().windows)

    @property
    def current_window(self) -> Window | None:
        return cast("Window | None", super().current_window)

    def get_window_by_id(self, window_id: str) -> Window | None:
        return cast("Window | None", super().get_window_by_id(window_id))

    def get_session_by_id(self, session_id: str, include_buried: bool = True) -> Session | None:
        return cast("Session | None", super().get_session_by_id(session_id, include_buried))

    def get_tab_by_id(self, tab_id: str) -> Tab | None:
        return cast("Tab | None", super().get_tab_by_id(tab_id))

    def get_window_for_tab(self, tab_id: str) -> Window | None:
        return cast("Window | None", super().get_window_for_tab(tab_id))

    def get_window_and_tab_for_session(self, session: Session) -> tuple[None, None] | tuple[Window, Tab]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(tuple["Window", "Tab"] | tuple[None, None], super().get_window_and_tab_for_session(session))

    async def window_delegate_get_tab_by_id(self, tab_id: str) -> Tab | None:
        return cast("Tab | None", await super().window_delegate_get_tab_by_id(tab_id))

    async def tab_delegate_get_window_by_id(self, window_id: str) -> Window | None:
        return cast("Window | None", await super().tab_delegate_get_window_by_id(window_id))

    def session_delegate_get_tab(self, session) -> Tab | None:
        return cast("Tab | None", super().session_delegate_get_tab(session))


@overload
async def async_get_app(connection: Connection, create_if_needed: Literal[True]) -> App: ...
@overload
async def async_get_app(connection: Connection, create_if_needed: Literal[False]) -> App | None: ...
@overload
async def async_get_app(connection: Connection, create_if_needed: bool = ...) -> App | None: ...
async def async_get_app(connection: Connection, create_if_needed: bool = True) -> App | None:
    """Return this package's App wrapper singleton, creating or replacing upstream App.instance if needed.

    :param connection: The connection to iTerm2.
    :type connection: :class:`Connection`
    :param create_if_needed: If `True`, create the global :class:`App` instance
      if one does not already exists. If `False`, do not create it.

    :returns: The global :class:`App` instance. If :param:`create_if_needed` is False,
    then this may return `None` if no such instance exists.
    :rtype: :class:`App` | None
    """
    current = app.App.instance
    created_wrapper = False

    if current is None:
        if create_if_needed:
            app.App.instance = await App.async_construct(connection)
            created_wrapper = True
    elif not isinstance(current, App):
        # Defensive: if upstream created its singleton before our wrapper, replace it.
        app.App.instance = await App.async_construct(connection)
        created_wrapper = True
    else:
        await current.async_refresh()

    if created_wrapper:
        add_disconnect_callback(app.invalidate_app)

    return cast(App | None, app.App.instance)
