from __future__ import annotations

from typing import TYPE_CHECKING, cast

from iterm2 import lifecycle
from iterm2.connection import Connection as IT2Connection


if TYPE_CHECKING:
    from .it2connection import Connection


class NewSessionMonitor(lifecycle.NewSessionMonitor):
    def __init__(self, connection: Connection):
        super().__init__(cast("IT2Connection", connection))
