from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from iterm2_api_wrapper import state as state_module
from iterm2_api_wrapper.state import (
    _validate_state,
    changed_slice,
    iTermState,
)


if TYPE_CHECKING:
    from iterm2_api_wrapper.api.it2app import App
    from iterm2_api_wrapper.api.it2connection import Connection
    from iterm2_api_wrapper.api.it2profile import PartialProfile, Profile
    from iterm2_api_wrapper.api.it2session import Session
    from iterm2_api_wrapper.api.it2tab import Tab
    from iterm2_api_wrapper.api.it2window import Window
else:
    App = Connection = PartialProfile = Profile = Session = Tab = Window = object


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


def as_connection(connection: object) -> Connection:
    return cast(Connection, connection)


def as_app(app: object) -> App:
    return cast(App, app)


def as_window(window: object) -> Window:
    return cast(Window, window)


def as_tab(tab: object) -> Tab:
    return cast(Tab, tab)


def as_session(session: object) -> Session:
    return cast(Session, session)


def as_profile(profile: object) -> Profile | PartialProfile:
    return cast(Profile | PartialProfile, profile)


def as_fake_connection(connection: Connection) -> FakeConnection:
    return cast(FakeConnection, connection)


def as_fake_session(session: Session) -> FakeSession:
    return cast(FakeSession, session)


