from __future__ import annotations

from typing import TYPE_CHECKING, cast

from iterm2 import transaction

from .it2connection import Connection


if TYPE_CHECKING:
    from iterm2.connection import Connection as IT2Connection


class Transaction(transaction.Transaction):
    def __init__(self, connection: Connection | IT2Connection):
        super().__init__(cast("IT2Connection", connection))
