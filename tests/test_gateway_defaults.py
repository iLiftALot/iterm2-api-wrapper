from __future__ import annotations

import asyncio
import errno
from dataclasses import dataclass
from typing import Any, cast

import pytest

from iterm2_api_wrapper import gateway as gateway_module
from iterm2_api_wrapper.api.it2connection import Connection
from iterm2_api_wrapper.gateway import DefaultITermGateway, SetupCoroGateway, _get_connect_timeout_s


@dataclass
class FakeState:
    connection: object | None = None
    kwargs: dict[str, Any] | None = None
    _refresh_callback: Any = None
    _event_loop: asyncio.AbstractEventLoop | None = None

    async def ensure_state(self, refresh_callback: Any = None) -> None:
        return None

    def refresh_from(self, new_state: Any) -> None:
        assert isinstance(new_state, FakeState)
        self.connection = new_state.connection
        self.kwargs = new_state.kwargs
        self._refresh_callback = new_state._refresh_callback
        self._event_loop = new_state._event_loop


def test_get_connect_timeout_uses_default_for_missing_or_invalid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ITERM_CONNECT_TIMEOUT", raising=False)
    assert _get_connect_timeout_s() == 10.0

    monkeypatch.setenv("ITERM_CONNECT_TIMEOUT", "not-a-number")
    assert _get_connect_timeout_s() == 10.0


def test_get_connect_timeout_clamps_negative_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITERM_CONNECT_TIMEOUT", "-4.5")

    assert _get_connect_timeout_s() == 0.0


def test_async_create_connection_with_retry_retries_reset_errors() -> None:
    connected = cast(Connection, object())

    class ResetThenSucceeds:
        attempts = 0
        loop: asyncio.AbstractEventLoop | None = None

        @classmethod
        async def async_create(cls) -> Connection:
            cls.attempts += 1
            if cls.attempts == 1:
                raise OSError(errno.ECONNRESET, "reset")
            return connected

    result = asyncio.run(
        gateway_module._async_create_connection_with_retry(
            ResetThenSucceeds, timeout_s=1.0, initial_delay_s=0.0, max_delay_s=0.0
        )
    )

    assert result is connected
    assert ResetThenSucceeds.attempts == 2


def test_default_gateway_creates_state_with_lazy_runtime_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any]] = []

    async def fake_create_connection(connection_cls: object, *, timeout_s: float) -> str:
        calls.append(("connect", timeout_s))
        return "connection"

    async def fake_setup(connection: str, *, activate: bool, **kwargs: Any) -> FakeState:
        return FakeState(connection=connection, kwargs={**kwargs, "activate": activate})

    import iterm2_api_wrapper.api.it2api as api_module
    import iterm2_api_wrapper.api.it2connection as connection_module
    import iterm2_api_wrapper.mac.platform_macos as platform_macos

    monkeypatch.setattr(
        platform_macos, "activate_iterm_app", lambda app_path=None: calls.append(("activate", app_path))
    )
    monkeypatch.setattr(gateway_module, "_get_connect_timeout_s", lambda: 0.25)
    monkeypatch.setattr(gateway_module, "_async_create_connection_with_retry", fake_create_connection)
    monkeypatch.setattr(connection_module, "Connection", object)
    monkeypatch.setattr(api_module, "create_iterm_state", fake_setup)

    result = asyncio.run(DefaultITermGateway().create_state(debug=True))

    assert result == FakeState(connection="connection", kwargs={"debug": True, "activate": False})
    assert calls == [("activate", None), ("connect", 0.25)]


def test_default_gateway_translates_retry_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_connection(connection_cls: object, *, timeout_s: float) -> str:
        raise TimeoutError("too slow")

    import iterm2_api_wrapper.mac.platform_macos as platform_macos

    monkeypatch.setattr(platform_macos, "activate_iterm_app", lambda app_path=None: None)
    monkeypatch.setattr(gateway_module, "_get_connect_timeout_s", lambda: 0.0)
    monkeypatch.setattr(gateway_module, "_async_create_connection_with_retry", fake_create_connection)

    with pytest.raises(ConnectionError, match="Could not connect to iTerm2's Python API"):
        asyncio.run(DefaultITermGateway().create_state())


def test_setup_coro_gateway_invokes_custom_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_connection(connection_cls: object, *, timeout_s: float) -> str:
        return "connection"

    async def setup(connection: str, **kwargs: Any) -> FakeState:
        return FakeState(connection=connection, kwargs=kwargs)

    import iterm2_api_wrapper.mac.platform_macos as platform_macos

    monkeypatch.setattr(platform_macos, "activate_iterm_app", lambda app_path=None: None)
    monkeypatch.setattr(gateway_module, "_get_connect_timeout_s", lambda: 1.5)
    monkeypatch.setattr(gateway_module, "_async_create_connection_with_retry", fake_create_connection)

    result = asyncio.run(SetupCoroGateway[FakeState](setup).create_state(new_tab=True))

    assert result == FakeState(connection="connection", kwargs={"new_tab": True})


def test_setup_coro_gateway_translates_retry_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_connection(connection_cls: object, *, timeout_s: float) -> str:
        raise TimeoutError("too slow")

    async def setup(connection: str, **kwargs: Any) -> FakeState:
        return FakeState(connection=connection, kwargs=kwargs)

    import iterm2_api_wrapper.mac.platform_macos as platform_macos

    monkeypatch.setattr(platform_macos, "activate_iterm_app", lambda app_path=None: None)
    monkeypatch.setattr(gateway_module, "_get_connect_timeout_s", lambda: 0.0)
    monkeypatch.setattr(gateway_module, "_async_create_connection_with_retry", fake_create_connection)

    with pytest.raises(ConnectionError, match="Could not connect to iTerm2's Python API"):
        asyncio.run(SetupCoroGateway[FakeState](setup).create_state())
