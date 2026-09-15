from __future__ import annotations

import inspect
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from rich.text import Text

from iterm2_api_wrapper._logging import config as config_module
from iterm2_api_wrapper._logging import logger as logger_module
from iterm2_api_wrapper._logging.config import ConsoleConfig, LogLevel, PrettyLogConfig


def _logger_config(path: Path, terminal_buffer: StringIO | None = None) -> PrettyLogConfig:
    terminal: ConsoleConfig = {"force_terminal": False, "width": 200, "log_path": False, "log_time": False}
    if terminal_buffer is not None:
        terminal["file"] = terminal_buffer
    return {
        "logger_config": {"markup": False, "highlight": True, "source_link": "none"},
        "file_manager_config": {
            "path": path,
            "encoding": "utf-8",
            "clear_file_on_init": True,
            "flush_each_write": True,
        },
        "file_console_config": {
            "force_terminal": False,
            "color_system": None,
            "no_color": True,
            "width": 200,
            "log_path": False,
            "log_time": False,
        },
        "terminal_console_config": terminal,
        "traceback_config": {"show_locals": False, "width": 160},
    }


def test_log_level_helpers_resolve_valid_and_invalid_values() -> None:
    assert config_module._resolve_level("debug") is config_module.LogLevel.DEBUG
    assert config_module._severity("ERROR") > config_module._severity("INFO")

    with pytest.raises(ValueError, match="Invalid log level"):
        config_module._resolve_level("verbose")


