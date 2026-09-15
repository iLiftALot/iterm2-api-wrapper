from __future__ import annotations

from typing import TYPE_CHECKING

from iterm2 import transaction

from ._connection_compat import _as_upstream_connection


if TYPE_CHECKING:
    from ..core.gateway import Connection


class Transaction(transaction.Transaction):
    def __init__(self, connection: Connection):
        super().__init__(_as_upstream_connection(connection))
