from __future__ import annotations

from typing import TYPE_CHECKING, cast

from iterm2 import alert
from iterm2.connection import Connection


if TYPE_CHECKING:
    from iterm2.connection import Connection as IT2Connection

    from .it2connection import Connection


class Alert(alert.Alert):
    async def async_run(self, connection: Connection) -> int:  # pyright: ignore[reportIncompatibleMethodOverride]
        return await super().async_run(cast(IT2Connection, connection))


class TextInputAlert(alert.TextInputAlert):
    async def async_run(self, connection: Connection) -> str | None:
        return await super().async_run(cast(IT2Connection, connection))


class PolyModalAlert(alert.PolyModalAlert):
    async def async_run(self, connection: Connection) -> alert.PolyModalResult:
        return await super().async_run(cast(IT2Connection, connection))
