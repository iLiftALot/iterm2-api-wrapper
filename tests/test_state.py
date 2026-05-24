from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from iterm2_api_wrapper import state as state_module
from iterm2_api_wrapper.state import _validate_state, iTermState


class FakeConnection:
    def __init__(self, loop: asyncio.AbstractEventLoop | None = None, websocket: Any = None) -> None:
        self.loop = loop
        self.websocket = websocket


class FakeWebsocket:
    def __init__(self, *, state: str = "OPEN", close_code: int | None = None) -> None:
        self.state = SimpleNamespace(name=state)
        self.close_code = close_code
        self.recv_calls = 0

    async def recv(self, *args: Any, **kwargs: Any) -> None:
        self.recv_calls += 1
        raise AssertionError("online() should not call recv()")


class FakeTarget:
    def __init__(self, **variables: str) -> None:
        self.variables = variables
        self.calls: list[str] = []

    async def async_get_variable(self, variable: str) -> str:
        self.calls.append(variable)
        return self.variables.get(variable, f"{variable}-value")


class FakeSession(FakeTarget):
    session_id = "session-1"

    def __init__(self, **variables: str) -> None:
        super().__init__(**variables)
        self.name = variables.get("name", "session-name")
        self.sent: list[tuple[str, bool]] = []
        self.contents: list[Any] = []
        self.line_info = SimpleNamespace(overflow=0, scrollback_buffer_height=0, mutable_area_height=0)

    async def async_send_text(self, text: str, *, suppress_broadcast: bool) -> None:
        self.sent.append((text, suppress_broadcast))

    async def async_get_line_info(self) -> Any:
        return self.line_info

    async def async_get_contents(self, first_line: int, number_of_lines: int) -> list[Any]:
        return self.contents[first_line : first_line + number_of_lines]

    async def async_set_name(self, name: str) -> None:
        self.name = name


class FakeTab(FakeTarget):
    def __init__(self, current_session: FakeSession | None = None, **variables: str) -> None:
        super().__init__(**variables)
        self.current_session = current_session
        self.title_set_to: str | None = None

    async def async_set_title(self, title: str) -> None:
        self.title_set_to = title
        self.variables["title"] = title


def make_state(loop: asyncio.AbstractEventLoop) -> iTermState:
    session = FakeSession(path="/current", username="user", hostname="host")
    return iTermState(
        connection=FakeConnection(loop=loop),
        app=FakeTarget(global_var="global"),
        window=FakeTarget(window_var="window"),
        tab=FakeTab(session, tab_var="tab", title="prompt$"),
        session=session,
        profile=SimpleNamespace(name="Default"),
    )


def test_validate_state_rejects_sync_functions() -> None:
    def sync_method(self: iTermState) -> None:
        return None

    with pytest.raises(TypeError, match="can only be applied to async methods"):
        _validate_state(sync_method)


def test_refresh_from_requires_iterm_state() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        with pytest.raises(TypeError, match="refresh_from expects an iTermState"):
            state.refresh_from(object())  # type: ignore[arg-type]

    asyncio.run(scenario())


def test_ensure_state_refreshes_from_callback_when_invalid() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        state = make_state(loop)
        refreshed = make_state(loop)
        refreshed.is_hotkey_window = True

        async def invalid() -> bool:
            return False

        async def callback() -> iTermState:
            return refreshed

        state.validated_state = invalid  # type: ignore[method-assign]

        await state.ensure_state(callback)

        assert state.connection is refreshed.connection
        assert state.app is refreshed.app
        assert state.is_hotkey_window is True

    asyncio.run(scenario())


def test_ensure_state_requires_refresh_callback_when_invalid() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def invalid() -> bool:
            return False

        state.validated_state = invalid  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="No refresh callback"):
            await state.ensure_state()

    asyncio.run(scenario())


def test_validated_state_updates_current_iterm_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        state = make_state(loop)
        new_session = FakeSession()
        new_window = FakeTarget()
        new_tab = FakeTab(new_session)

        class FakeApp(FakeTarget):
            def get_session_by_id(self, session_id: str, *, include_buried: bool) -> FakeSession:
                assert session_id == "session-1"
                assert include_buried is False
                return new_session

            def get_window_and_tab_for_session(self, session: FakeSession) -> tuple[FakeTarget, FakeTab]:
                assert session is new_session
                return new_window, new_tab

        async def fake_get_app(connection: FakeConnection, *, create_if_needed: bool) -> FakeApp:
            assert connection is state.connection
            assert create_if_needed is False
            return FakeApp()

        async def online() -> bool:
            return True

        monkeypatch.setattr(state_module.app, "async_get_app", fake_get_app)
        state.online = online  # type: ignore[method-assign]

        assert await state.validated_state() is True
        assert state.session is new_session
        assert state.window is new_window
        assert state.tab is new_tab

    asyncio.run(scenario())


def test_online_uses_passive_websocket_state() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        websocket = FakeWebsocket(state="OPEN")
        state = make_state(loop)
        state.connection.websocket = websocket

        assert await state.online() is True
        assert websocket.recv_calls == 0

        websocket.state = SimpleNamespace(name="CLOSED")
        assert await state.online() is False
        assert websocket.recv_calls == 0

    asyncio.run(scenario())


def test_variable_helpers_dispatch_to_expected_targets() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        state.ensure_state = ensure_state  # type: ignore[method-assign]

        assert await state.get_variable("session", "path") == "/current"
        assert await state.get_variable("user", "custom") == "custom-value"
        assert await state.get_variable("tab", "tab_var") == "tab"
        assert await state.get_variable("window", "window_var") == "window"
        assert await state.get_variable("iterm2", "global_var") == "global"
        with pytest.raises(ValueError, match="Invalid context"):
            await state.get_variable("bad", "value")  # type: ignore[arg-type]

    asyncio.run(scenario())


