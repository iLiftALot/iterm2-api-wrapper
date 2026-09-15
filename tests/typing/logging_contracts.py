from __future__ import annotations

from collections.abc import Mapping

from rich.style import Style
from rich.theme import Theme
from typing_extensions import assert_type

from iterm2_api_wrapper._logging import PrettyLog
from iterm2_api_wrapper._logging.config import (
    ConsoleConfig,
    FileManagerConfig,
    LogCallConfig,
    LogConfig,
    LogMode,
    PrettyLogConfig,
    SourceLinkMode,
    TracebackConfig,
    get_default_log_config,
    merge_pretty_config,
)
from iterm2_api_wrapper._logging.styles import LogStyle, StyleLike, StyleSpec, ThemeStyles, create_log_theme


def _check_style_contracts() -> None:
    spec = StyleSpec(color="bright_cyan", bold=True, underline2=False)
    style_like: StyleLike = LogStyle.SUCCESS
    typed_styles: ThemeStyles = {"logging.level.info": spec, "log.success": "bold green"}
    raw_styles: dict[str, str] = {"application.custom": "italic blue"}
    rich_styles: Mapping[str, Style] = {"application.rich": Style(color="yellow")}

    assert_type(spec.to_rich_style(), Style)
    assert_type(create_log_theme(typed_styles), Theme)
    assert_type(create_log_theme(raw_styles), Theme)
    assert_type(create_log_theme(rich_styles), Theme)

    del style_like


def _check_config_contracts() -> None:
    mode: LogMode = "all"
    source_link: SourceLinkMode = "vscode"
    logger_config: LogConfig = {
        "style": StyleSpec(color="cyan"),
        "justify": "left",
        "overflow": "ellipsis",
        "source_link": source_link,
    }
    file_manager: FileManagerConfig = {
        "path": "logs/application.log",
        "encoding": "utf-8",
        "clear_file_on_init": False,
        "flush_each_write": True,
    }
    terminal: ConsoleConfig = {
        "color_system": "truecolor",
        "theme": create_log_theme({"application.custom": "bold blue"}),
        "log_path": True,
    }
    traceback: TracebackConfig = {"show_locals": False, "locals_overflow": "ellipsis"}
    pretty: PrettyLogConfig = {
        "logger_config": logger_config,
        "file_manager_config": file_manager,
        "terminal_console_config": terminal,
        "traceback_config": traceback,
    }
    call: LogCallConfig = {"style": LogStyle.SUCCESS, "source_link": "file", "traceback_config": {"show_locals": True}}

    assert_type(get_default_log_config(), PrettyLogConfig)
    assert_type(merge_pretty_config(pretty, {"logger_config": call}), PrettyLogConfig)

    del mode


def _allow_all(level: object, messages: tuple[object, ...]) -> bool:
    del level, messages
    return True


def _check_logger_contracts() -> None:
    logger = PrettyLog(
        "typing",
        mode="all",
        level="DEBUG",
        pretty_config={
            "logger_config": {"source_link": "vscode"},
            "file_manager_config": {"path": "logs/typing.log"},
            "traceback_config": {"show_locals": False},
        },
    )
    child = logger.child("child", component="api")
    assert_type(child, PrettyLog)
    assert_type(logger.is_enabled_for("INFO"), bool)
    logger.info(
        "ready",
        mode="all",
        style=StyleSpec(color="green"),
        source_link="file",
        terminal_console_config={"width": 120},
        file_manager_config={"flush_each_write": True},
        traceback_config={"show_locals": False},
    )
    logger.add_filter(_allow_all)
    assert_type(logger.remove_filter(_allow_all), bool)
    with logger.scoped_level("WARNING") as scoped_level:
        assert_type(scoped_level, PrettyLog)
    with logger.scoped_context(request_id="abc") as scoped_context:
        assert_type(scoped_context, PrettyLog)
    with logger.timer("operation") as timed:
        assert_type(timed, PrettyLog)
