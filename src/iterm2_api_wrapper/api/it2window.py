from __future__ import annotations

from typing import TYPE_CHECKING, cast

from iterm2 import profile, window


if TYPE_CHECKING:
    from .it2connection import Connection
    from .it2tab import Tab


class Window(window.Window):
    """Represents a terminal window.

    Do not create an instance of `Window` by calling the initializer yourself.
    To get a reference to an existing window, use :class:`~iterm2.app.App` and
    query its `windows` property. To create a new window, use
    :meth:`async_create`.
    """

    @property
    def tabs(self) -> list[Tab]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Tab], super().tabs)

    @property
    def current_tab(self) -> Tab | None:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(Tab | None, super().current_tab)

    @staticmethod
    async def async_create(  # pyright: ignore[reportIncompatibleMethodOverride]
        connection: Connection,
        profile: str | None = None,
        command: str | None = None,
        profile_customizations: profile.LocalWriteOnlyProfile | None = None,
    ) -> Window | None:
        return cast(
            Window | None, await window.Window.async_create(connection, profile, command, profile_customizations)
        )

    async def async_create_tab(
        self,
        profile: str | None = None,
        command: str | None = None,
        index: int | None = None,
        profile_customizations: profile.LocalWriteOnlyProfile | None = None,
    ) -> Tab | None:
        return cast(Tab | None, await super().async_create_tab(profile, command, index, profile_customizations))