def test_terminal_diff_helpers_extract_command_output() -> None:
    assert iTermState._last_nonempty_line(["", "  ", " prompt$ "]) == "prompt$"
    assert iTermState._last_nonempty_line(["", "  "]) is None

    changed = iTermState._changed_slice(["prompt$"], ["prompt$", "prompt$ echo hi", "hi", "prompt$"])
    assert changed == ["prompt$ echo hi", "hi", "prompt$"]
    assert iTermState._extract_output_from_changed_block(changed, prompt_line="prompt$", command="echo hi") == "hi"
    assert iTermState._extract_output_from_changed_block([], prompt_line="prompt$", command="echo hi") == ""


def test_get_prompt_candidate_nudges_empty_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        snapshots = iter([["", " "], ["prompt$"]])

        async def get_contents() -> list[str]:
            return next(snapshots)

        async def no_sleep(delay: float) -> None:
            return None

        state._get_terminal_contents = get_contents  # type: ignore[method-assign]
        monkeypatch.setattr(state_module.asyncio, "sleep", no_sleep)

        lines, prompt_line = await state._get_prompt_candidate(suppress_broadcast=True)

        assert lines == ["prompt$"]
        assert prompt_line == "prompt$"
        assert state.session.sent == [("\r", True)]

    asyncio.run(scenario())


def test_run_command_without_shell_integration_uses_snapshot_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        snapshots = iter(
            [
                ["prompt$"],
                ["prompt$", "prompt$ echo hi"],
                ["prompt$", "prompt$ echo hi", "hi", "prompt$"],
                ["prompt$", "prompt$ echo hi", "hi", "prompt$"],
            ]
        )

        async def get_contents() -> list[str]:
            return next(snapshots)

        async def no_sleep(delay: float) -> None:
            return None

        state._get_terminal_contents = get_contents  # type: ignore[method-assign]
        monkeypatch.setattr(state_module.asyncio, "sleep", no_sleep)

        result = await state._run_command_without_shell_integration(
            command="echo hi", suppress_broadcast=False, timeout=1.0
        )

        assert result == "hi"
        assert state.session.sent == [("echo hi\r", False)]

    asyncio.run(scenario())


def test_run_command_changes_directory_before_fallback() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        async def get_session_var(name: str) -> str:
            assert name == "path"
            return "/old"

        async def shell_integration_enabled() -> bool:
            return False

        async def fallback(**kwargs: Any) -> str:
            assert kwargs == {"command": "pwd", "suppress_broadcast": True, "timeout": 4.0}
            return "fallback-output"

        state.ensure_state = ensure_state  # type: ignore[method-assign]
        state.get_session_var = get_session_var  # type: ignore[method-assign]
        state._shell_integration_enabled = shell_integration_enabled  # type: ignore[method-assign]
        state._run_command_without_shell_integration = fallback  # type: ignore[method-assign]

        result = await state.run_command("pwd", path="/new", broadcast=False, timeout=4.0)

        assert result == "fallback-output"
        assert state.session.sent == [("cd '/new'\r", True)]

    asyncio.run(scenario())


def test_string_in_lines_uses_command_range_when_output_range_is_empty() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        updated_prompt = SimpleNamespace(
            output_range=SimpleNamespace(start=SimpleNamespace(y=0), end=SimpleNamespace(y=0)),
            command_range=SimpleNamespace(start=SimpleNamespace(y=2), end=SimpleNamespace(y=4)),
        )
        state.session.contents = [
            SimpleNamespace(string="ignored", hard_eol=True),
            SimpleNamespace(string="ignored", hard_eol=True),
            SimpleNamespace(string="", hard_eol=True),
            SimpleNamespace(string="line one", hard_eol=True),
            SimpleNamespace(string="line two", hard_eol=False),
        ]

        async def get_prompt(unique_id: str | None = None) -> Any:
            assert unique_id == "prompt-1"
            return updated_prompt

        state._get_prompt = get_prompt  # type: ignore[method-assign]

        result = await state._string_in_lines(SimpleNamespace(unique_id="prompt-1"))

        assert result == "line one\nline two"

    asyncio.run(scenario())


def test_validate_state_cancels_cross_loop_future_when_outer_task_is_cancelled() -> None:
    async def scenario() -> None:
        caller_loop = asyncio.get_running_loop()
        target_loop = asyncio.new_event_loop()

        state = make_state(target_loop)

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        state.ensure_state = ensure_state  # type: ignore[method-assign]

        started = asyncio.Event()
        cancelled_on_target = asyncio.Event()

        @_validate_state
        async def slow_method(self: iTermState) -> str:
            started.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled_on_target.set()
                raise
            return "done"

        def run_target_loop() -> None:
            asyncio.set_event_loop(target_loop)
            target_loop.run_forever()

        import threading

        thread = threading.Thread(target=run_target_loop, daemon=True)
        thread.start()

        try:
            task = asyncio.create_task(slow_method(state))
            await asyncio.wait_for(started.wait(), timeout=1.0)

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            await asyncio.wait_for(cancelled_on_target.wait(), timeout=1.0)
        finally:
            target_loop.call_soon_threadsafe(target_loop.stop)
            thread.join(timeout=1.0)
            target_loop.close()

    asyncio.run(scenario())
