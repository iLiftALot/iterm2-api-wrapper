from __future__ import annotations

from iterm2_api_wrapper.typings import CommandExecutionResult, CommandExecutionStatus, HexCodeEnum


CommandExitCode = CommandExecutionStatus.ExitCode


def test_hexcode_enum_encodes_control_bytes() -> None:
    assert str(HexCodeEnum.CNTRL_C) == "\x03"
    assert str(HexCodeEnum.ESC) == "\x1b"
    assert str(HexCodeEnum.B) == "b"
    # Multi-byte meta sequence (ESC + char).
    assert str(HexCodeEnum.ALT_B) == "\x1bb"


def test_exit_code_coerce_known_and_unknown() -> None:
    assert CommandExitCode.coerce(0) is CommandExitCode.SUCCESS
    assert CommandExitCode.coerce(1) is CommandExitCode.GENERAL_FAILURE
    # Unknown utility-specific status is returned unchanged.
    assert CommandExitCode.coerce(42) == 42


def test_status_normalizes_known_exit_code_on_init() -> None:
    status = CommandExecutionStatus(prompt_id="p", command="echo hi", exit_code=0)

    assert status.exit_code is CommandExitCode.SUCCESS
    assert status.code == 0
    assert status.succeeded is True
    assert status.failed is False
    assert status.known_exit_code is CommandExitCode.SUCCESS
    assert status.was_signaled is False
    assert status.signal_number is None


def test_status_preserves_unknown_exit_code() -> None:
    status = CommandExecutionStatus(prompt_id=None, command=None, exit_code=42)

    assert status.exit_code == 42
    assert status.succeeded is False
    assert status.failed is True
    assert status.known_exit_code is None


def test_status_signal_interpretation() -> None:
    status = CommandExecutionStatus(prompt_id=None, command="sleep", exit_code=130)

    assert status.was_signaled is True
    assert status.signal_number == 2  # 130 - 128
    assert status.succeeded is False


def test_timed_out_status_is_not_coerced_and_reports_failure() -> None:
    status = CommandExecutionStatus(
        prompt_id=None, command=None, exit_code=CommandExitCode.GENERAL_FAILURE, timed_out=True
    )

    assert status.timed_out is True
    assert status.known_exit_code is None
    assert status.was_signaled is False
    assert status.signal_number is None
    assert status.succeeded is False
    assert status.failed is True


def test_command_execution_result_str_returns_output() -> None:
    status = CommandExecutionStatus(prompt_id="p", command="echo hi", exit_code=0)
    result = CommandExecutionResult(output="hi", status=status)

    assert str(result) == "hi"
    assert result.output == "hi"
