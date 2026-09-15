from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias, cast

from iterm2 import api_pb2, rpc, session
from typing_extensions import override

from .it2profile import Profile


if TYPE_CHECKING:
    from iterm2.selection import Selection as IT2Selection

    from .it2selection import Selection as _Selection
    from .it2tab import Tab


# TODO: Move this where it should go and perform the same refractors for the whole codebase
Selection: TypeAlias = "_Selection | IT2Selection"


class Session(session.Session):
    _Session__session_id: str
    name: str

    async def async_get_profile(self) -> Profile:
        response: api_pb2.ServerOriginatedMessage = await rpc.async_get_profile(self.connection, self.__session_id)
        status = response.get_profile_property_response.status
        if status == api_pb2.GetProfilePropertyResponse.Status.Value("OK"):
            return Profile(
                self._Session__session_id, self.connection, response.get_profile_property_response.properties
            )
        raise rpc.RPCException(api_pb2.GetProfilePropertyResponse.Status.Name(status))

    async def async_get_selection(self) -> Selection:
        return cast("Selection", await super().async_get_selection())

    @override
    async def async_get_selection_text(self, selection: Selection | None = None) -> str:
        sel = selection
        if sel is None:
            sel = await self.async_get_selection()

        return await sel.async_get_string(self.connection, self.session_id, self.grid_size.width)

    @property
    def tab(self) -> Tab | None:
        return cast(Tab | None, super().tab)
