from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
from iterm2.capabilities import AppVersionTooOld

from iterm2_api_wrapper.core import runtime_setup as it2runtime


def connection(version: tuple[int, int] = (1, 14)) -> Any:
    return SimpleNamespace(iterm2_protocol_version=version)


@pytest.fixture
def validation_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(it2runtime, "_enhance_imports", lambda: None)
    monkeypatch.setattr(it2runtime, "_install_iterm2_connection_bridge", lambda: None)


@pytest.fixture
def isolated_connection_bridge() -> Iterator[tuple[Any, Any, Any, type[Any]]]:
    import iterm2
    import iterm2.connection as upstream_connection

    from iterm2_api_wrapper.api import it2connection as wrapper_connection

    root_names = ("Connection", "run_until_complete", "run_forever", "add_disconnect_callback")
    module_names = root_names
    original_root_exports = {name: getattr(iterm2, name) for name in root_names}
    original_module_exports = {name: getattr(upstream_connection, name) for name in module_names}
    original_upstream_callbacks = upstream_connection.gDisconnectCallbacks
    original_upstream_callback_values = list(original_upstream_callbacks)
    original_wrapper_helpers = list(wrapper_connection.Connection.helpers)
    original_wrapper_callbacks = list(wrapper_connection.gDisconnectCallbacks)

    class PreviousConnection:
        helpers: ClassVar[list[Any]] = []

    upstream_connection.Connection = PreviousConnection
    upstream_connection.gDisconnectCallbacks = []

    try:
        yield iterm2, upstream_connection, wrapper_connection, PreviousConnection
    finally:
        wrapper_connection.Connection.helpers[:] = original_wrapper_helpers
        wrapper_connection.gDisconnectCallbacks[:] = original_wrapper_callbacks
        original_upstream_callbacks[:] = original_upstream_callback_values
        upstream_connection.gDisconnectCallbacks = original_upstream_callbacks

        for name, value in original_module_exports.items():
            setattr(upstream_connection, name, value)
        for name, value in original_root_exports.items():
            setattr(iterm2, name, value)


def test_validate_runtime_checks_every_connection(monkeypatch: pytest.MonkeyPatch, validation_only: None) -> None:
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(it2runtime, "check_supports_prompt_monitor_modes", lambda conn: calls.append(("prompt", conn)))
    monkeypatch.setattr(it2runtime, "check_supports_get_default_profile", lambda conn: calls.append(("profile", conn)))
    monkeypatch.setattr(it2runtime, "check_supports_prompt_id", lambda conn: calls.append(("prompt_id", conn)))

    first = connection()
    second = connection()

    it2runtime.validate_iterm2_runtime(first)
    it2runtime.validate_iterm2_runtime(second)

    assert calls == [
        ("prompt", first),
        ("profile", first),
        ("prompt_id", first),
        ("prompt", second),
        ("profile", second),
        ("prompt_id", second),
    ]


def test_validate_runtime_rejects_unsupported_connection(validation_only: None) -> None:
    with pytest.raises(AppVersionTooOld):
        it2runtime.validate_iterm2_runtime(connection((1, 4)))


def test_validate_runtime_logs_protocol_version(monkeypatch: pytest.MonkeyPatch, validation_only: None) -> None:
    logged: list[str] = []

    monkeypatch.setattr(it2runtime.log, "debug", lambda message: logged.append(message))

    it2runtime.validate_iterm2_runtime(connection((1, 14)))

    assert logged == ["iTerm protocol version 1.14"]


def test_connection_bridge_transfers_helpers_once_and_is_idempotent(
    isolated_connection_bridge: tuple[Any, Any, Any, type[Any]],
) -> None:
    _iterm2, _upstream, wrapper_connection, previous_connection = isolated_connection_bridge

    async def helper(connection: object, message: object) -> bool:
        return True

    previous_connection.helpers = [helper]
    wrapper_connection.Connection.helpers.clear()

    it2runtime._install_iterm2_connection_bridge()
    it2runtime._install_iterm2_connection_bridge()

    assert wrapper_connection.Connection.helpers == [helper]


def test_connection_bridge_shares_disconnect_callback_registry(
    isolated_connection_bridge: tuple[Any, Any, Any, type[Any]],
) -> None:
    _iterm2, upstream_connection, wrapper_connection, _previous_connection = isolated_connection_bridge
    calls: list[str] = []

    def upstream_callback() -> None:
        calls.append("upstream")

    def wrapper_callback() -> None:
        calls.append("wrapper")

    def late_callback() -> None:
        calls.append("late")

    upstream_connection.gDisconnectCallbacks.append(upstream_callback)
    wrapper_connection.gDisconnectCallbacks[:] = [wrapper_callback]
    old_upstream_add_callback = upstream_connection.add_disconnect_callback

    it2runtime._install_iterm2_connection_bridge()
    old_upstream_add_callback(late_callback)

    assert upstream_connection.gDisconnectCallbacks is wrapper_connection.gDisconnectCallbacks
    assert wrapper_connection.gDisconnectCallbacks == [wrapper_callback, upstream_callback, late_callback]


def test_connection_bridge_replaces_module_and_root_exports(
    isolated_connection_bridge: tuple[Any, Any, Any, type[Any]],
) -> None:
    iterm2, upstream_connection, wrapper_connection, _previous_connection = isolated_connection_bridge

    it2runtime._install_iterm2_connection_bridge()

    assert upstream_connection.Connection is wrapper_connection.Connection
    assert upstream_connection.run_until_complete is wrapper_connection.run_until_complete
    assert upstream_connection.run_forever is wrapper_connection.run_forever
    assert upstream_connection.add_disconnect_callback is wrapper_connection.add_disconnect_callback
    assert iterm2.Connection is wrapper_connection.Connection
    assert iterm2.run_until_complete is wrapper_connection.run_until_complete
    assert iterm2.run_forever is wrapper_connection.run_forever
    assert iterm2.add_disconnect_callback is wrapper_connection.add_disconnect_callback
