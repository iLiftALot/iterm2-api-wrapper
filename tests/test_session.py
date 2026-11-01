from __future__ import annotations

import asyncio

import pytest
from iterm2 import api_pb2, rpc
from iterm2.selection import Selection as UpstreamSelection

from iterm2_api_wrapper.api._connection_compat import _as_upstream_connection
from iterm2_api_wrapper.api.it2selection import Selection
from iterm2_api_wrapper.api.it2session import Session

from .fake import FakeConnection


@pytest.mark.parametrize("selection_type", [Selection, UpstreamSelection])
def test_selection_text_accepts_wrapper_and_upstream_selection(
    monkeypatch: pytest.MonkeyPatch, selection_type: type[UpstreamSelection]
) -> None:
    async def scenario() -> None:
        connection = FakeConnection()
        summary = api_pb2.SessionSummary(unique_identifier="session-1", title="test")
        summary.grid_size.width = 80
        session = Session(_as_upstream_connection(connection), None, summary, floating=True)
        selected = selection_type([])

        async def get_string(self: object, received_connection: object, session_id: str, width: int) -> str:
            assert received_connection is connection
            assert session_id == "session-1"
            assert width == 80
            return "selected text"

        async def get_selection() -> UpstreamSelection:
            return selected

        monkeypatch.setattr(selection_type, "async_get_string", get_string)
        monkeypatch.setattr(session, "async_get_selection", get_selection)

        assert await session.async_get_selection_text(selected) == "selected text"
        assert await session.async_get_selection_text() == "selected text"

    asyncio.run(scenario())


def test_selection_text_rejects_session_without_grid_size() -> None:
    async def scenario() -> None:
        summary = api_pb2.SessionSummary(unique_identifier="buried-session")
        session = Session(_as_upstream_connection(FakeConnection()), None, summary)

        with pytest.raises(rpc.RPCException, match="Session has no grid size"):
            await session.async_get_selection_text(Selection([]))

    asyncio.run(scenario())
