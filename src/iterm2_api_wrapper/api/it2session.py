from __future__ import annotations

from typing import TYPE_CHECKING, cast

from iterm2 import session


if TYPE_CHECKING:
    from .it2profile import Profile
    from .it2tab import Tab


class Session(session.Session):
    name: str

    async def async_get_profile(self) -> Profile:
        return cast(Profile, await super().async_get_profile())

    @property
    def tab(self) -> Tab | None:
        return cast(Tab | None, super().tab)
