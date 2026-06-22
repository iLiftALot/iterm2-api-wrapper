from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

import pytest

from iterm2_api_wrapper import state as state_module
from iterm2_api_wrapper.state import (
    LoopManager,
    User,
    _validate_state,
    changed_slice,
    iTermState,
)
from iterm2_api_wrapper.typings import CommandExecutionResult, CommandExecutionStatus, HexCodeEnum


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


class FakePromptMonitor:
    Mode = state_module.PromptMonitor.Mode
    events: ClassVar[list[Any]] = []
    snapshots: ClassVar[list[list[str]]] = []
    instances: ClassVar[list[FakePromptMonitor]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.initial_snapshot = self._next_snapshot()
        FakePromptMonitor.instances.append(self)

    @classmethod
    def reset(
        cls,
        *,
        events: list[Any] | None = None,
        snapshots: list[list[str]] | None = None,
    ) -> None:
        cls.events = list(events or [])
        cls.snapshots = list(snapshots or [])
        cls.instances = []

    @classmethod
    def _next_snapshot(cls) -> list[str]:
        if cls.snapshots:
            return cls.snapshots.pop(0)
        return []

    async def __aenter__(self) -> FakePromptMonitor:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def async_get(self, *args: Any, **kwargs: Any) -> Any:
        if not FakePromptMonitor.events:
            raise TimeoutError
        event = FakePromptMonitor.events.pop(0)
        if isinstance(event, BaseException):
            raise event
        return event

    async def refresh_snapshot(self) -> list[str]:
        return self._next_snapshot()


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


def test_marker_line_detection_ignores_wrapped_command_argument() -> None:
    marker = "__ITERM_DONE_snapshot-diff__"
    wrapped_echo = f"prompt$ echo hi; printf '\\n{marker}\\n'"

    assert not state_module._is_marker_line(wrapped_echo, marker)
    assert state_module._is_marker_line(marker, marker)


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

        assert result == f"{wrapped_echo}\nhi"
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

        assert result == f"{wrapped_echo}\nhi"
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


def test_wait_for_prompt_accepts_fast_command_end_only_for_initial_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        Mode = FakePromptMonitor.Mode

        async def send_command() -> None:
            return None

        FakePromptMonitor.reset(
            snapshots=[["prompt$"]],
            events=[(Mode.COMMAND_END, 0, "prompt-current")],
        )
        monkeypatch.setattr(state_module, "PromptMonitor", FakePromptMonitor)

        result = await state._wait_for_prompt(
            send_command(),
            timeout=1.0,
            expected_command="ls-fancy",
            initial_prompt_id="prompt-current",
        )

        assert result == CommandExecutionStatus(
            prompt_id=None,
            command="ls-fancy",
            exit_code=CommandExecutionStatus.ExitCode.SUCCESS,
        )

    asyncio.run(scenario())


def test_wait_for_prompt_accepts_fast_command_end_but_uses_initial_prompt_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        Mode = FakePromptMonitor.Mode

        async def send_command() -> None:
            return None

        FakePromptMonitor.reset(
            snapshots=[["prompt$"]],
            events=[(Mode.COMMAND_END, 0, "old-prompt")],
        )
        monkeypatch.setattr(state_module, "PromptMonitor", FakePromptMonitor)

        result = await state._wait_for_prompt(
            send_command(),
            timeout=1.0,
            expected_command="ls-fancy",
            initial_prompt_id="prompt-current",
        )

        assert result == CommandExecutionStatus(
            prompt_id=None,
            command="ls-fancy",
            exit_code=CommandExecutionStatus.ExitCode.SUCCESS,
        )

    asyncio.run(scenario())


def test_wait_for_prompt_ignores_foreign_events_and_uses_active_prompt_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        Mode = FakePromptMonitor.Mode
        prompt_obj = SimpleNamespace(unique_id="prompt-fallback")
        sent: list[bool] = []

        async def send_command() -> None:
            sent.append(True)

        FakePromptMonitor.reset(
            snapshots=[["prompt$"]],
            events=[
                (Mode.COMMAND_END, 0, "old-prompt"),
                (Mode.COMMAND_START, "foreign command", "foreign-prompt"),
                (Mode.PROMPT, prompt_obj, None),
                (Mode.COMMAND_START, "echo hi", "start-prompt"),
                (Mode.COMMAND_END, 0, None),
            ],
        )
        monkeypatch.setattr(state_module, "PromptMonitor", FakePromptMonitor)

        result = await state._wait_for_prompt(send_command(), timeout=1.0, expected_command="echo hi")

        assert sent == [True]
        assert result == CommandExecutionStatus(
            prompt_id=None,
            command="echo hi",
            exit_code=CommandExecutionStatus.ExitCode.SUCCESS,
        )

    asyncio.run(scenario())


def test_wait_for_prompt_retries_after_changed_snapshot_then_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def send_command() -> None:
            return None

        FakePromptMonitor.reset(
            snapshots=[["prompt$"], ["prompt$", "partial output"], ["prompt$", "partial output"]],
            events=[TimeoutError(), TimeoutError()],
        )
        monkeypatch.setattr(state_module, "PromptMonitor", FakePromptMonitor)

        result = await state._wait_for_prompt(send_command(), timeout=1.0, expected_command="echo hi")

        assert result.timed_out is True
        assert result.prompt_id is None
        assert result.command is None
        assert result.exit_code is CommandExecutionStatus.ExitCode.GENERAL_FAILURE

    asyncio.run(scenario())


def test_run_command_with_shell_integration_returns_prompt_output() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        status = CommandExecutionStatus(
            prompt_id="prompt-1",
            command="echo\\nhi",
            exit_code=CommandExecutionStatus.ExitCode.SUCCESS,
        )

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        async def shell_integration_enabled() -> bool:
            return True

        async def get_terminal_snapshot() -> list[str]:
            return ["prompt$"]

        async def get_prompt(unique_id: str | None = None) -> Any:
            assert unique_id is None
            return SimpleNamespace(unique_id="prompt-current")

        async def wait_for_prompt(coro: Any, **kwargs: Any) -> CommandExecutionStatus:
            assert kwargs == {
                "timeout": 2.0,
                "expected_command": "echo\\nhi",
                "initial_prompt_id": "prompt-current",
            }
            await coro
            return status

        async def get_prompt_output(prompt_id: str, *, expected_command: str | None = None) -> str:
            assert prompt_id == "prompt-1"
            assert expected_command == "echo\\nhi"
            return "prompt-output"

        patch_attr(state, "ensure_state", ensure_state)
        patch_attr(state, "_shell_integration_enabled", shell_integration_enabled)
        patch_attr(state, "_get_terminal_snapshot", get_terminal_snapshot)
        patch_attr(state, "_wait_for_prompt", wait_for_prompt)
        patch_attr(state, "_get_prompt_output", get_prompt_output)
        patch_attr(state, "_get_prompt", get_prompt)

        result = await state.run_command("echo\nhi", broadcast=True, timeout=2.0)

        assert result == CommandExecutionResult(output="prompt-output", status=status)
        assert as_fake_session(state.session).sent == [("echo\\nhi\r", False)]

    asyncio.run(scenario())


def test_run_command_with_shell_integration_falls_back_to_snapshot_diff() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        status = CommandExecutionStatus(
            prompt_id="prompt-1",
            command="echo hi",
            exit_code=CommandExecutionStatus.ExitCode.GENERAL_FAILURE,
            timed_out=True,
        )
        snapshots = iter([["prompt$"], ["prompt$", "echo hi", "fallback", "prompt$"]])

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        async def shell_integration_enabled() -> bool:
            return True

        async def get_terminal_snapshot() -> list[str]:
            return next(snapshots)

        async def get_prompt(unique_id: str | None = None) -> Any:
            assert unique_id is None
            return SimpleNamespace(unique_id="prompt-current")

        async def wait_for_prompt(coro: Any, **kwargs: Any) -> CommandExecutionStatus:
            assert kwargs == {
                "timeout": 3.0,
                "expected_command": "echo hi",
                "initial_prompt_id": "prompt-current",
            }
            await coro
            return status

        async def get_prompt_output(prompt_id: str, *, expected_command: str | None = None) -> None:
            assert prompt_id == "prompt-1"
            return None

        patch_attr(state, "ensure_state", ensure_state)
        patch_attr(state, "_shell_integration_enabled", shell_integration_enabled)
        patch_attr(state, "_get_terminal_snapshot", get_terminal_snapshot)
        patch_attr(state, "_wait_for_prompt", wait_for_prompt)
        patch_attr(state, "_get_prompt_output", get_prompt_output)
        patch_attr(state, "_get_prompt", get_prompt)

        result = await state.run_command("echo hi", timeout=3.0)

        assert result.output == "echo hi\nfallback\nprompt$"
        assert result.status is status
        assert as_fake_session(state.session).sent == [("echo hi\r", True)]

    asyncio.run(scenario())


def test_probe_shell_integration_live_sends_bare_return_and_handles_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        Mode = FakePromptMonitor.Mode

        FakePromptMonitor.reset(events=[(Mode.PROMPT, SimpleNamespace(), "prompt-2")])
        monkeypatch.setattr(state_module, "PromptMonitor", FakePromptMonitor)

        assert await state._probe_shell_integration_live(timeout=1.0) is True
        assert as_fake_session(state.session).sent == [("\r", True)]

        as_fake_session(state.session).sent.clear()
        FakePromptMonitor.reset(events=[TimeoutError()])

        assert await state._probe_shell_integration_live(timeout=1.0) is False
        assert as_fake_session(state.session).sent == [("\r", True)]

    asyncio.run(scenario())


def test_changed_slice_edge_cases() -> None:
    # No change -> empty slice.
    assert changed_slice(["a", "b"], ["a", "b"]) == []
    # Pure append.
    assert changed_slice(["a"], ["a", "b", "c"]) == ["b", "c"]
    # Change sandwiched between a stable prefix and suffix.
    assert changed_slice(["p", "x", "q"], ["p", "y", "z", "q"]) == ["y", "z"]
    # Empty before yields the whole after.
    assert changed_slice([], ["only"]) == ["only"]


def test_usable_loop_filters_none_and_closed() -> None:
    assert LoopManager._usable_loop(None) is None

    closed = asyncio.new_event_loop()
    closed.close()
    assert LoopManager._usable_loop(closed) is None

    open_loop = asyncio.new_event_loop()
    try:
        assert LoopManager._usable_loop(open_loop) is open_loop
    finally:
        open_loop.close()


def test_user_display_name_and_lookup() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        user = User(state)

        # Plain names get the "user." prefix; existing user refs are left intact.
        assert user.display_name("foo") == "user.foo"
        assert user.display_name("session.user.bar") == "session.user.bar"

        # A plain name resolves against the session target.
        assert await user.async_get_variable("plain") == "plain-value"
        # A name that already references user context is looked up verbatim.
        assert await user.async_get_variable("x.user.y") == "x.user.y-value"

    asyncio.run(scenario())


def test_send_escape_sequence_resolves_members_and_names() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        patch_attr(state, "ensure_state", ensure_state)

        await state.send_escape_sequence(HexCodeEnum.ESC, "B", broadcast=False)

        # ESC member + the "B" member name both resolve to their control bytes.
        assert as_fake_session(state.session).sent == [("\x1bb", True)]

    asyncio.run(scenario())


def test_send_escape_sequence_requires_at_least_one_sequence() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        patch_attr(state, "ensure_state", ensure_state)

        with pytest.raises(ValueError, match="at least one sequence"):
            await state.send_escape_sequence()

    asyncio.run(scenario())


def test_typed_var_getters_route_to_expected_contexts() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        captured: list[tuple[str, str]] = []

        async def fake_get_variable(*, ctx: str, variable: str) -> str:
            captured.append((ctx, variable))
            return "value"

        patch_attr(state, "get_variable", fake_get_variable)

        await state.get_session_var("path")
        await state.get_session_var("foo.user.bar")
        await state.get_window_var("window_var")
        await state.get_tab_var("tab_var")
        await state.get_global_var("global_var")
        await state.get_user_var("custom")

        assert captured == [
            ("session", "path"),
            ("user", "foo.user.bar"),
            ("window", "window_var"),
            ("tab", "tab_var"),
            ("iterm2", "global_var"),
            ("user", "custom"),
        ]

    asyncio.run(scenario())


def test_online_returns_false_without_websocket() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        as_fake_connection(state.connection).websocket = None
        assert await state.online() is False

    asyncio.run(scenario())


def test_online_returns_false_when_close_code_present() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        as_fake_connection(state.connection).websocket = FakeWebsocket(state="OPEN", close_code=1006)
        assert await state.online() is False

    asyncio.run(scenario())


def test_validated_state_returns_false_when_offline() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def offline() -> bool:
            return False

        patch_attr(state, "online", offline)
        assert await state.validated_state() is False

    asyncio.run(scenario())


def test_validated_state_returns_false_when_app_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def online() -> bool:
            return True

        async def fake_get_app(connection: Any, *, create_if_needed: bool) -> None:
            return None

        patch_attr(state, "online", online)
        monkeypatch.setattr(state_module, "async_get_app", fake_get_app)

        assert await state.validated_state() is False

    asyncio.run(scenario())


def test_debug_property_reflects_loop_debug_flag() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        state = make_state(loop)

        loop.set_debug(False)
        assert state.debug is False
        loop.set_debug(True)
        assert state.debug is True
        loop.set_debug(False)

    asyncio.run(scenario())


def test_refresh_from_copies_all_fields_and_reconciles_loop() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        state = make_state(loop)
        replacement = make_state(loop)
        replacement.is_hotkey_window = True

        async def callback() -> iTermState:
            return replacement

        replacement._refresh_callback = callback

        state.refresh_from(replacement)

        assert state.connection is replacement.connection
        assert state.app is replacement.app
        assert state.window is replacement.window
        assert state.tab is replacement.tab
        assert state.session is replacement.session
        assert state.profile is replacement.profile
        assert state.is_hotkey_window is True
        assert state._refresh_callback is callback
        assert state.connection.loop is loop

    asyncio.run(scenario())


def test_refresh_from_rejects_non_state() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        with pytest.raises(TypeError, match="refresh_from expects an iTermState"):
            state.refresh_from(cast(Any, object()))

    asyncio.run(scenario())


def test_ensure_state_accepts_awaitable_callback() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        state = make_state(loop)
        refreshed = make_state(loop)

        async def invalid() -> bool:
            return False

        patch_attr(state, "validated_state", invalid)

        async def awaitable_callback() -> iTermState:
            return refreshed

        await state.ensure_state(awaitable_callback())

        assert state.connection is refreshed.connection

    asyncio.run(scenario())


def test_get_terminal_snapshot_trims_trailing_blank_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        class FakeTransaction:
            def __init__(self, connection: Any) -> None:
                self.connection = connection

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *exc: Any) -> bool:
                return False

        monkeypatch.setattr(state_module, "Transaction", FakeTransaction)

        session = as_fake_session(state.session)
        session.line_info = SimpleNamespace(overflow=0, scrollback_buffer_height=0, mutable_area_height=4)
        session.contents = [
            SimpleNamespace(string="first"),
            SimpleNamespace(string="second"),
            SimpleNamespace(string="   "),
            SimpleNamespace(string=""),
        ]

        snapshot = await state._get_terminal_snapshot()
        assert snapshot == ["first", "second"]

        filtered = await state._get_terminal_snapshot(trim_end=False, filter_all_empty=True)
        assert filtered == ["first", "second"]

    asyncio.run(scenario())


