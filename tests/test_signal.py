from __future__ import annotations

import asyncio
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path

import pytest

from iterm2_api_wrapper.utils.signal import Signal, SignalResult, SignalShellBusyError

from .fake import FakeState, as_state


def _wait_for_file(path: Path, timeout: float = 2.0) -> bytes:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            time.sleep(0.01)

    raise TimeoutError(path)


def _wait_for_absence(path: Path, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if not path.exists():
            return
        time.sleep(0.01)

    raise TimeoutError(path)


def _install_ack_from_command(command: str, *, pid: int) -> tuple[Path, str, str]:
    _, _, _, signal_dir_text, nonce, digest = shlex.split(command)
    signal_dir = Path(signal_dir_text)

    (signal_dir / Signal.BINDING_FILE).write_text(
        f"{Signal.PROTOCOL_VERSION}\tready\t{pid}\tUSR1\t{digest}\t{nonce}\n", encoding="utf-8"
    )
    (signal_dir / f"install.{nonce}").write_text(
        f"{Signal.PROTOCOL_VERSION}\tok\t{pid}\tUSR1\t{nonce}\t{digest}\n", encoding="utf-8"
    )
    return signal_dir, nonce, digest


def _configure_fake_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, handler: Path) -> None:
    monkeypatch.setattr(Signal, "SIGNAL_ROOT", tmp_path / "signals")
    monkeypatch.setattr(Signal, "SIGNAL_SCRIPT", handler)
    monkeypatch.setattr(
        Signal, "_read_process_identity", staticmethod(lambda pid: ("ttys123", "Fri Jul 24 21:00:00 2026", "/bin/zsh"))
    )


def _request_for_pid(signal_root: Path, pid: int) -> tuple[Path, Path, str]:
    signal_dir = next(signal_root.iterdir())
    request = next(signal_dir.glob(f"request.{pid}.*"))
    return signal_dir, request, request.name.rsplit(".", 1)[1]


def _publish_fake_result(
    signal_dir: Path, pid: int, nonce: str, result: SignalResult, *, prompt_status: int = 0, redraw_status: int = 0
) -> None:
    (signal_dir / f"started.{pid}.{nonce}").write_text(
        f"{Signal.PROTOCOL_VERSION}\tstarted\t{pid}\t{nonce}\n", encoding="utf-8"
    )
    (signal_dir / f"stdout.{pid}.{nonce}").write_text(result.stdout, encoding="utf-8")
    (signal_dir / f"stderr.{pid}.{nonce}").write_text(result.stderr, encoding="utf-8")
    (signal_dir / f"response.{pid}.{nonce}").write_text(
        (f"{Signal.PROTOCOL_VERSION}\tok\t{pid}\t{nonce}\t{result.returncode}\t{prompt_status}\t{redraw_status}\n"),
        encoding="utf-8",
    )


def test_execute_sources_once_then_reuses_cached_live_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = FakeState()
        handler = tmp_path / "handler.zsh"
        handler.write_text("handler-v1", encoding="utf-8")
        _configure_fake_process(tmp_path, monkeypatch, handler)

        async def send_text(command: str, suppress: bool) -> None:
            assert suppress is True
            _install_ack_from_command(command, pid=4242)

        state.on_send = send_text
        commands: list[str] = []
        expected_results = iter((SignalResult(0, "first output\n", ""), SignalResult(17, "", "second error\n")))
        kill_calls: list[tuple[int, int]] = []

        def fake_kill(pid: int, signal_number: int) -> None:
            kill_calls.append((pid, signal_number))
            if signal_number == 0:
                return

            signal_dir, request, nonce = _request_for_pid(tmp_path / "signals", pid)
            commands.append(request.read_text(encoding="utf-8"))
            _publish_fake_result(signal_dir, pid, nonce, next(expected_results))

        monkeypatch.setattr(os, "kill", fake_kill)

        first = await Signal(as_state(state), "/bin/zsh").execute("print -r -- 'first output'")
        signal_dir = next((tmp_path / "signals").iterdir())
        (signal_dir / "response.9999.stale").write_text("stale", encoding="utf-8")
        second = await Signal(as_state(state), "/bin/zsh").execute("print -u2 second error; return 17")

        assert first == SignalResult(0, "first output\n", "")
        assert second == SignalResult(17, "", "second error\n")
        assert commands == ["print -r -- 'first output'", "print -u2 second error; return 17"]
        assert len(state.sent) == 1
        assert [call for call in kill_calls if call[1] != 0] == [(4242, signal.SIGUSR1), (4242, signal.SIGUSR1)]

        assert {path.name for path in signal_dir.iterdir()} == {
            Signal.INSTALL_LOCK_FILE,
            Signal.OPERATION_LOCK_FILE,
            Signal.BINDING_FILE,
            Signal.IDENTITY_FILE,
        }

    asyncio.run(scenario())


