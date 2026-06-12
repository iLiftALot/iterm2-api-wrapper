from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast, overload

from iterm2 import app


if TYPE_CHECKING:
    from iterm2.connection import Connection as IT2Connection

    from .it2connection import Connection
    from .it2session import Session
    from .it2tab import Tab
    from .it2window import Window


class App(app.App):
    @property
    def windows(self) -> list[Window]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Window], super().windows)

    @property
    def current_window(self) -> Window | None:
        return cast(Window | None, super().current_window)

    def get_window_by_id(self, window_id: str) -> Window | None:
        return cast(Window | None, super().get_window_by_id(window_id))

    def get_session_by_id(self, session_id: str, include_buried: bool = True) -> Session | None:
        return cast(Session | None, super().get_session_by_id(session_id, include_buried))

    def get_tab_by_id(self, tab_id: str) -> Tab | None:
        return cast(Tab | None, super().get_tab_by_id(tab_id))

    def get_window_for_tab(self, tab_id: str) -> Window | None:
        return cast(Window | None, super().get_window_for_tab(tab_id))

    def get_window_and_tab_for_session(self, session: Session) -> tuple[None, None] | tuple[Window, Tab]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(tuple[Window, Tab] | tuple[None, None], super().get_window_and_tab_for_session(session))

    async def window_delegate_get_tab_by_id(self, tab_id: str) -> Tab | None:
        return cast(Tab | None, await super().window_delegate_get_tab_by_id(tab_id))

    async def tab_delegate_get_window_by_id(self, window_id: str) -> Window | None:
        return cast(Window | None, await super().tab_delegate_get_window_by_id(window_id))

    def session_delegate_get_tab(self, session) -> Tab | None:
        return cast(Tab | None, super().session_delegate_get_tab(session))


@overload
async def async_get_app(connection: Connection, create_if_needed: Literal[True]) -> App: ...
@overload
async def async_get_app(connection: Connection, create_if_needed: Literal[False]) -> App | None: ...
async def async_get_app(connection: Connection, create_if_needed: bool = True) -> App | None:
    """Returns the app singleton, creating it if needed.

    :param connection: The connection to iTerm2.
    :type connection: :class:`Connection`
    :param create_if_needed: If `True`, create the global :class:`App` instance
      if one does not already exists. If `False`, do not create it.

    :returns: The global :class:`App` instance. If :param:`create_if_needed` is False,
    then this may return `None` if no such instance exists.
    :rtype: :class:`App` | None
    """
    return cast(App, await app.async_get_app(cast("IT2Connection", connection), create_if_needed))
