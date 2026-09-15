from __future__ import annotations

from typing import TYPE_CHECKING

from iterm2 import lifecycle

from ._connection_compat import _as_upstream_connection


if TYPE_CHECKING:
    from ..core.gateway import Connection


class NewSessionMonitor(lifecycle.NewSessionMonitor):
    def __init__(self, connection: Connection):
        super().__init__(_as_upstream_connection(connection))