def test_install_is_public_idempotent_and_changed_digest_reinstalls_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        state = FakeState()
        handler = tmp_path / "handler.zsh"
        handler.write_text("handler-v1", encoding="utf-8")
        _configure_fake_process(tmp_path, monkeypatch, handler)

        async def send_text(command: str, suppress: bool) -> None:
            assert suppress is True
            _install_ack_from_command(command, pid=4242)

        state.on_send = send_text
        monkeypatch.setattr(os, "kill", lambda pid, signal_number: None)
        target = Signal(as_state(state), "zsh")

        await target.install()
        await target.install()
        assert len(state.sent) == 1

        handler.write_text("handler-v2", encoding="utf-8")
        await target.install()
        await target.install()
        assert len(state.sent) == 2

    asyncio.run(scenario())


def test_execute_serializes_concurrent_callers_for_one_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = FakeState()
        handler = tmp_path / "handler.zsh"
        handler.write_text("handler-v1", encoding="utf-8")
        _configure_fake_process(tmp_path, monkeypatch, handler)

        async def send_text(command: str, suppress: bool) -> None:
            assert suppress is True
            _install_ack_from_command(command, pid=4242)

        state.on_send = send_text
        commands: list[str] = []
        first_request: list[tuple[Path, str]] = []
        first_started = asyncio.Event()
        second_started = asyncio.Event()

        def fake_kill(pid: int, signal_number: int) -> None:
            if signal_number == 0:
                return

            signal_dir, request, nonce = _request_for_pid(tmp_path / "signals", pid)
            commands.append(request.read_text(encoding="utf-8"))

            if len(commands) == 1:
                (signal_dir / f"started.{pid}.{nonce}").write_text(
                    f"{Signal.PROTOCOL_VERSION}\tstarted\t{pid}\t{nonce}\n", encoding="utf-8"
                )
                first_request.append((signal_dir, nonce))
                first_started.set()
                return

            _publish_fake_result(signal_dir, pid, nonce, SignalResult(0, "second\n", ""))
            second_started.set()

        monkeypatch.setattr(os, "kill", fake_kill)

        first_task = asyncio.create_task(Signal(as_state(state), "zsh").execute("first command"))
        await asyncio.wait_for(first_started.wait(), timeout=1.0)
        second_task = asyncio.create_task(Signal(as_state(state), "zsh").execute("second command"))

        await asyncio.sleep(0.05)
        assert commands == ["first command"]

        signal_dir, first_nonce = first_request[0]
        _publish_fake_result(signal_dir, 4242, first_nonce, SignalResult(0, "first\n", ""))

        assert await first_task == SignalResult(0, "first\n", "")
        await asyncio.wait_for(second_started.wait(), timeout=1.0)
        assert await second_task == SignalResult(0, "second\n", "")
        assert commands == ["first command", "second command"]
        assert len(state.sent) == 1

    asyncio.run(scenario())


def test_install_recognizes_an_existing_handler_while_the_shell_is_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        state = FakeState()
        handler = tmp_path / "handler.zsh"
        handler.write_text("handler-v1", encoding="utf-8")
        _configure_fake_process(tmp_path, monkeypatch, handler)

        async def send_text(command: str, suppress: bool) -> None:
            assert suppress is True
            _install_ack_from_command(command, pid=4242)

        state.on_send = send_text
        monkeypatch.setattr(os, "kill", lambda pid, signal_number: None)
        target = Signal(as_state(state), "zsh")
        await target.install()

        signal_dir = next((tmp_path / "signals").iterdir())
        binding_path = signal_dir / Signal.BINDING_FILE
        version, _, pid, signal_name, digest, generation = binding_path.read_text(encoding="utf-8").strip().split("\t")
        (signal_dir / Signal.BUSY_FILE).write_text(
            f"{version}\tbusy\t{pid}\t{signal_name}\t{digest}\t{generation}\n", encoding="utf-8"
        )
        binding_path.unlink()
        state.job_name = "vim"

        await asyncio.wait_for(target.install(), timeout=0.25)

        assert len(state.sent) == 1
        assert (signal_dir / Signal.IDENTITY_FILE).is_file()

    asyncio.run(scenario())


