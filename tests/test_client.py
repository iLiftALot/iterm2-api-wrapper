from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from iterm2_api_wrapper import client as client_module
from iterm2_api_wrapper.client import iTermClient
from iterm2_api_wrapper.gateway import ITermGateway


@dataclass
class DummyState:
    marker: str = "initial"
    setup_kwargs: dict[str, Any] | None = None

    _refresh_callback: Any = None
    _event_loop: asyncio.AbstractEventLoop | None = None
    connection: Any | None = None
    ensure_state_calls: int = 0
    ensure_state_exc: Exception | None = None

    async def ensure_state(self, refresh_callback: Any = None) -> None:
        self.ensure_state_calls += 1
        if self.ensure_state_exc is None:
            return
        exc = self.ensure_state_exc
        self.ensure_state_exc = None
        raise exc

    def refresh_from(self, new_state: DummyState) -> None:
        assert isinstance(new_state, DummyState)
        self.marker = new_state.marker
        self.setup_kwargs = new_state.setup_kwargs
        self._refresh_callback = new_state._refresh_callback
        self._event_loop = new_state._event_loop
        self.connection = new_state.connection


class FailingRefreshState(DummyState):
    def refresh_from(self, new_state: Any) -> None:
        raise RuntimeError("refresh failed")


class DummyGateway(ITermGateway[DummyState]):
    def __init__(self, states: list[DummyState]) -> None:
        self._states = list(states)
        self.calls: list[dict[str, Any]] = []

    async def create_state(self, **kwargs: Any) -> DummyState:
        self.calls.append(kwargs)
        state = self._states.pop(0) if self._states else DummyState()
        state.setup_kwargs = dict(kwargs)
        return state


def stop_client(client: iTermClient[Any]) -> None:
    client.close()


def test_client_initializes_state_and_thread() -> None:
    gateway = DummyGateway([DummyState(marker="boot")])
    client: iTermClient[DummyState] = iTermClient(gateway=gateway, debug=True, new_tab=False)
    try:
        assert client._thread.is_alive()
        assert client.state.marker == "boot"
        assert gateway.calls == [{"debug": True, "new_tab": False}]
    finally:
        stop_client(client)


def test_get_state_calls_ensure_state() -> None:
    gateway = DummyGateway([DummyState(marker="boot")])
    client: iTermClient[DummyState] = iTermClient(gateway=gateway)
    try:
        assert client.state.ensure_state_calls == 0
        state = client.get_state()
        assert state is client.state
        assert state.ensure_state_calls == 1
    finally:
        stop_client(client)


def test_close_closes_active_connection() -> None:
    class ClosableConnection:
        def __init__(self) -> None:
            self.closed = False

        async def async_close(self) -> None:
            self.closed = True

    connection = ClosableConnection()
    state = DummyState(marker="boot")
    state.connection = connection
    gateway = DummyGateway([state])
    client: iTermClient[DummyState] = iTermClient(gateway=gateway)

    client.close()

    assert connection.closed is True
    assert client._loop.is_closed()


def test_get_state_refreshes_state_on_ensure_state_error() -> None:
    initial = DummyState(marker="initial", ensure_state_exc=RuntimeError("boom"))
    refreshed = DummyState(marker="refreshed")
    gateway = DummyGateway([initial, refreshed])

    client: iTermClient[DummyState] = iTermClient(gateway=gateway)
    try:
        state = client.get_state()
        assert state is client.state
        assert state.marker == "refreshed"
        assert state.ensure_state_calls == 1
        assert len(gateway.calls) == 2
    finally:
        stop_client(client)


def test_get_state_replaces_state_when_in_place_refresh_fails() -> None:
    initial = FailingRefreshState(marker="initial", ensure_state_exc=RuntimeError("boom"))
    refreshed = DummyState(marker="replacement")
    gateway = DummyGateway([initial, refreshed])

    client: iTermClient[DummyState] = iTermClient(gateway=gateway)
    try:
        state = client.get_state()
        assert state is refreshed
        assert client.state is refreshed
        assert state.marker == "replacement"
        assert len(gateway.calls) == 2
    finally:
        stop_client(client)


