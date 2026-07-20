from __future__ import annotations

from typing import TYPE_CHECKING, cast

from iterm2 import api_pb2, rpc, session

from .it2profile import Profile


if TYPE_CHECKING:
    from .it2selection import Selection
    from .it2tab import Tab


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

    @property
    def tab(self) -> Tab | None:
        return cast(Tab | None, super().tab)
