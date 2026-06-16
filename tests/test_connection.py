from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, cast

import pytest

from iterm2_api_wrapper.api import it2connection as connection_module
from iterm2_api_wrapper.api.it2connection import Connection


def test_iterm2_protocol_version_handles_missing_or_malformed_header() -> None:
    conn = Connection()
    assert conn.iterm2_protocol_version == (0, 0)

    conn.websocket = cast(Any, SimpleNamespace(response=SimpleNamespace(headers={})))
    assert conn.iterm2_protocol_version == (0, 0)

    conn.websocket = cast(Any, SimpleNamespace(response=SimpleNamespace(headers={"X-iTerm2-Protocol-Version": "bad"})))
    assert conn.iterm2_protocol_version == (0, 0)


def test_iterm2_protocol_version_parses_major_minor_header() -> None:
    conn = Connection()
    conn.websocket = cast(Any, SimpleNamespace(response=SimpleNamespace(headers={"X-iTerm2-Protocol-Version": "3.5"})))

    assert conn.iterm2_protocol_version == (3, 5)


def test_get_connect_coro_selects_unix_or_tcp(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = Connection()
    monkeypatch.setattr(conn, "_unix_domain_socket_path", lambda: "/tmp/iterm.sock")
    monkeypatch.setattr(conn, "_get_unix_connect_coro", lambda: "unix")
    monkeypatch.setattr(conn, "_get_tcp_connect_coro", lambda: "tcp")

    monkeypatch.setattr(os.path, "exists", lambda path: True)
    assert conn._get_connect_coro() == "unix"

    monkeypatch.setattr(os.path, "exists", lambda path: False)
    assert conn._get_connect_coro() == "tcp"


def test_run_wraps_connection_coro(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeConnection:
        def run(self, *, forever: bool, coro: Any, retry: bool, debug: bool) -> str:
            calls.append({"forever": forever, "retry": retry, "debug": debug})
            coroutine = coro("connection")
            try:
                coroutine.close()
            except AttributeError:
                pass
            return "result"

    async def sample(connection: Any, value: str) -> str:
        return f"{connection}:{value}"

    monkeypatch.setattr(connection_module, "Connection", FakeConnection)

    assert connection_module.run(False, sample, False, True, "value") == "result"
    assert calls == [{"forever": False, "retry": False, "debug": True}]


def test_run_until_complete_reraises_connection_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    async def sample(connection: Any) -> None:
        return None

    def fake_run(*args: Any, **kwargs: Any) -> None:
        raise ConnectionRefusedError("no iTerm")

    monkeypatch.setattr(connection_module, "run", fake_run)
    monkeypatch.setattr(connection_module.log, "error", lambda *args, **kwargs: None)

    with pytest.raises(ConnectionRefusedError):
        connection_module.run_until_complete(sample)


def test_run_forever_wraps_connection_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    async def sample(connection: Any) -> None:
        return None

    def fake_run(*args: Any, **kwargs: Any) -> None:
        raise ConnectionRefusedError("no iTerm")

    monkeypatch.setattr(connection_module, "run", fake_run)
    monkeypatch.setattr(connection_module.log, "error", lambda *args, **kwargs: None)

    with pytest.raises(ConnectionRefusedError):
        connection_module.run_forever(sample)
