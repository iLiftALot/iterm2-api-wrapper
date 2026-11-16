from __future__ import annotations

from typing import TYPE_CHECKING, cast

from iterm2 import Frame, Point, Size, profile, window

from iterm2_api_wrapper.pyobjc_adapter.pyobjc_typings import NSScreen


if TYPE_CHECKING:
    from ..core.gateway import Connection
    from ..pyobjc_adapter.pyobjc_typings import CGRect
    from .it2tab import Tab

from ._connection_compat import _as_upstream_connection


class Window(window.Window):
    """Represents a terminal window.

    Do not create an instance of `Window` by calling the initializer yourself.
    To get a reference to an existing window, use :class:`~iterm2.app.App` and
    query its `windows` property. To create a new window, use
    :meth:`async_create`.
    """

    @property
    def tabs(self) -> list[Tab]:  # type: ignore
        return cast(list["Tab"], super().tabs)

    @property
    def current_tab(self) -> Tab | None:  # type: ignore
        return cast("Tab | None", super().current_tab)

    @staticmethod
    async def async_create(  # type: ignore
        connection: Connection,
        profile: str | None = None,
        command: str | None = None,
        profile_customizations: profile.LocalWriteOnlyProfile | None = None,
    ) -> Window | None:
        return cast(
            Window | None,
            await window.Window.async_create(
                _as_upstream_connection(connection), profile, command, profile_customizations
            ),
        )

    async def async_create_tab(
        self,
        profile: str | None = None,
        command: str | None = None,
        index: int | None = None,
        profile_customizations: profile.LocalWriteOnlyProfile | None = None,
        select: bool = True,
    ) -> Tab | None:
        return cast(
            "Tab | None", await super().async_create_tab(profile, command, index, profile_customizations, select)
        )


def maximum_visible_window_frame(window: Window) -> Frame:
    """Return the usable frame of the display containing most of the window."""

    def compute_intersection_area(left: Frame, right: CGRect) -> float:
        # fmt: off
        l_origin, r_origin, l_size, r_size = (
            left.origin,
            right.origin,
            left.size,
            right.size,
        )
        # fmt: on
        l_min_x, l_min_y = float(l_origin.x), float(l_origin.y)
        l_max_x, l_max_y = l_min_x + float(l_size.width), l_min_y + float(l_size.height)

        r_min_x, r_min_y = float(r_origin.x), float(r_origin.y)
        r_max_x, r_max_y = r_min_x + float(r_size.width), r_min_y + float(r_size.height)

        overlap_width = max(0.0, min(l_max_x, r_max_x) - max(l_min_x, r_min_x))
        overlap_height = max(0.0, min(l_max_y, r_max_y) - max(l_min_y, r_min_y))

        intersection_area = overlap_width * overlap_height
        return intersection_area

    screens = list(NSScreen.screens())
    if not screens:
        raise RuntimeError("AppKit reported no available displays")

    proto_frame = window.frame
    current_frame = Frame(
        Point(proto_frame.origin.x, proto_frame.origin.y), Size(proto_frame.size.width, proto_frame.size.height)
    )
    target_screen = max(screens, key=lambda screen: compute_intersection_area(current_frame, screen.frame()))
    visible_frame = target_screen.visibleFrame()

    return Frame(
        Point(int(visible_frame.origin.x), int(visible_frame.origin.y)),
        Size(int(visible_frame.size.width), int(visible_frame.size.height)),
    )
