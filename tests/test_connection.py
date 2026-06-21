from __future__ import annotations

import asyncio
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


def test_headers_include_cookie_and_key_only_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ITERM2_COOKIE", raising=False)
    monkeypatch.delenv("ITERM2_KEY", raising=False)

    base_headers = connection_module._headers()
    assert "x-iterm2-cookie" not in base_headers
    assert "x-iterm2-key" not in base_headers
    assert base_headers["origin"] == "ws://localhost/"
    assert base_headers["x-iterm2-disable-auth-ui"] == "true"

    monkeypatch.setenv("ITERM2_COOKIE", "the-cookie")
    monkeypatch.setenv("ITERM2_KEY", "the-key")

    auth_headers = connection_module._headers()
    assert auth_headers["x-iterm2-cookie"] == "the-cookie"
    assert auth_headers["x-iterm2-key"] == "the-key"
    assert connection_module._cookie_and_key() == ("the-cookie", "the-key")


def test_uri_and_subprotocols_are_stable() -> None:
    assert connection_module._uri() == "ws://localhost:1912"
    assert [str(sp) for sp in connection_module._subprotocols()] == ["api.iterm2.com"]


def test_unix_domain_socket_path_honors_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IT2_SUITE", "MyTerm")
    path = Connection()._unix_domain_socket_path()
    assert path.endswith("/Library/Application Support/MyTerm/private/socket")


def test_iterm2_protocol_version_returns_zero_without_response() -> None:
    conn = Connection()
    conn.websocket = cast(Any, SimpleNamespace(response=None))
    assert conn.iterm2_protocol_version == (0, 0)


def test_register_helper_appends_and_rejects_none() -> None:
    original = list(Connection.helpers)
    try:

        async def helper(connection: Connection, message: Any) -> bool:
            return True

        Connection.register_helper(helper)
        assert Connection.helpers[-1] is helper

        with pytest.raises(AssertionError):
            Connection.register_helper(cast(Any, None))
    finally:
        Connection.helpers[:] = original


def test_remove_auth_clears_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITERM2_COOKIE", "c")
    monkeypatch.setenv("ITERM2_KEY", "k")

    Connection()._remove_auth()

    assert os.environ.get("ITERM2_COOKIE") is None
    assert os.environ.get("ITERM2_KEY") is None


def test_authenticate_returns_auth_result_and_swallows_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from iterm2 import auth

    conn = Connection()
    monkeypatch.setattr(auth, "authenticate", lambda: True)
    assert conn.authenticate(force=False) is True

    def raise_auth_error() -> bool:
        raise auth.AuthenticationException("nope")

    monkeypatch.setattr(auth, "authenticate", raise_auth_error)
    assert conn.authenticate(force=True) is False


def test_add_disconnect_callback_registers_global() -> None:
    original = list(connection_module.gDisconnectCallbacks)
    try:
        connection_module.gDisconnectCallbacks.clear()

        def callback() -> None:
            return None

        connection_module.add_disconnect_callback(callback)
        assert connection_module.gDisconnectCallbacks == [callback]
    finally:
        connection_module.gDisconnectCallbacks[:] = original


def test_collect_garbage_drops_done_tasks() -> None:
    async def scenario() -> None:
        conn = Connection()

        async def quick() -> None:
            return None

        async def slow() -> None:
            await asyncio.sleep(10)

        done_task = asyncio.ensure_future(quick())
        await done_task
        pending_task = asyncio.ensure_future(slow())

        conn._Connection__tasks = [done_task, pending_task]  # type: ignore[attr-defined]
        conn._collect_garbage()

        remaining = conn._Connection__tasks  # type: ignore[attr-defined]
        assert remaining == [pending_task]

        pending_task.cancel()

    asyncio.run(scenario())


def test_receiver_helpers_match_and_pop_by_id() -> None:
    async def scenario() -> None:
        conn = Connection()
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

        message = SimpleNamespace(id="req-1")
        other = SimpleNamespace(id="other")

        conn._Connection__receivers = [  # type: ignore[attr-defined]
            (lambda m: m.id == "req-1", future)
        ]

        assert conn._receiver_index(cast(Any, other)) is None
        assert conn._receiver_index(cast(Any, message)) == 0

        popped = conn._get_receiver_future(cast(Any, message))
        assert popped is future
        # Receiver was removed after matching.
        assert conn._get_receiver_future(cast(Any, message)) is None

    asyncio.run(scenario())


def test_async_dispatch_until_id_resolves_when_future_completes() -> None:
    async def scenario() -> None:
        conn = Connection()
        message = SimpleNamespace(id="abc")

        waiter = asyncio.ensure_future(conn.async_dispatch_until_id("abc"))
        await asyncio.sleep(0)  # let the receiver register

        future = conn._get_receiver_future(cast(Any, message))
        assert future is not None
        future.set_result(cast(Any, message))

        assert await waiter is message

    asyncio.run(scenario())


def test_async_send_message_requires_websocket() -> None:
    async def scenario() -> None:
        conn = Connection()
        with pytest.raises(ConnectionError, match="before websocket is connected"):
            await conn.async_send_message(cast(Any, SimpleNamespace(SerializeToString=lambda: b"")))

        sent: list[bytes] = []

        class FakeWebsocket:
            async def send(self, data: bytes) -> None:
                sent.append(data)

        conn.websocket = cast(Any, FakeWebsocket())
        await conn.async_send_message(cast(Any, SimpleNamespace(SerializeToString=lambda: b"payload")))
        assert sent == [b"payload"]

    asyncio.run(scenario())


def test_async_dispatch_to_helper_stops_on_first_truthy_helper() -> None:
    async def scenario() -> None:
        conn = Connection()
        seen: list[str] = []

        async def first(connection: Connection, message: Any) -> bool:
            seen.append("first")
            return True

        async def second(connection: Connection, message: Any) -> bool:
            seen.append("second")
            return True

        original = list(Connection.helpers)
        Connection.helpers[:] = [first, second]
        try:
            await conn._async_dispatch_to_helper(cast(Any, SimpleNamespace()))
        finally:
            Connection.helpers[:] = original

        assert seen == ["first"]

    asyncio.run(scenario())


def test_set_message_in_future_schedules_result() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        conn = Connection()
        future: asyncio.Future[Any] = loop.create_future()
        message = SimpleNamespace(id="x")

        conn.set_message_in_future(loop, cast(Any, message), future)
        result = await future
        assert result is message

    asyncio.run(scenario())


def test_async_close_is_safe_without_websocket() -> None:
    async def scenario() -> None:
        conn = Connection()
        # No websocket, no dispatch future -> should be a no-op without error.
        await conn.async_close()
        assert conn.websocket is None

    asyncio.run(scenario())


def test_async_close_closes_websocket_and_cancels_tasks() -> None:
    async def scenario() -> None:
        conn = Connection()
        closed: list[str] = []

        class FakeWebsocket:
            async def close(self) -> None:
                closed.append("close")

            async def wait_closed(self) -> None:
                closed.append("wait_closed")

        async def slow() -> None:
            await asyncio.sleep(10)

        pending = asyncio.ensure_future(slow())
        conn._Connection__tasks = [pending]  # type: ignore[attr-defined]
        conn.websocket = cast(Any, FakeWebsocket())

        await conn.async_close()

        assert closed == ["close", "wait_closed"]
        assert conn.websocket is None
        assert pending.cancelled()
        assert conn._Connection__tasks == []  # type: ignore[attr-defined]

    asyncio.run(scenario())


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