def test_execute_waits_for_an_installed_busy_shell_without_typing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        state = FakeState()
        handler = tmp_path / "handler.zsh"
        handler.write_text("handler-v1", encoding="utf-8")
        _configure_fake_process(tmp_path, monkeypatch, handler)

        async def send_text(command: str, suppress: bool) -> None:
            assert suppress is True
            _install_ack_from_command(command, pid=4242)

        state.on_send = send_text
        dispatched: list[str] = []

        def fake_kill(pid: int, signal_number: int) -> None:
            if signal_number == 0:
                return

            signal_dir, request, nonce = _request_for_pid(tmp_path / "signals", pid)
            dispatched.append(request.read_text(encoding="utf-8"))
            _publish_fake_result(signal_dir, pid, nonce, SignalResult(0, "queued\n", ""))

        monkeypatch.setattr(os, "kill", fake_kill)
        target = Signal(as_state(state), "zsh")
        await target.install()

        signal_dir = next((tmp_path / "signals").iterdir())
        binding_path = signal_dir / Signal.BINDING_FILE
        binding_payload = binding_path.read_text(encoding="utf-8")
        version, _, pid, signal_name, digest, generation = binding_payload.strip().split("\t")
        (signal_dir / Signal.BUSY_FILE).write_text(
            f"{version}\tbusy\t{pid}\t{signal_name}\t{digest}\t{generation}\n", encoding="utf-8"
        )
        binding_path.unlink()
        state.job_name = "vim"

        execute_task = asyncio.create_task(target.execute("queued command"))
        await asyncio.sleep(0.05)

        assert dispatched == []
        assert len(state.sent) == 1

        binding_path.write_text(binding_payload, encoding="utf-8")
        (signal_dir / Signal.BUSY_FILE).unlink()

        assert await asyncio.wait_for(execute_task, timeout=1.0) == SignalResult(0, "queued\n", "")
        assert dispatched == ["queued command"]
        assert len(state.sent) == 1

    asyncio.run(scenario())


def test_missing_start_ack_invalidates_cached_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = FakeState()
        handler = tmp_path / "handler.zsh"
        handler.write_text("handler-v1", encoding="utf-8")
        _configure_fake_process(tmp_path, monkeypatch, handler)
        monkeypatch.setattr(Signal, "START_TIMEOUT", 0.01)
        monkeypatch.setattr(Signal, "POLL_INTERVAL", 0.0)

        async def send_text(command: str, suppress: bool) -> None:
            _install_ack_from_command(command, pid=4242)

        state.on_send = send_text
        monkeypatch.setattr(os, "kill", lambda pid, signal_number: None)

        with pytest.raises(TimeoutError, match="shell acknowledgment"):
            await Signal(as_state(state), "zsh").execute("print never-started")

        signal_dir = next((tmp_path / "signals").iterdir())
        remaining = {path.name for path in signal_dir.iterdir()}
        assert Signal.BINDING_FILE not in remaining
        assert Signal.IDENTITY_FILE not in remaining
        assert not any(
            name.startswith(("request.", "started.", "response.", "stdout.", "stderr.")) for name in remaining
        )

    asyncio.run(scenario())


def test_execute_never_signals_without_install_ack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = FakeState()
        handler = tmp_path / "handler.zsh"
        handler.touch()
        monkeypatch.setattr(Signal, "SIGNAL_ROOT", tmp_path / "signals")
        monkeypatch.setattr(Signal, "SIGNAL_SCRIPT", handler)
        monkeypatch.setattr(Signal, "INSTALL_TIMEOUT", 0.01)
        monkeypatch.setattr(Signal, "POLL_INTERVAL", 0.0)

        def unexpected_kill(*_: object) -> None:
            raise AssertionError("os.kill must not run before installation is acknowledged")

        monkeypatch.setattr(os, "kill", unexpected_kill)

        with pytest.raises(TimeoutError, match="shell acknowledgment"):
            await Signal(as_state(state), "zsh").execute("print never-installed")

    asyncio.run(scenario())