def patch_attr(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


def call_untyped(func: object, /, *args: object, **kwargs: object) -> Any:
    return cast(Any, func)(*args, **kwargs)


def make_state(loop: asyncio.AbstractEventLoop) -> iTermState:
    session = FakeSession(path="/current", username="user", hostname="host")
    profile = SimpleNamespace(name="Default", all_properties={})
    return iTermState(
        connection=as_connection(FakeConnection(loop=loop)),
        app=as_app(FakeTarget(global_var="global")),
        window=as_window(FakeTarget(window_var="window")),
        tab=as_tab(FakeTab(session, tab_var="tab", title="prompt$")),
        session=as_session(session),
        profile=as_profile(profile),
    )


def test_validate_state_rejects_sync_functions() -> None:
    def sync_method(self: iTermState) -> None:
        return None

    with pytest.raises(TypeError, match="can only be applied to async methods"):
        _validate_state(cast(Any, sync_method))


def test_refresh_from_requires_iterm_state() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        with pytest.raises(TypeError, match="refresh_from expects an iTermState"):
            call_untyped(state.refresh_from, object())

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

        patch_attr(state, "validated_state", invalid)

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

        patch_attr(state, "validated_state", invalid)

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

        monkeypatch.setattr(state_module, "async_get_app", fake_get_app)
        patch_attr(state, "online", online)

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
        as_fake_connection(state.connection).websocket = websocket

        assert await state.online() is True
        assert websocket.recv_calls == 0

        websocket.state = SimpleNamespace(name="CLOSED")
        assert await state.online() is False
        assert websocket.recv_calls == 0

    asyncio.run(scenario())


def test_loop_manager_uses_connection_loop_when_state_loop_is_missing() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        state = make_state(loop)

        assert state._event_loop is None
        assert state.loop is loop
        assert state._event_loop is loop
        assert state.connection.loop is loop

    asyncio.run(scenario())


def test_loop_manager_reconciles_connection_to_usable_state_loop() -> None:
    async def scenario() -> None:
        state_loop = asyncio.get_running_loop()
        stale_connection_loop = asyncio.new_event_loop()
        state = make_state(stale_connection_loop)
        state._event_loop = state_loop

        try:
            assert state.loop is state_loop
            assert state._event_loop is state_loop
            assert state.connection.loop is state_loop
        finally:
            stale_connection_loop.close()

    asyncio.run(scenario())


def test_loop_manager_discards_closed_state_loop_and_uses_connection_loop() -> None:
    async def scenario() -> None:
        connection_loop = asyncio.get_running_loop()
        closed_state_loop = asyncio.new_event_loop()
        state = make_state(connection_loop)
        state._event_loop = closed_state_loop
        closed_state_loop.close()

        assert state.loop is connection_loop
        assert state._event_loop is connection_loop
        assert state.connection.loop is connection_loop

    asyncio.run(scenario())


def test_loop_manager_rejects_non_running_required_loop() -> None:
    loop = asyncio.new_event_loop()
    state = make_state(loop)

    try:
        with pytest.raises(RuntimeError, match="not running"):
            state.loop_manager.require_loop()

        assert state.loop is loop
        assert state._event_loop is loop
        assert state.connection.loop is loop
    finally:
        loop.close()


def test_variable_helpers_dispatch_to_expected_targets() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        patch_attr(state, "ensure_state", ensure_state)
        get_variable = cast(Any, state.get_variable)

        assert await get_variable("session", "path") == "/current"
        assert await get_variable("user", "custom") == "custom-value"
        assert await get_variable("tab", "tab_var") == "tab"
        assert await get_variable("window", "window_var") == "window"
        assert await get_variable("iterm2", "global_var") == "global"
        with pytest.raises(ValueError, match="Invalid context"):
            await get_variable("bad", "value")

    asyncio.run(scenario())


def test_terminal_diff_helpers_extract_command_output() -> None:
    changed = changed_slice(["prompt$"], ["prompt$", "prompt$ echo hi", "hi", "prompt$"])
    assert changed == ["prompt$ echo hi", "hi", "prompt$"]


def test_run_command_without_shell_integration_uses_empty_snapshot_without_prompt_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        marker = "__ITERM_DONE_empty-terminal__"
        wrapped_echo = f"echo hi; printf '\\n{marker}\\n'"
        snapshots = iter([["", " "], ["", " ", wrapped_echo, "hi", marker]])

        async def get_contents() -> list[str]:
            return next(snapshots)

        async def no_sleep(delay: float) -> None:
            return None

        def fixed_uuid4() -> str:
            return "empty-terminal"

        patch_attr(state, "_get_terminal_snapshot", get_contents)
        monkeypatch.setattr(state_module, "uuid4", fixed_uuid4)
        monkeypatch.setattr(asyncio, "sleep", no_sleep)

        result = await state._run_command_without_shell_integration(
            command="echo hi", suppress_broadcast=True, timeout=1.0
        )

        assert result == f"{wrapped_echo}\nhi\n{marker}"
        assert as_fake_session(state.session).sent == [(f"{wrapped_echo}\r", True)]

    asyncio.run(scenario())


def test_run_command_without_shell_integration_uses_snapshot_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        marker = "__ITERM_DONE_snapshot-diff__"
        wrapped_echo = f"prompt$ echo hi; printf '\\n{marker}\\n'"
        sent_command = f"echo hi; printf '\\n{marker}\\n'"
        snapshots = iter(
            [
                ["prompt$"],
                ["prompt$", wrapped_echo],
                ["prompt$", wrapped_echo, "hi", marker, "prompt$"],
            ]
        )

        async def get_contents() -> list[str]:
            return next(snapshots)

        async def no_sleep(delay: float) -> None:
            return None

        def fixed_uuid4() -> str:
            return "snapshot-diff"

        patch_attr(state, "_get_terminal_snapshot", get_contents)
        monkeypatch.setattr(state_module, "uuid4", fixed_uuid4)
        monkeypatch.setattr(asyncio, "sleep", no_sleep)

        result = await state._run_command_without_shell_integration(
            command="echo hi", suppress_broadcast=False, timeout=1.0
        )

        assert result == f"{wrapped_echo}\nhi\n{marker}\nprompt$"
        assert as_fake_session(state.session).sent == [(f"{sent_command}\r", False)]

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

        patch_attr(state, "ensure_state", ensure_state)
        patch_attr(state, "get_session_var", get_session_var)
        patch_attr(state, "_shell_integration_enabled", shell_integration_enabled)
        patch_attr(state, "_run_command_without_shell_integration", fallback)

        result = await state.run_command("pwd", path="/new", broadcast=False, timeout=4.0)

        assert result.output == "fallback-output"
        assert as_fake_session(state.session).sent == [("cd -- /new\r", True)]

    asyncio.run(scenario())


def test_validate_state_cancels_cross_loop_future_when_outer_task_is_cancelled() -> None:
    async def scenario() -> None:
        target_loop = asyncio.new_event_loop()

        state = make_state(target_loop)

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        patch_attr(state, "ensure_state", ensure_state)

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