def test_import_does_not_install_hooks_or_initialize_output() -> None:
    script = """
import sys
before = sys.excepthook
import iterm2_api_wrapper._logging.logger as module
assert sys.excepthook is before
assert module._standalone_terminal is None
assert all(not item._sinks.terminal.initialized for item in module.PrettyLog._registry.values())
assert all(not item._sinks.file.initialized for item in module.PrettyLog._registry.values())
assert len({id(item._sinks) for item in module.PrettyLog._registry.values()}) == 1
module.install_pretty_tracebacks({"show_locals": False})
assert sys.excepthook is not before
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_pretty_log_filters_levels_context_and_file_output(tmp_path: Path) -> None:
    path = tmp_path / "pretty.log"
    log = logger_module.PrettyLog("facade", mode="file", level="INFO", pretty_config=_logger_config(path))
    child = log.child("child", component="api")

    log.debug("hidden")
    log.info("visible")
    child.warning("child visible")
    with log.scoped_level("DEBUG") as scoped:
        assert scoped is log
        log.debug("debug visible")
    with log.scoped_context(request_id="abc"):
        log.info("context visible")

    def blocked(level: LogLevel, messages: tuple[object, ...]) -> bool:
        del level
        return "blocked" not in str(messages[0])

    log.add_filter(blocked)
    log.info("blocked")
    assert log.remove_filter(blocked) is True
    assert log.remove_filter(blocked) is False
    log.add_filter(blocked)
    log.clear_filters()
    log.disable()
    log.info("disabled")
    log.enable()
    log.error("enabled error")
    log.flush()

    content = path.read_text(encoding="utf-8")
    assert "visible" in content
    assert "child visible" in content
    assert "component=api" in content
    assert "debug visible" in content
    assert "request_id=abc" in content
    assert "enabled error" in content
    assert "hidden" not in content
    assert "blocked" not in content
    assert "disabled" not in content
    assert log.is_enabled_for("INFO") is True
    assert log.is_enabled_for("DEBUG") is False

    log.close()
    child.info("child survives parent close")
    child.close()
    assert "child survives parent close" in path.read_text(encoding="utf-8")


def test_hierarchy_and_configuration_are_isolated(tmp_path: Path) -> None:
    root = logger_module.PrettyLog("hierarchy", mode="file", pretty_config=_logger_config(tmp_path / "tree.log"))
    child = logger_module.PrettyLog.get_logger("hierarchy.worker")

    assert child.parent is root
    assert root.children == {"hierarchy.worker": child}
    assert logger_module.PrettyLog.get_logger("hierarchy.worker") is child
    assert logger_module.PrettyLog.list_loggers()["hierarchy"] is root
    assert child._sinks is root._sinks

    child.configure(logger_config={"source_link": "file"})
    assert child.pretty_config.get("logger_config", {}).get("source_link") == "file"
    assert root.pretty_config.get("logger_config", {}).get("source_link") == "none"
    child.configure(terminal_console_config={"width": 77})
    assert child._sinks is not root._sinks
    assert child.pretty_config.get("terminal_console_config", {}).get("width") == 77
    assert root.pretty_config.get("terminal_console_config", {}).get("width") == 200

    child.close()
    root.close()


def test_active_call_lease_survives_concurrent_logger_close(tmp_path: Path) -> None:
    path = tmp_path / "leased.log"
    log = logger_module.PrettyLog("leased", mode="file", pretty_config=_logger_config(path))
    resolved = log._resolve_call({})

    assert resolved.sinks.reference_count == 2
    log.close()
    assert resolved.sinks.reference_count == 1
    resolved.sinks.emit("file", Text("terminal"), Text("leased entry"))
    resolved.close()
    resolved.close()

    assert resolved.sinks.reference_count == 0
    assert path.read_text(encoding="utf-8") == "leased entry\n"


def test_source_location_uses_the_public_call_site(tmp_path: Path) -> None:
    path = tmp_path / "source.log"
    pretty_config = _logger_config(path)
    pretty_config.setdefault("file_console_config", {})["log_path"] = True
    pretty_config.setdefault("logger_config", {})["source_link"] = "none"
    log = logger_module.PrettyLog("source", mode="file", pretty_config=pretty_config)

    frame = inspect.currentframe()
    assert frame is not None
    expected_line = frame.f_lineno + 1
    log.info("source location")
    del frame
    log.close()

    assert f"{Path(__file__).name}:{expected_line}" in path.read_text(encoding="utf-8")


def test_ordinary_call_locals_are_explicitly_opt_in(tmp_path: Path) -> None:
    path = tmp_path / "locals.log"
    log = logger_module.PrettyLog("locals", mode="file", pretty_config=_logger_config(path))
    local_secret = "-".join(("ordinary", "local", "value"))

    log.info("without locals")
    assert local_secret not in path.read_text(encoding="utf-8")
    log.info("with locals", log_locals=True)
    log.close()

    content = path.read_text(encoding="utf-8")
    assert "local_secret" in content
    assert local_secret in content


def test_exception_obeys_mode_threshold_filter_and_locals_policy(tmp_path: Path) -> None:
    path = tmp_path / "exceptions.log"
    terminal_buffer = StringIO()
    log = logger_module.PrettyLog(
        "exceptions", mode="all", level="ERROR", pretty_config=_logger_config(path, terminal_buffer)
    )

    hidden_local = "-".join(("terminal", "secret"))
    try:
        raise RuntimeError("terminal failure")
    except RuntimeError:
        assert hidden_local
        log.exception("terminal only", mode="terminal")

    assert "terminal only" in terminal_buffer.getvalue()
    assert "terminal failure" in terminal_buffer.getvalue()
    assert "terminal-secret" not in terminal_buffer.getvalue()
    assert not path.exists()

    previous_terminal = terminal_buffer.getvalue()
    try:
        raise ValueError("file failure")
    except ValueError:
        log.exception("file only", mode="file")

    assert terminal_buffer.getvalue() == previous_terminal
    assert "file only" in path.read_text(encoding="utf-8")
    assert "file failure" in path.read_text(encoding="utf-8")

    log.set_level("CRITICAL")
    try:
        raise RuntimeError("threshold suppressed")
    except RuntimeError:
        log.exception("threshold suppressed", mode="file")
    log.set_level("ERROR")
    log.add_filter(lambda level, messages: False)
    try:
        raise RuntimeError("filter suppressed")
    except RuntimeError:
        log.exception("filter suppressed", mode="file")
    log.close()

    content = path.read_text(encoding="utf-8")
    assert "threshold suppressed" not in content
    assert "filter suppressed" not in content


def test_timer_logs_success_and_failure_then_reraises(tmp_path: Path) -> None:
    path = tmp_path / "timer.log"
    log = logger_module.PrettyLog("timer", mode="file", pretty_config=_logger_config(path))

    with log.timer("successful operation") as active:
        assert active is log

    with pytest.raises(RuntimeError, match="expected failure"):
        with log.timer("failed operation"):
            raise RuntimeError("expected failure")
    log.close()

    content = path.read_text(encoding="utf-8")
    assert "successful operation completed in" in content
    assert "failed operation failed after" in content
    assert "expected failure" in content


def test_invalid_modes_are_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid log mode"):
        logger_module._validate_mode("invalid")
