from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest
from iterm2 import api_pb2, capabilities, prompt, rpc

from iterm2_api_wrapper.api import it2prompt
from iterm2_api_wrapper.api.it2measurement import CoordRange
from iterm2_api_wrapper.api.it2prompt import Prompt, PromptMonitor


def test_check_supports_prompt_monitor_modes_passes_when_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capabilities, "supports_prompt_monitor_modes", lambda connection: True)
    # Should not raise.
    assert it2prompt.check_supports_prompt_monitor_modes(cast(Any, object())) is None


def test_check_supports_prompt_monitor_modes_raises_when_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capabilities, "supports_prompt_monitor_modes", lambda connection: False)

    with pytest.raises(capabilities.AppVersionTooOld):
        it2prompt.check_supports_prompt_monitor_modes(cast(Any, object()))


def prompt_response(status_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        get_prompt_response=SimpleNamespace(status=api_pb2.GetPromptResponse.Status.Value(status_name))
    )


def test_prompt_range_properties_convert_protobuf_ranges() -> None:
    proto = api_pb2.GetPromptResponse()
    proto.output_range.start.x = 1
    proto.output_range.start.y = 2
    proto.output_range.end.x = 3
    proto.output_range.end.y = 4
    proto.prompt_range.start.x = 5
    proto.prompt_range.end.x = 6
    proto.command_range.start.y = 7
    proto.command_range.end.y = 8

    wrapped = Prompt(proto)

    assert isinstance(wrapped.output_range, CoordRange)
    assert (wrapped.output_range.start.x, wrapped.output_range.start.y) == (1, 2)
    assert (wrapped.output_range.end.x, wrapped.output_range.end.y) == (3, 4)
    assert isinstance(wrapped.prompt_range, CoordRange)
    assert (wrapped.prompt_range.start.x, wrapped.prompt_range.end.x) == (5, 6)
    assert isinstance(wrapped.command_range, CoordRange)
    assert (wrapped.command_range.start.y, wrapped.command_range.end.y) == (7, 8)


def test_async_get_prompt_wraps_ok_response(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        response = prompt_response("OK")
        captured: list[tuple[Any, str | None, str | None]] = []

        async def fake_rpc(connection: Any, session_id: str | None, prompt_id: str | None) -> Any:
            captured.append((connection, session_id, prompt_id))
            return response

        def fake_prompt(prompt_proto: object) -> tuple[str, object]:
            return ("wrapped", prompt_proto)

        monkeypatch.setattr(it2prompt.rpc, "async_get_prompt", fake_rpc)
        monkeypatch.setattr(it2prompt, "Prompt", fake_prompt)

        result = await it2prompt.async_get_prompt(cast(Any, "conn"), "session-1")
        assert result == ("wrapped", response.get_prompt_response)
        assert captured == [("conn", "session-1", None)]

    asyncio.run(scenario())


def test_async_get_prompt_by_id_checks_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        response = prompt_response("PROMPT_UNAVAILABLE")
        checked: list[Any] = []

        async def fake_rpc(connection: Any, session_id: str | None, prompt_id: str | None) -> Any:
            assert (connection, session_id, prompt_id) == ("conn", "session-1", "uid-9")
            return response

        monkeypatch.setattr(it2prompt.capabilities, "check_supports_prompt_id", checked.append)
        monkeypatch.setattr(it2prompt.rpc, "async_get_prompt", fake_rpc)

        result = await it2prompt.async_get_prompt(cast(Any, "conn"), "session-1", "uid-9")
        assert result is None
        assert checked == ["conn"]

    asyncio.run(scenario())


def test_async_get_prompt_raises_rpc_exception_for_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        async def fake_rpc(connection: Any, session_id: str | None, prompt_id: str | None) -> Any:
            return prompt_response("SESSION_NOT_FOUND")

        monkeypatch.setattr(it2prompt.rpc, "async_get_prompt", fake_rpc)

        with pytest.raises(rpc.RPCException, match="SESSION_NOT_FOUND"):
            await it2prompt.async_get_prompt(cast(Any, "conn"), "missing-session")

    asyncio.run(scenario())


def test_refresh_snapshot_requires_provider() -> None:
    async def scenario() -> None:
        monitor = cast(PromptMonitor[Any], object.__new__(PromptMonitor))
        monitor.snapshot_provider = None

        with pytest.raises(RuntimeError, match="snapshot_provider was not passed"):
            await monitor.refresh_snapshot()

    asyncio.run(scenario())


def test_refresh_snapshot_updates_current_snapshot() -> None:
    async def scenario() -> None:
        monitor = cast(PromptMonitor[Any], object.__new__(PromptMonitor))

        async def provider() -> list[str]:
            return ["line-1", "line-2"]

        monitor.snapshot_provider = provider
        monitor.current_snapshot = cast(Any, None)

        snapshot = await monitor.refresh_snapshot()
        assert snapshot == ["line-1", "line-2"]
        assert monitor.current_snapshot == ["line-1", "line-2"]

    asyncio.run(scenario())


def test_prompt_monitor_initializes_upstream_and_snapshot_state(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, str, list[prompt.PromptMonitor.Mode] | None]] = []

    def base_init(
        self: object, connection: Any, session_id: str, modes: list[prompt.PromptMonitor.Mode] | None = None
    ) -> None:
        calls.append((connection, session_id, modes))

    async def provider() -> list[str]:
        return ["prompt$"]

    modes = [prompt.PromptMonitor.Mode.PROMPT]
    monkeypatch.setattr(prompt.PromptMonitor, "__init__", base_init)

    monitor = PromptMonitor(cast(Any, "connection"), "session-1", modes, snapshot_provider=provider)

    assert calls == [("connection", "session-1", modes)]
    assert monitor.snapshot_provider is provider
    assert monitor.initial_snapshot is None
    assert monitor.current_snapshot is None


def test_prompt_monitor_enter_captures_initial_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        monitor = cast(PromptMonitor[list[str]], object.__new__(PromptMonitor))
        calls: list[str] = []

        async def provider() -> list[str]:
            calls.append("snapshot")
            return ["prompt$"]

        async def base_enter(self: object) -> object:
            calls.append("base-enter")
            return self

        monitor.snapshot_provider = provider
        monitor.initial_snapshot = []
        monitor.current_snapshot = []
        monkeypatch.setattr(prompt.PromptMonitor, "__aenter__", base_enter)

        entered = await monitor.__aenter__()

        assert entered is monitor
        assert monitor.initial_snapshot == ["prompt$"]
        assert monitor.current_snapshot == ["prompt$"]
        assert calls == ["snapshot", "base-enter"]

    asyncio.run(scenario())


def test_async_get_filters_by_requested_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        Mode = prompt.PromptMonitor.Mode
        monitor = cast(PromptMonitor[Any], object.__new__(PromptMonitor))

        events = iter(
            [(Mode.COMMAND_START, "echo hi"), (Mode.COMMAND_END, 0), (Mode.PROMPT, SimpleNamespace(unique_id="p-1"))]
        )

        # The override delegates to ``super().async_get`` which resolves to the
        # upstream base method; patching it lets us drive the event stream.
        async def fake_base_async_get(self: Any, include_id: bool = False) -> Any:
            return next(events)

        monkeypatch.setattr(prompt.PromptMonitor, "async_get", fake_base_async_get, raising=True)

        # Non-PROMPT events are skipped until the requested mode arrives.
        result = await monitor.async_get(mode=Mode.PROMPT)
        assert result[0] == Mode.PROMPT

    asyncio.run(scenario())
