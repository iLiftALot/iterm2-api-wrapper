from __future__ import annotations

from typing import cast, TYPE_CHECKING
from iterm2 import tab

if TYPE_CHECKING:
    from .it2session import Session


class Tab(tab.Tab):
    @property
    def all_sessions(self) -> list[Session]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Session], super().all_sessions)

    @property
    def sessions(self) -> list[Session]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Session], super().sessions)

    @property
    def current_session(self) -> Session | None:
        return cast(Session, super().current_session)
