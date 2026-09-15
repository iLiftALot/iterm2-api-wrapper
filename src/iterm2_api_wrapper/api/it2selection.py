from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeAlias

from iterm2 import selection

from ._connection_compat import _as_upstream_connection


if TYPE_CHECKING:
    from ..core.gateway import Connection


iTermSelection: TypeAlias = "Selection | selection.Selection | SelectionLike"


class SelectionLike(Protocol):
    async def async_get_string(self, connection: Connection, session_id: str, width: int) -> str: ...


class Selection(selection.Selection):
    async def async_get_string(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, connection: Connection, session_id: str, width: int
    ) -> str:
        return await super().async_get_string(_as_upstream_connection(connection), session_id, width)
