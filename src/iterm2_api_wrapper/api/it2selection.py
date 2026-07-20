from iterm2 import selection
from typing import TYPE_CHECKING, cast


if TYPE_CHECKING:
    from .it2connection import Connection
    from iterm2 import Connection as IT2Connection


class Selection(selection.Selection):
    async def async_get_string(self, connection: IT2Connection | Connection, session_id: str, width: int) -> str:
        return await super().async_get_string(cast("IT2Connection", connection), session_id, width)
