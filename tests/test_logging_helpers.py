from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console
from rich.text import Text

from iterm2_api_wrapper._logging import config as config_module
from iterm2_api_wrapper._logging import logger as logger_module
from iterm2_api_wrapper._logging import styles


def test_log_level_helpers_resolve_valid_and_invalid_values() -> None:
    assert config_module._resolve_level("debug") is config_module.LogLevel.DEBUG
    assert config_module._severity("ERROR") > config_module._severity("INFO")

    with pytest.raises(ValueError, match="Invalid log level"):
        config_module._resolve_level("verbose")


def test_gradient_helpers_style_text() -> None:
    assert styles.gradient_colors(["red"], 3) == ["red", "red", "red"]
    assert styles.gradient_colors(["red", "blue"], 1) == ["red"]
    colors = styles.gradient_colors(["#000000", "#ffffff"], 3)
    assert colors == ["rgb(0,0,0)", "rgb(127,127,127)", "rgb(255,255,255)"]

    text = Text("abc")
    styles.GradientHighlighter(["red", "blue"]).highlight(text)
    assert text.spans


def test_prefix_rule_renders_rule_to_remaining_width() -> None:
    console = Console(width=16, record=True)
    console.print(logger_module._PrefixRule(Text("[INFO]")))

    assert "[INFO]" in console.export_text()


def test_file_console_manager_lazily_creates_and_rebuilds(tmp_path: Path) -> None:
    path = tmp_path / "log.txt"
    manager = logger_module._FileConsoleManager.get_or_create(
        path, file_manager_config={"clear_file_on_init": True}, console_config={"force_terminal": False, "width": 40}
    )

    manager.console.print("first")
    assert "first" in path.read_text()

    manager.reset_config(console_config={"width": 60})
    manager.console.print("second")
    manager.close()

    content = path.read_text()
    assert "first" in content
    assert "second" in content


def test_terminal_console_manager_rebuilds_on_config_change() -> None:
    manager = logger_module._TerminalConsoleManager(width=20)
    first = manager.console

    manager.reset_config(width=30)

    assert manager.console is not first
    manager.close()
    assert manager._console is None


def test_pretty_log_filters_levels_context_and_file_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_path = tmp_path / "pretty.log"
    monkeypatch.setattr(logger_module, "LOG_PATH", log_path)
    logger_module.PrettyLog._registry.clear()
    logger_module._FileConsoleManager._instances.clear()

    log = logger_module.PrettyLog(
        "root",
        mode="file",
        level="INFO",
        pretty_config={
            "logger_config": {"markup": False},
            "file_manager_config": {"clear_file_on_init": True},
            "file_console_config": {"force_terminal": False, "width": 120, "log_path": False, "log_time": False},
            "terminal_console_config": {"force_terminal": False, "width": 120},
        },
    )
    child = log.child("child", component="api")

    log.debug("hidden")
    log.info("visible")
    child.warning("child visible")
    with log.scoped_level("DEBUG"):
        log.debug("debug visible")
    with log.scoped_context(request_id="abc"):
        assert "request_id" in log._context
    assert "request_id" not in log._context

    log.add_filter(lambda level, messages: "blocked" not in str(messages[0]))
    log.info("blocked")
    log.disable()
    log.info("disabled")
    log.enable()
    log.error("enabled error")

    content = log_path.read_text()
    assert "visible" in content
    assert "child visible" in content
    assert "debug visible" in content
    assert "enabled error" in content
    assert "hidden" not in content
    assert "blocked" not in content
    assert "disabled" not in content