def test_execute_rejects_nul_and_unsupported_shell_before_installing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        state = FakeState()
        monkeypatch.setattr(Signal, "SIGNAL_ROOT", tmp_path / "signals")

        with pytest.raises(ValueError, match="NUL"):
            await Signal(as_state(state), "zsh").execute("print before\0after")

        with pytest.raises(RuntimeError, match="requires zsh"):
            await Signal(as_state(state), "/bin/bash").execute("print unsupported")

        assert state.sent == []
        assert not (tmp_path / "signals").exists()

    asyncio.run(scenario())


def test_execute_does_not_bootstrap_into_a_foreground_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = FakeState()
        state.job_name = "vim"
        handler = tmp_path / "handler.zsh"
        handler.touch()
        monkeypatch.setattr(Signal, "SIGNAL_ROOT", tmp_path / "signals")
        monkeypatch.setattr(Signal, "SIGNAL_SCRIPT", handler)

        def unexpected_kill(*_: object) -> None:
            raise AssertionError("a busy, uninstalled target must not receive a signal")

        monkeypatch.setattr(os, "kill", unexpected_kill)

        with pytest.raises(SignalShellBusyError, match="not the foreground job"):
            await Signal(as_state(state), "zsh").execute("print unsafe-bootstrap")

        assert state.sent == []

    asyncio.run(scenario())


def _write_zsh_request(control: Path, pid: int, nonce: str, command: str) -> None:
    (control / f"stdout.{pid}.{nonce}").write_bytes(b"")
    (control / f"stderr.{pid}.{nonce}").write_bytes(b"")
    (control / f"request.{pid}.{nonce}").write_text(command, encoding="utf-8")


