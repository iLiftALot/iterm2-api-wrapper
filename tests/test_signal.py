from __future__ import annotations

import asyncio
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path

import pytest

from iterm2_api_wrapper.utils.signal import Signal

from .fake import FakeState, as_state


def _wait_for_file(
    path: Path,
    timeout: float = 2.0,
) -> bytes:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            time.sleep(0.01)

    raise TimeoutError(path)


def _install_ack_from_command(
    command: str,
    *,
    pid: int,
) -> tuple[Path, str, str]:
    (
        _,
        _,
        _,
        signal_dir_text,
        nonce,
        digest,
    ) = shlex.split(command)

    signal_dir = Path(signal_dir_text)

    (signal_dir / Signal.BINDING_FILE).write_text(
        (f"{Signal.PROTOCOL_VERSION}\tready\t{pid}\tUSR1\t{digest}\t{nonce}\n"),
        encoding="utf-8",
    )

    (signal_dir / f"install.{nonce}").write_text(
        (f"{Signal.PROTOCOL_VERSION}\tok\t{pid}\tUSR1\t{nonce}\t{digest}\n"),
        encoding="utf-8",
    )

    return signal_dir, nonce, digest


def test_cd_sources_once_then_reuses_cached_live_shell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        state = FakeState()
        target_one = tmp_path / "target-one"
        target_two = tmp_path / "target-two"
        handler = tmp_path / "handler.zsh"

        target_one.mkdir()
        target_two.mkdir()
        handler.write_text(
            "handler-v1",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            Signal,
            "SIGNAL_ROOT",
            tmp_path / "signals",
        )
        monkeypatch.setattr(
            Signal,
            "SIGNAL_SCRIPT",
            handler,
        )
        monkeypatch.setattr(
            Signal,
            "_read_process_identity",
            staticmethod(
                lambda pid: (
                    "ttys123",
                    "Fri Jul 24 21:00:00 2026",
                    "/bin/zsh",
                )
            ),
        )

        async def send_text(
            command: str,
            suppress: bool,
        ) -> None:
            assert suppress is True
            _install_ack_from_command(
                command,
                pid=4242,
            )

        state.on_send = send_text
        kill_calls: list[tuple[int, int]] = []

        def fake_kill(
            pid: int,
            signal_number: int,
        ) -> None:
            kill_calls.append(
                (
                    pid,
                    signal_number,
                )
            )

            if signal_number == 0:
                return

            signal_dir = next((tmp_path / "signals").iterdir())
            request = next(signal_dir.glob(f"request.{pid}.*"))
            nonce = request.name.rsplit(
                ".",
                1,
            )[1]

            (signal_dir / f"response.{pid}.{nonce}").write_text(
                (f"{Signal.PROTOCOL_VERSION}\tok\t{pid}\t{nonce}\t0\t0\t0\n"),
                encoding="utf-8",
            )

        monkeypatch.setattr(
            os,
            "kill",
            fake_kill,
        )

        # Two distinct Signal instances model two distinct run_command calls.
        await Signal(
            as_state(state),
            "/bin/zsh",
        ).cd(str(target_one))

        await Signal(
            as_state(state),
            "/bin/zsh",
        ).cd(str(target_two))

        # Only the first operation bootstraps through shell text.
        assert len(state.sent) == 1

        # Both directory changes still use the signal protocol.
        assert kill_calls == [
            (
                4242,
                0,
            ),
            (
                4242,
                signal.SIGUSR1,
            ),
            (
                4242,
                0,
            ),
            (
                4242,
                signal.SIGUSR1,
            ),
        ]

        signal_dir = next((tmp_path / "signals").iterdir())

        assert {path.name for path in signal_dir.iterdir()} == {
            Signal.INSTALL_LOCK_FILE,
            Signal.BINDING_FILE,
            Signal.IDENTITY_FILE,
        }

    asyncio.run(scenario())


