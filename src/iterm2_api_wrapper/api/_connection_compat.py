from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from ..core.gateway import Connection


def _as_upstream_connection(connection: Connection) -> Any:
    """Return `connection` at the narrow nominal upstream typing boundary."""
    return connection