def test_zsh_handler_executes_general_commands_in_parent_scope(tmp_path: Path) -> None:
    control = tmp_path / "control"
    hook_output = tmp_path / "hook-state"
    target = tmp_path / "target with spaces\nand newline"
    control.mkdir(mode=0o700)
    target.mkdir()

    environment = os.environ.copy()
    environment.update(
        {
            "SIGNAL_TEST_CONTROL": str(control),
            "SIGNAL_TEST_HANDLER": str(Signal.SIGNAL_SCRIPT),
            "SIGNAL_TEST_HOOK": str(hook_output),
        }
    )
    digest = "a" * 64
    install_nonce = "0123456789abcdef0123456789abcdef"
    command = f"""
TRAPUSR1() {{ :; }}
SIGNAL_PROMPT_COUNT=0
prompt_probe() {{
    (( SIGNAL_PROMPT_COUNT += 1 ))
    print -rn -- "$SIGNAL_PROMPT_COUNT|$PWD|$SIGNAL_PLAIN|$SIGNAL_EXPORTED" >| "$SIGNAL_TEST_HOOK"
}}
precmd_functions=(prompt_probe)
source "$SIGNAL_TEST_HANDLER" "$SIGNAL_TEST_CONTROL" {install_nonce} {digest}
while true; do sleep 0.05; done
"""

    process = subprocess.Popen(
        ["/bin/zsh", "-fc", command], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    try:
        install_fields = _wait_for_file(control / f"install.{install_nonce}").decode().strip().split("\t")
        binding_fields = _wait_for_file(control / Signal.BINDING_FILE).decode().strip().split("\t")
        assert install_fields[:4] == [Signal.PROTOCOL_VERSION, "ok", str(process.pid), "USR2"]
        assert binding_fields == [Signal.PROTOCOL_VERSION, "ready", str(process.pid), "USR2", digest, install_nonce]

        first_nonce = "11111111111111111111111111111111"
        first_command = (
            f"typeset SIGNAL_TYPED=typed; SIGNAL_PLAIN=plain; export SIGNAL_EXPORTED=exported; "
            f"alias signal_alias='print -r -- alias-ok'; "
            f"signal_function() {{ print -r -- function-ok; }}; "
            f"setopt NO_BEEP; builtin cd -- {shlex.quote(str(target))}; "
            "sleep 0.05; "
            "print -r -- first-out; print -r -- second-out; "
            "print -u2 -r -- first-err; print -u2 -r -- second-err; return 17"
        )
        _write_zsh_request(control, process.pid, first_nonce, first_command)
        os.kill(process.pid, signal.SIGUSR2)

        assert _wait_for_file(control / f"started.{process.pid}.{first_nonce}").decode().strip().split("\t") == [
            Signal.PROTOCOL_VERSION,
            "started",
            str(process.pid),
            first_nonce,
        ]
        assert _wait_for_file(control / Signal.BUSY_FILE).decode().strip().split("\t") == [
            Signal.PROTOCOL_VERSION,
            "busy",
            str(process.pid),
            "USR2",
            digest,
            install_nonce,
        ]
        assert _wait_for_file(control / f"response.{process.pid}.{first_nonce}").decode().strip().split("\t") == [
            Signal.PROTOCOL_VERSION,
            "ok",
            str(process.pid),
            first_nonce,
            "17",
            "0",
            "0",
        ]
        assert (control / f"stdout.{process.pid}.{first_nonce}").read_text(encoding="utf-8") == (
            "first-out\nsecond-out\n"
        )
        assert (control / f"stderr.{process.pid}.{first_nonce}").read_text(encoding="utf-8") == (
            "first-err\nsecond-err\n"
        )
        assert hook_output.read_text(encoding="utf-8") == f"1|{target}|plain|exported"
        _wait_for_absence(control / Signal.BUSY_FILE)
        _wait_for_file(control / Signal.BINDING_FILE)

        second_nonce = "22222222222222222222222222222222"
        second_command = (
            "signal_alias; signal_function; "
            'print -r -- "$PWD|$SIGNAL_TYPED|$SIGNAL_PLAIN|$SIGNAL_EXPORTED|'
            '$PAGER|$GIT_PAGER|$MANPAGER|$BAT_PAGER|$LESS|${options[beep]}"'
        )
        _write_zsh_request(control, process.pid, second_nonce, second_command)
        os.kill(process.pid, signal.SIGUSR2)

        assert _wait_for_file(control / f"response.{process.pid}.{second_nonce}").decode().strip().split("\t")[4:] == [
            "0",
            "0",
            "0",
        ]
        assert (control / f"stdout.{process.pid}.{second_nonce}").read_text(encoding="utf-8") == (
            f"alias-ok\nfunction-ok\n{target}|typed|plain|exported|cat|cat|cat|cat|FRX|off\n"
        )
        assert hook_output.read_text(encoding="utf-8") == f"2|{target}|plain|exported"
        _wait_for_absence(control / Signal.BUSY_FILE)
        assert process.poll() is None
    finally:
        process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)


def test_zsh_handler_withdraws_readiness_when_list_trap_is_replaced(tmp_path: Path) -> None:
    control = tmp_path / "control"
    control.mkdir(mode=0o700)
    digest = "b" * 64
    nonce = "fedcba9876543210fedcba9876543210"
    environment = os.environ.copy()
    environment.update({"SIGNAL_TEST_CONTROL": str(control), "SIGNAL_TEST_HANDLER": str(Signal.SIGNAL_SCRIPT)})
    command = f"""
source "$SIGNAL_TEST_HANDLER" "$SIGNAL_TEST_CONTROL" {nonce} {digest}
[[ -f "$SIGNAL_TEST_CONTROL/{Signal.BINDING_FILE}" ]] && print ready
_iterm2_api_wrapper_signal_deactivate
[[ ! -e "$SIGNAL_TEST_CONTROL/{Signal.BINDING_FILE}" ]] && print inactive
_iterm2_api_wrapper_signal_activate
[[ -f "$SIGNAL_TEST_CONTROL/{Signal.BINDING_FILE}" ]] && print reactivated
trap ':' "$_ITERM2_API_WRAPPER_SIGNAL_NAME"
_iterm2_api_wrapper_signal_activate
[[ ! -e "$SIGNAL_TEST_CONTROL/{Signal.BINDING_FILE}" ]] && print replaced
"""

    completed = subprocess.run(
        ["/bin/zsh", "-fc", command], check=True, capture_output=True, env=environment, text=True
    )
    assert completed.stdout.splitlines() == ["ready", "inactive", "reactivated", "replaced"]