def test_changed_handler_digest_forces_one_reinstall(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        state = FakeState()
        target = tmp_path / "target"
        handler = tmp_path / "handler.zsh"

        target.mkdir()
        handler.write_text(
            "handler-v1",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            Signal,
            "SIGNAL_ROOT",
            tmp_path / "signals",
        )
        monkeypatch.setattr(
            Signal,
            "SIGNAL_SCRIPT",
            handler,
        )
        monkeypatch.setattr(
            Signal,
            "_read_process_identity",
            staticmethod(
                lambda pid: (
                    "ttys123",
                    "Fri Jul 24 21:00:00 2026",
                    "/bin/zsh",
                )
            ),
        )

        async def send_text(
            command: str,
            suppress: bool,
        ) -> None:
            assert suppress is True
            _install_ack_from_command(
                command,
                pid=4242,
            )

        state.on_send = send_text

        def fake_kill(
            pid: int,
            signal_number: int,
        ) -> None:
            if signal_number == 0:
                return

            signal_dir = next((tmp_path / "signals").iterdir())
            request = next(signal_dir.glob(f"request.{pid}.*"))
            nonce = request.name.rsplit(
                ".",
                1,
            )[1]

            (signal_dir / f"response.{pid}.{nonce}").write_text(
                (f"{Signal.PROTOCOL_VERSION}\tok\t{pid}\t{nonce}\t0\t0\t0\n"),
                encoding="utf-8",
            )

        monkeypatch.setattr(
            os,
            "kill",
            fake_kill,
        )

        await Signal(
            as_state(state),
            "zsh",
        ).cd(str(target))

        handler.write_text(
            "handler-v2",
            encoding="utf-8",
        )

        await Signal(
            as_state(state),
            "zsh",
        ).cd(str(target))

        assert len(state.sent) == 2

    asyncio.run(scenario())


def test_response_timeout_invalidates_cached_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        state = FakeState()
        target = tmp_path / "target"
        handler = tmp_path / "handler.zsh"

        target.mkdir()
        handler.write_text(
            "handler-v1",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            Signal,
            "SIGNAL_ROOT",
            tmp_path / "signals",
        )
        monkeypatch.setattr(
            Signal,
            "SIGNAL_SCRIPT",
            handler,
        )
        monkeypatch.setattr(
            Signal,
            "RESPONSE_TIMEOUT",
            0.01,
        )
        monkeypatch.setattr(
            Signal,
            "POLL_INTERVAL",
            0.0,
        )
        monkeypatch.setattr(
            Signal,
            "_read_process_identity",
            staticmethod(
                lambda pid: (
                    "ttys123",
                    "Fri Jul 24 21:00:00 2026",
                    "/bin/zsh",
                )
            ),
        )

        async def send_text(
            command: str,
            suppress: bool,
        ) -> None:
            _install_ack_from_command(
                command,
                pid=4242,
            )

        state.on_send = send_text

        monkeypatch.setattr(
            os,
            "kill",
            lambda pid, signal_number: None,
        )

        with pytest.raises(
            TimeoutError,
            match="shell acknowledgment",
        ):
            await Signal(
                as_state(state),
                "zsh",
            ).cd(str(target))

        signal_dir = next((tmp_path / "signals").iterdir())
        remaining = {path.name for path in signal_dir.iterdir()}

        assert Signal.BINDING_FILE not in remaining
        assert Signal.IDENTITY_FILE not in remaining

    asyncio.run(scenario())


def test_cd_never_signals_without_install_ack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        state = FakeState()
        target = tmp_path / "target"
        handler = tmp_path / "handler.zsh"

        target.mkdir()
        handler.touch()

        monkeypatch.setattr(
            Signal,
            "SIGNAL_ROOT",
            tmp_path / "signals",
        )
        monkeypatch.setattr(
            Signal,
            "SIGNAL_SCRIPT",
            handler,
        )
        monkeypatch.setattr(
            Signal,
            "INSTALL_TIMEOUT",
            0.01,
        )
        monkeypatch.setattr(
            Signal,
            "POLL_INTERVAL",
            0.0,
        )

        def unexpected_kill(
            *_: object,
        ) -> None:
            raise AssertionError("os.kill must not run before installation is acknowledged")

        monkeypatch.setattr(
            os,
            "kill",
            unexpected_kill,
        )

        with pytest.raises(
            TimeoutError,
            match="shell acknowledgment",
        ):
            await Signal(
                as_state(state),
                "zsh",
            ).cd(str(target))

    asyncio.run(scenario())


def test_cd_rejects_unsupported_shell_before_installing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        state = FakeState()
        target = tmp_path / "target"

        target.mkdir()

        def unexpected_kill(
            *_: object,
        ) -> None:
            raise AssertionError("unsupported shells must never receive a signal")

        monkeypatch.setattr(
            os,
            "kill",
            unexpected_kill,
        )

        with pytest.raises(
            RuntimeError,
            match="require zsh",
        ):
            await Signal(
                as_state(state),
                "/bin/bash",
            ).cd(str(target))

        assert state.sent == []

    asyncio.run(scenario())


def test_zsh_handler_binding_lifecycle_and_signal_dispatch(
    tmp_path: Path,
) -> None:
    control = tmp_path / "control"
    target = tmp_path / "target with spaces\nand newline"
    hook_output = tmp_path / "hook-pwd"

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
prompt_probe() {{ print -rn -- "$PWD" >| "$SIGNAL_TEST_HOOK"; }}
precmd_functions=(prompt_probe)
source "$SIGNAL_TEST_HANDLER" "$SIGNAL_TEST_CONTROL" {install_nonce} {digest}
while true; do sleep 0.05; done
"""

    process = subprocess.Popen(
        [
            "/bin/zsh",
            "-fc",
            command,
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        install_fields = _wait_for_file(control / f"install.{install_nonce}").decode().strip().split("\t")
        binding_fields = _wait_for_file(control / Signal.BINDING_FILE).decode().strip().split("\t")

        assert install_fields[:2] == [
            Signal.PROTOCOL_VERSION,
            "ok",
        ]
        assert install_fields[3] == "USR2"

        assert binding_fields == [
            Signal.PROTOCOL_VERSION,
            "ready",
            str(process.pid),
            "USR2",
            digest,
            install_nonce,
        ]

        nonce = "requestnonce"
        request = control / f"request.{process.pid}.{nonce}"
        request.write_bytes(os.fsencode(str(target)) + b"\0")

        os.kill(
            process.pid,
            signal.SIGUSR2,
        )

        response_fields = _wait_for_file(control / (f"response.{process.pid}.{nonce}")).decode().strip().split("\t")

        assert response_fields == [
            Signal.PROTOCOL_VERSION,
            "ok",
            str(process.pid),
            nonce,
            "0",
            "0",
            "0",
        ]
        assert hook_output.read_text(encoding="utf-8") == str(target)
        assert process.poll() is None
    finally:
        process.terminate()

        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)


def test_zsh_handler_withdraws_readiness_when_its_trap_is_replaced(
    tmp_path: Path,
) -> None:
    control = tmp_path / "control"
    control.mkdir(mode=0o700)

    digest = "b" * 64
    nonce = "fedcba9876543210fedcba9876543210"

    environment = os.environ.copy()
    environment.update(
        {
            "SIGNAL_TEST_CONTROL": str(control),
            "SIGNAL_TEST_HANDLER": str(Signal.SIGNAL_SCRIPT),
        }
    )

    command = f"""
source "$SIGNAL_TEST_HANDLER" "$SIGNAL_TEST_CONTROL" {nonce} {digest}
[[ -f "$SIGNAL_TEST_CONTROL/{Signal.BINDING_FILE}" ]] && print ready
_iterm2_api_wrapper_signal_deactivate
[[ ! -e "$SIGNAL_TEST_CONTROL/{Signal.BINDING_FILE}" ]] && print inactive
_iterm2_api_wrapper_signal_activate
[[ -f "$SIGNAL_TEST_CONTROL/{Signal.BINDING_FILE}" ]] && print reactivated
functions[TRAPUSR1]=':'
_iterm2_api_wrapper_signal_activate
[[ ! -e "$SIGNAL_TEST_CONTROL/{Signal.BINDING_FILE}" ]] && print replaced
"""

    completed = subprocess.run(
        [
            "/bin/zsh",
            "-fc",
            command,
        ],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert completed.stdout.splitlines() == [
        "ready",
        "inactive",
        "reactivated",
        "replaced",
    ]
