from __future__ import annotations

from typing import TYPE_CHECKING

from iterm2 import alert

from ._connection_compat import _as_upstream_connection


if TYPE_CHECKING:
    from ..core.gateway import Connection


class Alert(alert.Alert):
    async def async_run(self, connection: Connection) -> int:  # pyright: ignore[reportIncompatibleMethodOverride]
        return await super().async_run(_as_upstream_connection(connection))


class TextInputAlert(alert.TextInputAlert):
    async def async_run(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, connection: Connection
    ) -> str | None:
        return await super().async_run(_as_upstream_connection(connection))


class PolyModalAlert(alert.PolyModalAlert):
    async def async_run(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, connection: Connection
    ) -> alert.PolyModalResult:
        return await super().async_run(_as_upstream_connection(connection))