def test_async_create_factory_initializes_without_blocking_running_loop() -> None:
    async def scenario() -> None:
        gateway = DummyGateway([DummyState(marker="async")])
        client: iTermClient[DummyState] = await iTermClient.create(gateway=gateway, debug=False)
        try:
            assert client.state.marker == "async"
            assert gateway.calls == [{"debug": False}]
        finally:
            stop_client(client)

    asyncio.run(scenario())


def test_get_state_async_from_foreign_loop_calls_ensure_state() -> None:
    async def scenario() -> None:
        gateway = DummyGateway([DummyState(marker="boot")])
        client: iTermClient[DummyState] = iTermClient(gateway=gateway)
        try:
            state = await client.get_state_async()
            assert state is client.state
            assert state.ensure_state_calls == 1
        finally:
            stop_client(client)

    asyncio.run(scenario())


def test_get_state_async_from_client_loop_uses_direct_async_path() -> None:
    gateway = DummyGateway([DummyState(marker="boot")])
    client: iTermClient[DummyState] = iTermClient(gateway=gateway)
    try:

        async def call_from_client_loop() -> DummyState:
            return await client.get_state_async()

        state = asyncio.run_coroutine_threadsafe(call_from_client_loop(), client.loop).result(timeout=2)

        assert state is client.state
        assert state.ensure_state_calls == 1
    finally:
        stop_client(client)


def test_context_managers_close_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client: iTermClient[DummyState] = iTermClient(gateway=DummyGateway([DummyState()]))
    closed: list[bool] = []
    monkeypatch.setattr(client, "close", lambda: closed.append(True))

    with client as entered:
        assert entered is client

    assert closed == [True]


def test_get_shared_client_caches_created_client_by_default_key(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        created = object()
        calls: list[dict[str, Any]] = []

        async def fake_create(**kwargs: Any) -> object:
            calls.append(kwargs)
            return created

        monkeypatch.setattr(client_module, "_shared_clients", {})
        monkeypatch.setattr(client_module, "_shared_lock", asyncio.Lock())
        monkeypatch.setattr(client_module.iTermClient, "create", staticmethod(fake_create))

        first = await client_module.get_shared_client(debug=True)
        second = await client_module.get_shared_client(debug=False)

        assert first is created
        assert second is created
        assert calls == [{"debug": True}]

    asyncio.run(scenario())


def test_get_shared_client_uses_identifier_key(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        created: list[object] = []
        calls: list[dict[str, Any]] = []

        async def fake_create(**kwargs: Any) -> object:
            calls.append(kwargs)
            client = object()
            created.append(client)
            return client

        monkeypatch.setattr(client_module, "_shared_clients", {})
        monkeypatch.setattr(client_module, "_shared_lock", asyncio.Lock())
        monkeypatch.setattr(client_module.iTermClient, "create", staticmethod(fake_create))

        first = await client_module.get_shared_client(service_name="pyterm-mcp", extra_id="session-a")
        second = await client_module.get_shared_client(service_name="pyterm-mcp", extra_id="session-a")
        third = await client_module.get_shared_client(service_name="pyterm-mcp", extra_id="session-b")
        fourth = await client_module.get_shared_client(
            service_name="pyterm-mcp", dedicated_profile_name="Default", extra_id="session-a"
        )

        assert first is second
        assert third is not first
        assert fourth is not first
        assert fourth is not third
        assert len(created) == 3
        assert calls == [
            {"service_name": "pyterm-mcp", "extra_id": "session-a"},
            {"service_name": "pyterm-mcp", "extra_id": "session-b"},
            {"service_name": "pyterm-mcp", "dedicated_profile_name": "Default", "extra_id": "session-a"},
        ]

    asyncio.run(scenario())


def test_close_shared_client_removes_only_matching_key(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        class ClosableClient:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        default_client = ClosableClient()
        session_client = ClosableClient()

        default_key = client_module._shared_client_key()
        session_key = client_module._shared_client_key(service_name="pyterm-mcp", extra_id="session-a")

        shared_clients = {default_key: default_client, session_key: session_client}

        monkeypatch.setattr(client_module, "_shared_clients", shared_clients)
        monkeypatch.setattr(client_module, "_shared_lock", asyncio.Lock())

        await client_module.close_shared_client(service_name="pyterm-mcp", extra_id="session-a")

        assert session_client.closed is True
        assert default_client.closed is False
        assert shared_clients == {default_key: default_client}

    asyncio.run(scenario())