def test_wait_for_terminal_snapshot_completion_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def unchanged_snapshot() -> list[str]:
            return ["prompt$"]

        async def no_sleep(delay: float) -> None:
            return None

        patch_attr(state, "_get_terminal_snapshot", unchanged_snapshot)
        monkeypatch.setattr(asyncio, "sleep", no_sleep)

        with pytest.raises(TimeoutError, match="shell integration disabled"):
            await state._wait_for_terminal_snapshot_completion(["prompt$"], marker="__MISSING__", timeout=0.0)

    asyncio.run(scenario())


def test_asdict_exposes_public_fields_only() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        data = state.asdict()

        assert set(data) == {"connection", "app", "window", "tab", "session", "profile", "is_hotkey_window"}
        assert data["is_hotkey_window"] is False
        assert all(not key.startswith("_") for key in data)
        # Objects with __dict__ are expanded into their attribute mapping.
        assert isinstance(data["session"], dict)

    asyncio.run(scenario())


class FakeTransaction:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeTransaction:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


def test_get_prompt_routes_by_unique_id(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        captured: dict[str, Any] = {}

        async def by_id(*, connection: Any, session_id: str, prompt_unique_id: str) -> str:
            captured["by_id"] = (session_id, prompt_unique_id)
            return "PROMPT-BY-ID"

        async def last(*, connection: Any, session_id: str) -> str:
            captured["last"] = session_id
            return "LAST-PROMPT"

        monkeypatch.setattr(state_module, "async_get_prompt_by_id", by_id)
        monkeypatch.setattr(state_module, "async_get_last_prompt", last)

        assert await state._get_prompt("uid-1") == "PROMPT-BY-ID"
        assert await state._get_prompt() == "LAST-PROMPT"
        assert captured["by_id"] == ("session-1", "uid-1")
        assert captured["last"] == "session-1"

    asyncio.run(scenario())


def test_shell_integration_enabled_uses_live_cache() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        sid = state.session.session_id

        # A cached "live" verdict short-circuits without re-probing.
        assert state.loop is not None
        state._si_live_cache[sid] = (True, state.loop.time())
        assert await state._shell_integration_enabled() is True

        # A recent "dead" verdict is honored within the recheck window.
        state._si_live_cache[sid] = (False, state.loop.time())
        assert await state._shell_integration_enabled() is False

    asyncio.run(scenario())


def test_get_prompt_output_returns_none_for_empty_output_range() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        empty_prompt = SimpleNamespace(
            output_range=SimpleNamespace(
                start=SimpleNamespace(x=0, y=0),
                end=SimpleNamespace(x=0, y=0),
                proto="out",
            ),
            command_range=SimpleNamespace(proto="cmd"),
            excluded_subranges=[],
            prompt_range=SimpleNamespace(proto="prompt"),
            command="echo hi",
        )

        async def get_prompt(unique_id: str | None = None) -> Any:
            assert unique_id == "id"
            return empty_prompt

        patch_attr(state, "_get_prompt", get_prompt)
        patch_attr(state.session, "contents", [SimpleNamespace(string="this must not be read")])

        assert await state._get_prompt_output("id", expected_command="echo hi") is None

    asyncio.run(scenario())


def test_get_prompt_output_rejects_prompt_for_different_command() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        stale_prompt = SimpleNamespace(
            output_range=SimpleNamespace(
                start=SimpleNamespace(x=0, y=0),
                end=SimpleNamespace(x=0, y=1),
                proto="out",
            ),
            command_range=SimpleNamespace(proto="cmd"),
            excluded_subranges=[],
            prompt_range=SimpleNamespace(proto="prompt"),
            command="source ~/.iterm2_shell_integration.zsh",
        )

        async def get_prompt(unique_id: str | None = None) -> Any:
            assert unique_id == "id"
            return stale_prompt

        patch_attr(state, "_get_prompt", get_prompt)
        patch_attr(state.session, "contents", [SimpleNamespace(string="stale output")])

        assert await state._get_prompt_output("id", expected_command="echo final-smoke") is None

    asyncio.run(scenario())


def test_get_prompt_output_returns_none_when_range_inverted() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        inverted_prompt = SimpleNamespace(
            output_range=SimpleNamespace(start=SimpleNamespace(x=0, y=5), end=SimpleNamespace(x=0, y=2), proto="out"),
            command_range=SimpleNamespace(proto="cmd"),
            excluded_subranges=[],
            prompt_range=SimpleNamespace(proto="prompt"),
            command="echo hi",
        )

        async def get_prompt(unique_id: str | None = None) -> Any:
            return inverted_prompt

        patch_attr(state, "_get_prompt", get_prompt)

        assert await state._get_prompt_output("id") is None

    asyncio.run(scenario())


def test_get_prompt_output_reads_session_contents(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        monkeypatch.setattr(state_module, "Transaction", FakeTransaction)

        valid_prompt = SimpleNamespace(
            output_range=SimpleNamespace(start=SimpleNamespace(x=0, y=0), end=SimpleNamespace(x=0, y=2), proto="out"),
            command_range=SimpleNamespace(proto="cmd"),
            excluded_subranges=[],
            prompt_range=SimpleNamespace(proto="prompt"),
            command="echo hi",
        )

        async def get_prompt(unique_id: str | None = None) -> Any:
            return valid_prompt

        patch_attr(state, "_get_prompt", get_prompt)
        session = as_fake_session(state.session)
        session.contents = [SimpleNamespace(string="hi"), SimpleNamespace(string="there")]

        result = await state._get_prompt_output("id")
        assert result == "hi\nthere"

    asyncio.run(scenario())


def test_shell_integration_enabled_returns_false_without_autoload(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def get_prompt(unique_id: str | None = None) -> None:
            return None

        patch_attr(state, "_get_prompt", get_prompt)
        # Profile has autoload disabled, so no marks -> not live.
        state.profile = cast(Any, SimpleNamespace(name="Default", all_properties={}))

        assert await state._shell_integration_enabled() is False
        assert state._si_live_cache[state.session.session_id][0] is False

    asyncio.run(scenario())


def test_shell_integration_enabled_trusts_editing_prompt_state() -> None:
    async def scenario() -> None:
        from iterm2 import prompt as iterm_prompt

        state = make_state(asyncio.get_running_loop())

        editing_prompt = SimpleNamespace(state=iterm_prompt.PromptState.EDITING)

        async def get_prompt(unique_id: str | None = None) -> Any:
            return editing_prompt

        patch_attr(state, "_get_prompt", get_prompt)

        assert await state._shell_integration_enabled() is True
        assert state._si_live_cache[state.session.session_id][0] is True

    asyncio.run(scenario())


def test_probe_shell_integration_live_true_on_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        class ProbeMonitor(FakePromptMonitor):
            async def async_get(self, include_id: bool = False, *, mode: Any = None) -> Any:
                return (mode, None)

        monkeypatch.setattr(state_module, "PromptMonitor", ProbeMonitor)

        assert await state._probe_shell_integration_live() is True
        # A bare CR is sent to mint a fresh prompt mark.
        assert as_fake_session(state.session).sent == [("\r", True)]

    asyncio.run(scenario())


def test_probe_shell_integration_live_false_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        class ProbeMonitor(FakePromptMonitor):
            async def async_get(self, include_id: bool = False, *, mode: Any = None) -> Any:
                raise TimeoutError

        monkeypatch.setattr(state_module, "PromptMonitor", ProbeMonitor)

        assert await state._probe_shell_integration_live(timeout=0.01) is False

    asyncio.run(scenario())


def test_run_command_uses_prompt_output_when_shell_integration_live() -> None:
    async def scenario() -> None:
        from iterm2_api_wrapper.typings import CommandExecutionStatus

        state = make_state(asyncio.get_running_loop())

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        async def get_session_var(name: str) -> str:
            assert name == "path"
            return "/current"

        async def shell_integration_enabled() -> bool:
            return True

        async def get_terminal_snapshot() -> list[str]:
            return ["prompt$"]

        status = CommandExecutionStatus(prompt_id="p-1", command="echo hi", exit_code=0)

        async def get_prompt(unique_id: str | None = None) -> Any:
            assert unique_id is None
            return SimpleNamespace(unique_id="prompt-current")

        async def wait_for_prompt(
            coro: Any,
            *,
            timeout: float,
            expected_command: str | None,
            initial_prompt_id: str | None,
        ) -> Any:
            await coro
            assert timeout == 2.0
            assert expected_command == "echo hi"
            assert initial_prompt_id == "prompt-current"
            return status

        async def get_prompt_output(prompt_id: str, *, expected_command: str | None = None) -> str:
            assert prompt_id == "p-1"
            return "hi"

        patch_attr(state, "ensure_state", ensure_state)
        patch_attr(state, "get_session_var", get_session_var)
        patch_attr(state, "_shell_integration_enabled", shell_integration_enabled)
        patch_attr(state, "_get_terminal_snapshot", get_terminal_snapshot)
        patch_attr(state, "_wait_for_prompt", wait_for_prompt)
        patch_attr(state, "_get_prompt_output", get_prompt_output)
        patch_attr(state, "_get_prompt", get_prompt)

        result = await state.run_command("echo hi", broadcast=False, timeout=2.0)

        assert result.output == "hi"
        assert result.status is status
        # No cd was issued because the current path already matched.
        assert as_fake_session(state.session).sent == [("echo hi\r", True)]

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
