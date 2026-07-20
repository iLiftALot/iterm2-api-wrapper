from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from iterm2_api_wrapper import state as state_module
from iterm2_api_wrapper.state import (
    LoopManager,
    MarkedCommand,
    User,
    _validate_state,
    iTermState,
)
from iterm2_api_wrapper.typings import CommandExecutionResult, CommandExecutionStatus, HexCodeEnum
from iterm2_api_wrapper.utils.parser import ParseResult

from .fake import (
    FakeConnection,
    FakePromptMonitor,
    FakeSession,
    FakeTab,
    FakeTarget,
    FakeWebsocket,
    as_fake_connection,
    as_fake_session,
    as_profile,
    call_untyped,
    make_state,
    patch_attr,
)


if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


def coord_range(start_x: int = 0, start_y: int = 0, end_x: int = 0, end_y: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        start=SimpleNamespace(x=start_x, y=start_y),
        end=SimpleNamespace(x=end_x, y=end_y),
        proto=f"{start_x},{start_y}:{end_x},{end_y}",
    )


def prompt_stub(
    *,
    unique_id: str = "prompt-current",
    output_range: SimpleNamespace | None = None,
    command_range: SimpleNamespace | None = None,
    prompt_range: SimpleNamespace | None = None,
    command: str = "echo hi",
) -> SimpleNamespace:
    return SimpleNamespace(
        unique_id=unique_id,
        output_range=output_range or coord_range(),
        command_range=command_range or coord_range(),
        excluded_subranges=[],
        prompt_range=prompt_range or coord_range(),
        command=command,
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


def test_marked_command_script_body_wraps_command_with_shell_integration_marks() -> None:
    marked = MarkedCommand("echo hi", command_label="echo hi", prompt="wrapper> ")
    body = marked.script_body

    assert str(marked) == marked.source_command
    assert marked.script_path.read_text(encoding="utf-8") == body
    assert "Generated by iterm2-api-wrapper" in body
    assert "emulate -L zsh" in body
    assert marked.aid in body
    assert marked.before_prompt_mark == marked.BEFORE_PROMPT.format(aid=marked.aid)
    assert marked.after_prompt_mark == marked.AFTER_PROMPT.format(aid=marked.aid)
    assert marked.before_output_mark == marked.BEFORE_OUTPUT.format(aid=marked.aid)
    assert marked.after_output_mark == marked.AFTER_OUTPUT.format(aid=marked.aid)
    assert f"printf {state_module.shlex.quote(marked.execution_prompt)}" in body
    assert f"printf {state_module.shlex.quote(marked.before_output_mark)}" in body
    assert f'  printf {state_module.shlex.quote(marked.after_output_mark)} "$__iterm_status"' in body
    assert "echo hi" in body
    assert "__iterm_status=$?" in body
    assert 'return "$__iterm_status"' in body
    marked.cleanup()


def test_marked_command_context_manager_cleans_up_script(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    with MarkedCommand("echo hi") as marked:
        script_path = marked.script_path

        assert script_path.parent == tmp_path
        assert script_path.read_text(encoding="utf-8") == marked.script_body
        assert script_path.stat().st_mode & 0o777 == 0o600

    assert not script_path.exists()
    marked.cleanup()
    assert not script_path.exists()


def test_run_command_without_shell_integration_sources_marked_script_and_cleans_up(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        status = CommandExecutionStatus(
            prompt_id="prompt-1", command="pwd", exit_code=CommandExecutionStatus.ExitCode.SUCCESS
        )

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        async def get_session_var(name: str) -> str:
            assert name == "path"
            return "/old"

        async def shell_integration_enabled() -> bool:
            return False

        async def snapshot() -> list[str]:
            return ["prompt$"]

        async def get_prompt(unique_id: str | None = None) -> Any:
            assert unique_id is None
            return SimpleNamespace(unique_id="prompt-current")

        async def wait_for_prompt(coro: Any, **kwargs: Any) -> CommandExecutionStatus:
            assert kwargs == {"timeout": 4.0, "expected_command": "pwd", "initial_prompt_id": "prompt-current"}
            await coro
            source_text = as_fake_session(state.session).sent[-1][0]
            script_path = Path(state_module.shlex.split(source_text.removesuffix("\r"))[1])
            script_body = script_path.read_text(encoding="utf-8")
            expected_mark_fragments = [
                state_module.MarkedCommand.BEFORE_PROMPT.split("{aid}", 1)[0],
                state_module.MarkedCommand.AFTER_PROMPT.split("{aid}", 1)[0],
                state_module.MarkedCommand.BEFORE_OUTPUT.split("{aid}", 1)[0],
                state_module.MarkedCommand.AFTER_OUTPUT.split("{aid}", 1)[0],
            ]
            assert ";aid=iterm2-api-wrapper-" in script_body
            for fragment in expected_mark_fragments:
                assert fragment in script_body
            return status

        async def run_parser(
            prompt_id: str | None, expected_command: str, initial_snapshot: list[str], **_: Any
        ) -> ParseResult:
            assert prompt_id == "prompt-1"
            assert expected_command == "pwd"
            assert initial_snapshot == ["prompt$"]
            return ParseResult(output="script-output", prompt="prompt$", command="pwd", command_parsed="pwd")

        async def no_sleep(delay: float) -> None:
            return None

        patch_attr(state, "ensure_state", ensure_state)
        patch_attr(state, "get_session_var", get_session_var)
        patch_attr(state, "_shell_integration_enabled", shell_integration_enabled)
        patch_attr(state, "_snapshot", snapshot)
        patch_attr(state, "_get_prompt", get_prompt)
        patch_attr(state, "_wait_for_prompt", wait_for_prompt)
        patch_attr(state, "_run_parser", run_parser)
        monkeypatch.setattr(asyncio, "sleep", no_sleep)
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        result = await state.run_command("pwd", path="/new", broadcast=False, timeout=4.0)

        assert result == CommandExecutionResult(output="script-output", status=status)
        assert list(tmp_path.iterdir()) == []
        sent = as_fake_session(state.session).sent
        assert sent[:3] == [
            ("\x15", True),
            ("cd -- /new\r", True),
            ("\x15", True),
        ]
        source_command, suppress = sent[3]
        assert suppress is True
        assert source_command.startswith(f"source {state_module.shlex.quote(str(tmp_path))}/")
        assert source_command.endswith("\r")

    asyncio.run(scenario())


def test_wait_for_prompt_accepts_fast_command_end_only_for_initial_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        Mode = FakePromptMonitor.Mode

        async def send_command() -> None:
            return None

        FakePromptMonitor.reset(snapshots=[["prompt$"]], events=[(Mode.COMMAND_END, 0, "prompt-current")])
        monkeypatch.setattr(state_module, "PromptMonitor", FakePromptMonitor)

        result = await state._wait_for_prompt(
            send_command(), timeout=1.0, expected_command="ls-fancy", initial_prompt_id="prompt-current"
        )

        assert result == CommandExecutionStatus(
            prompt_id=None, command="ls-fancy", exit_code=CommandExecutionStatus.ExitCode.SUCCESS
        )

    asyncio.run(scenario())


def test_wait_for_prompt_accepts_fast_command_end_but_uses_initial_prompt_id(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        Mode = FakePromptMonitor.Mode

        async def send_command() -> None:
            return None

        FakePromptMonitor.reset(snapshots=[["prompt$"]], events=[(Mode.COMMAND_END, 0, "old-prompt")])
        monkeypatch.setattr(state_module, "PromptMonitor", FakePromptMonitor)

        result = await state._wait_for_prompt(
            send_command(), timeout=1.0, expected_command="ls-fancy", initial_prompt_id="prompt-current"
        )

        assert result == CommandExecutionStatus(
            prompt_id=None, command="ls-fancy", exit_code=CommandExecutionStatus.ExitCode.SUCCESS
        )

    asyncio.run(scenario())


def test_wait_for_prompt_ignores_foreign_events_and_uses_active_prompt_id(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        Mode = FakePromptMonitor.Mode
        prompt_obj = SimpleNamespace(unique_id="prompt-fallback")
        sent: list[bool] = []

        async def send_command() -> None:
            sent.append(True)

        FakePromptMonitor.reset(
            snapshots=[["prompt$"], ["prompt$"]],
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
            prompt_id="start-prompt", command="echo hi", exit_code=CommandExecutionStatus.ExitCode.SUCCESS
        )

    asyncio.run(scenario())


def test_wait_for_prompt_retries_after_changed_snapshot_then_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
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
            prompt_id="prompt-1", command="echo\\nhi", exit_code=CommandExecutionStatus.ExitCode.SUCCESS
        )

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        async def shell_integration_enabled() -> bool:
            return True

        async def snapshot() -> list[str]:
            return ["prompt$"]

        async def get_prompt(unique_id: str | None = None) -> Any:
            assert unique_id is None
            return SimpleNamespace(unique_id="prompt-current")

        async def wait_for_prompt(coro: Any, **kwargs: Any) -> CommandExecutionStatus:
            assert kwargs == {"timeout": 2.0, "expected_command": "echo\\nhi", "initial_prompt_id": "prompt-current"}
            await coro
            return status

        async def run_parser(
            prompt_id: str | None, expected_command: str, initial_snapshot: list[str], **_: Any
        ) -> ParseResult:
            assert prompt_id == "prompt-1"
            assert expected_command == "echo\\nhi"
            assert initial_snapshot == ["prompt$"]
            return ParseResult(
                output="prompt-output", prompt="prompt$", command="echo\\nhi", command_parsed="echo\\nhi"
            )

        patch_attr(state, "ensure_state", ensure_state)
        patch_attr(state, "_shell_integration_enabled", shell_integration_enabled)
        patch_attr(state, "_snapshot", snapshot)
        patch_attr(state, "_wait_for_prompt", wait_for_prompt)
        patch_attr(state, "_run_parser", run_parser)
        patch_attr(state, "_get_prompt", get_prompt)

        result = await state.run_command("echo\nhi", broadcast=True, timeout=2.0)

        assert result == CommandExecutionResult(output="prompt-output", status=status)
        assert as_fake_session(state.session).sent == [("\x15", False), ("echo\\nhi\r", False)]

    asyncio.run(scenario())


def test_run_command_returns_parser_output_when_prompt_monitor_times_out() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        status = CommandExecutionStatus(
            prompt_id="prompt-1",
            command="echo hi",
            exit_code=CommandExecutionStatus.ExitCode.GENERAL_FAILURE,
            timed_out=True,
        )
        prompt = SimpleNamespace(unique_id="prompt-current")
        snapshots = iter([["prompt$"]])

        async def ensure_state(refresh_callback: Any = None) -> None:
            return None

        async def shell_integration_enabled() -> bool:
            return True

        async def snapshot() -> list[str]:
            return next(snapshots)

        async def get_prompt(unique_id: str | None = None) -> Any:
            assert unique_id is None
            return prompt

        async def wait_for_prompt(coro: Any, **kwargs: Any) -> CommandExecutionStatus:
            assert kwargs == {"timeout": 3.0, "expected_command": "echo hi", "initial_prompt_id": "prompt-current"}
            await coro
            return status

        async def run_parser(
            prompt_id: str | None, expected_command: str, initial_snapshot: list[str], **_: Any
        ) -> ParseResult:
            assert prompt_id == "prompt-1"
            assert expected_command == "echo hi"
            assert initial_snapshot == ["prompt$"]
            return ParseResult(output="fallback", prompt="prompt$", command="echo hi", command_parsed="echo hi")

        patch_attr(state, "ensure_state", ensure_state)
        patch_attr(state, "_shell_integration_enabled", shell_integration_enabled)
        patch_attr(state, "_snapshot", snapshot)
        patch_attr(state, "_wait_for_prompt", wait_for_prompt)
        patch_attr(state, "_run_parser", run_parser)
        patch_attr(state, "_get_prompt", get_prompt)

        result = await state.run_command("echo hi", timeout=3.0)

        assert result.output == "fallback"
        assert result.status is status
        assert as_fake_session(state.session).sent == [("\x15", True), ("echo hi\r", True)]

    asyncio.run(scenario())


def test_probe_shell_integration_live_sends_bare_return_and_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_snapshot_trims_trailing_blank_lines(monkeypatch: pytest.MonkeyPatch) -> None:
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

        snapshot = await state._snapshot()
        assert snapshot == ["first", "second"]

        filtered = await state._snapshot(trim_end=False, filter_all_empty=True)
        assert filtered == ["first", "second"]

    asyncio.run(scenario())


def test_send_text_can_skip_clearing_current_line() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        await state._send_text("echo hi", suppress=True, clear_line=False)

        assert as_fake_session(state.session).sent == [("echo hi\r", True)]

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


def test_get_prompt_routes_through_current_prompt_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        captured: list[tuple[Any, str | None, str | None]] = []

        async def get_prompt(connection: Any, session_id: str | None = None, prompt_id: str | None = None) -> str:
            captured.append((connection, session_id, prompt_id))
            return f"PROMPT-{prompt_id or 'LAST'}"

        monkeypatch.setattr(state_module, "async_get_prompt", get_prompt)

        assert await state._get_prompt("uid-1") == "PROMPT-uid-1"
        assert await state._get_prompt() == "PROMPT-LAST"
        assert captured == [
            (state.connection, "session-1", "uid-1"),
            (state.connection, "session-1", None),
        ]

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


def test_run_parser_returns_parse_result() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        same_line_prompt = prompt_stub(output_range=coord_range(end_x=9), command="echo hi")

        async def get_prompt(unique_id: str | None = None) -> Any:
            if unique_id is None:
                return None
            assert unique_id == "id"
            return same_line_prompt

        patch_attr(state, "_get_prompt", get_prompt)
        patch_attr(state, "_get_prompt", get_prompt)
        patch_attr(state.session, "contents", [SimpleNamespace(string="same line output", hard_eol=False)])

        result = await state._run_parser("id", "echo hi", [])
        assert result == ParseResult(output="same line", prompt="", command="echo hi", command_parsed="")

    asyncio.run(scenario())


def test_get_prompt_output_returns_empty_string_for_empty_output_range() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        empty_output_prompt = prompt_stub(output_range=coord_range(start_y=5, end_y=5))

        async def get_prompt(unique_id: str | None = None) -> Any:
            if unique_id is None:
                return None
            assert unique_id == "id"
            return empty_output_prompt

        patch_attr(state, "_get_prompt", get_prompt)
        patch_attr(
            state.session, "contents", [SimpleNamespace(string="next prompt - must not be read", hard_eol=True)] * 6
        )

        result = await state._run_parser("id", "echo hi", [])
        assert result.output == ""

    asyncio.run(scenario())


def test_run_parser_raises_when_prompt_unavailable() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def get_prompt(unique_id: str | None = None) -> None:
            if unique_id is None:
                return None
            assert unique_id == "id"
            return None

        patch_attr(state, "_get_prompt", get_prompt)
        with pytest.raises(RuntimeError, match="Failed to retrieve prompt"):
            await state._run_parser("id", "echo hi", [])

    asyncio.run(scenario())


def test_run_parser_uses_snapshot_fallback_when_prompt_command_differs() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        stale_prompt = prompt_stub(
            output_range=coord_range(end_y=1), prompt_range=coord_range(end_x=7), command="stale"
        )
        snapshots = iter([["prompt$"], ["prompt$", "echo final-smoke", "fallback", "prompt$"]])

        async def snapshot() -> list[str]:
            return next(snapshots)

        async def get_prompt(unique_id: str | None = None) -> Any:
            return stale_prompt

        patch_attr(state, "_get_prompt", get_prompt)
        patch_attr(state, "_snapshot", snapshot)
        patch_attr(state.session, "contents", [SimpleNamespace(string="prompt$", hard_eol=True)])

        initial_snapshot = await state._snapshot()
        result = await state._run_parser("id", "echo final-smoke", initial_snapshot)
        assert result.output == "fallback"

    asyncio.run(scenario())


def test_get_prompt_output_returns_empty_string_when_range_inverted() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        inverted_prompt = prompt_stub(output_range=coord_range(start_y=5, end_y=2))

        async def get_prompt(unique_id: str | None = None) -> Any:
            return inverted_prompt

        patch_attr(state, "_get_prompt", get_prompt)

        result = await state._run_parser("id", "", [])
        assert result.output == ""

    asyncio.run(scenario())


def test_get_prompt_output_reads_session_contents(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        monkeypatch.setattr(state_module, "Transaction", FakeTransaction)

        valid_prompt = prompt_stub(output_range=coord_range(end_y=2))

        async def get_prompt(unique_id: str | None = None) -> Any:
            if unique_id is None:
                return None
            return valid_prompt

        patch_attr(state, "_get_prompt", get_prompt)
        session = as_fake_session(state.session)
        session.contents = [SimpleNamespace(string="hi"), SimpleNamespace(string="there")]

        result = await state._run_parser("id", "echo hi", [])
        assert result.output == "hi\nthere"

    asyncio.run(scenario())


def test_shell_integration_enabled_returns_false_without_autoload(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())

        async def get_prompt(unique_id: str | None = None) -> None:
            return None

        patch_attr(state, "_get_prompt", get_prompt)
        # Profile has autoload disabled, so no marks -> not live.
        state.profile = as_profile(SimpleNamespace(name="Default", all_properties={}))

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

        async def snapshot() -> list[str]:
            return ["prompt$"]

        status = CommandExecutionStatus(prompt_id="p-1", command="echo hi", exit_code=0)

        async def get_prompt(unique_id: str | None = None) -> Any:
            assert unique_id is None
            return SimpleNamespace(unique_id="prompt-current")

        async def wait_for_prompt(
            coro: Any, *, timeout: float, expected_command: str | None, initial_prompt_id: str | None
        ) -> Any:
            await coro
            assert timeout == 2.0
            assert expected_command == "echo hi"
            assert initial_prompt_id == "prompt-current"
            return status

        async def run_parser(
            prompt_id: str | None, expected_command: str, initial_snapshot: list[str], **_: Any
        ) -> ParseResult:
            assert prompt_id == "p-1"
            assert expected_command == "echo hi"
            assert initial_snapshot == ["prompt$"]
            return ParseResult(output="hi", prompt="prompt$", command="echo hi", command_parsed="echo hi")

        patch_attr(state, "ensure_state", ensure_state)
        patch_attr(state, "get_session_var", get_session_var)
        patch_attr(state, "_shell_integration_enabled", shell_integration_enabled)
        patch_attr(state, "_snapshot", snapshot)
        patch_attr(state, "_wait_for_prompt", wait_for_prompt)
        patch_attr(state, "_run_parser", run_parser)
        patch_attr(state, "_get_prompt", get_prompt)

        result = await state.run_command("echo hi", broadcast=False, timeout=2.0)

        assert result.output == "hi"
        assert result.status is status
        # No cd was issued because the current path already matched.
        assert as_fake_session(state.session).sent == [("\x15", True), ("echo hi\r", True)]

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
