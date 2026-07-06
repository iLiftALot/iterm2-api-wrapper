from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest
from iterm2 import capabilities, prompt

from iterm2_api_wrapper.api import it2prompt
from iterm2_api_wrapper.api.it2prompt import PromptMonitor


def test_check_supports_prompt_monitor_modes_passes_when_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capabilities, "supports_prompt_monitor_modes", lambda connection: True)
    # Should not raise.
    assert it2prompt.check_supports_prompt_monitor_modes(cast(Any, object())) is None


def test_check_supports_prompt_monitor_modes_raises_when_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capabilities, "supports_prompt_monitor_modes", lambda connection: False)

    with pytest.raises(capabilities.AppVersionTooOld):
        it2prompt.check_supports_prompt_monitor_modes(cast(Any, object()))


def test_async_get_last_prompt_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        sentinel = object()
        captured: list[tuple[Any, str]] = []

        async def fake(connection: Any, session_id: str) -> object:
            captured.append((connection, session_id))
            return sentinel

        monkeypatch.setattr(prompt, "async_get_last_prompt", fake)

        result = await it2prompt.async_get_last_prompt(cast(Any, "conn"), "session-1")
        assert result is sentinel
        assert captured == [("conn", "session-1")]

    asyncio.run(scenario())


def test_async_get_prompt_by_id_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        sentinel = object()
        captured: list[tuple[Any, str, str]] = []

        async def fake(connection: Any, session_id: str, prompt_unique_id: str) -> object:
            captured.append((connection, session_id, prompt_unique_id))
            return sentinel

        monkeypatch.setattr(prompt, "async_get_prompt_by_id", fake)

        result = await it2prompt.async_get_prompt_by_id(cast(Any, "conn"), "session-1", "uid-9")
        assert result is sentinel
        assert captured == [("conn", "session-1", "uid-9")]

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
