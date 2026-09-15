from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from enum import IntEnum
from os import PathLike
from pathlib import Path
from types import ModuleType
from typing import IO, Literal, TypedDict

from rich.console import HighlighterType, JustifyMethod, OverflowMethod
from rich.emoji import EmojiVariant
from rich.style import StyleType as RichStyleType
from rich.text import Text
from rich.theme import Theme

from ..core.typings import StrEnum
from .styles import StyleLike, create_log_theme


class _LogLevel(IntEnum):
    """Numeric severities compatible with the standard-library logging scale."""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class LogLevel(StrEnum):
    """Supported logging severities."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


LogLevelName = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogLevelLike = LogLevel | LogLevelName
LogMode = Literal["terminal", "file", "all"]
SourceLinkMode = Literal["vscode", "file", "none"]


_LOG_LEVEL_MAP: dict[LogLevel, _LogLevel] = {
    LogLevel.DEBUG: _LogLevel.DEBUG,
    LogLevel.INFO: _LogLevel.INFO,
    LogLevel.WARNING: _LogLevel.WARNING,
    LogLevel.ERROR: _LogLevel.ERROR,
    LogLevel.CRITICAL: _LogLevel.CRITICAL,
}


def _log_level_from_str(level: str) -> LogLevel:
    """Convert a case-insensitive string to a supported level."""
    try:
        return LogLevel(level.upper())
    except ValueError:
        expected = ", ".join(member.value for member in LogLevel)
        raise ValueError(f"Invalid log level: {level!r}. Expected one of: {expected}") from None


def _resolve_level(level: LogLevel | str) -> LogLevel:
    """Return the canonical enum member for a level-like value."""
    return level if isinstance(level, LogLevel) else _log_level_from_str(level)


def _severity(level: LogLevel | str) -> int:
    """Return a level's numeric severity."""
    return _LOG_LEVEL_MAP[_resolve_level(level)]


_LEVEL_STYLES: dict[LogLevel, str] = {
    LogLevel.DEBUG: "logging.level.debug",
    LogLevel.INFO: "logging.level.info",
    LogLevel.WARNING: "logging.level.warning",
    LogLevel.ERROR: "logging.level.error",
    LogLevel.CRITICAL: "logging.level.critical",
}


class ConsoleConfig(TypedDict, total=False):
    """Public Rich ``Console`` constructor options, excluding private arguments."""

    color_system: Literal["auto", "standard", "256", "truecolor", "windows"] | None
    force_terminal: bool | None
    force_jupyter: bool | None
    force_interactive: bool | None
    soft_wrap: bool
    theme: Theme | None
    stderr: bool
    file: IO[str] | None
    quiet: bool
    width: int | None
    height: int | None
    style: RichStyleType | None
    no_color: bool | None
    tab_size: int
    record: bool
    markup: bool
    emoji: bool
    emoji_variant: EmojiVariant | None
    highlight: bool
    log_time: bool
    log_path: bool
    log_time_format: str | Callable[[datetime], Text]
    highlighter: HighlighterType | None
    legacy_windows: bool | None
    safe_box: bool
    get_datetime: Callable[[], datetime] | None
    get_time: Callable[[], float] | None


class FileManagerConfig(TypedDict, total=False):
    """Lazy file-sink lifecycle options."""

    path: str | PathLike[str]
    encoding: str
    clear_file_on_init: bool
    flush_each_write: bool


class TracebackConfig(TypedDict, total=False):
    """Options passed to Rich traceback construction and explicit installation."""

    width: int | None
    code_width: int | None
    extra_lines: int
    theme: str | None
    word_wrap: bool
    show_locals: bool
    locals_max_length: int
    locals_max_string: int
    locals_max_depth: int | None
    locals_hide_dunder: bool
    locals_hide_sunder: bool
    locals_overflow: OverflowMethod | None
    indent_guides: bool
    suppress: Iterable[str | ModuleType]
    max_frames: int


class LogConfig(TypedDict, total=False):
    """Per-entry rendering options, including Rich ``Console.print`` controls."""

    sep: str
    """String to write between print data. Defaults to " "."""
    end: str
    """String to write at end of print data. Defaults to "\\\\n"."""
    style: StyleLike | None
    """A style to apply to output. ``str`` or ``ThemeStyle | StyleType`` or ``Style(*StyleType)`` or ``None``. Defaults to None."""
    justify: JustifyMethod | None
    """One of "left", "right", "center", or "full". Defaults to ``None``."""
    overflow: OverflowMethod | None
    """Overflow method: "ignore", "crop", "fold", or "ellipsis". Defaults to None."""
    no_wrap: bool | None
    """Disable word wrapping. Defaults to None."""
    emoji: bool | None
    """Enable emoji code, or ``None`` to use console default. Defaults to None."""
    markup: bool | None
    """Enable markup, or ``None`` to use console default. Defaults to None."""
    highlight: bool | None
    """Enable automatic highlighting, or ``None`` to use console default. Defaults to None."""
    width: int | None
    """Width of output, or ``None`` to auto-detect. Defaults to ``None``."""
    height: int | None
    """Height of output, or ``None`` to auto-detect. Defaults to ``None``."""
    crop: bool
    """Crop output to width of terminal. Defaults to True."""
    soft_wrap: bool | None
    """Enable soft wrap mode which disables word wrapping and cropping of text or ``None`` for
                Console default. Defaults to ``None``."""
    new_line_start: bool
    """Insert a new line at the start if the output contains more than one line. Defaults to ``False``."""
    log_locals: bool
    """Boolean to enable logging of locals where ``log()`` was called. Defaults to False."""
    source_link: SourceLinkMode


class PrettyLogConfig(TypedDict, total=False):
    """Construction-time configuration for every logger owner."""

    logger_config: LogConfig
    file_manager_config: FileManagerConfig
    terminal_console_config: ConsoleConfig
    file_console_config: ConsoleConfig
    traceback_config: TracebackConfig


class LogCallConfig(LogConfig, total=False):
    """Per-call rendering options plus optional temporary sink overrides."""

    file_manager_config: FileManagerConfig
    terminal_console_config: ConsoleConfig
    file_console_config: ConsoleConfig
    traceback_config: TracebackConfig


DEFAULT_LOG_PATH = Path(__file__).resolve().parents[3] / "logs" / "iterm2_api_wrapper.log"


def get_default_log_config() -> PrettyLogConfig:
    """Return a fresh, mutation-isolated default configuration."""
    return {
        "logger_config": {
            "sep": " ",
            "end": "\n",
            "style": None,
            "justify": "left",
            "overflow": None,
            "no_wrap": None,
            "emoji": True,
            "markup": True,
            "highlight": True,
            "width": None,
            "height": None,
            "crop": False,
            "soft_wrap": None,
            "new_line_start": False,
            "log_locals": False,
            "source_link": "vscode",
        },
        "file_manager_config": {
            "path": DEFAULT_LOG_PATH,
            "encoding": "utf-8",
            "clear_file_on_init": False,
            "flush_each_write": True,
        },
        "terminal_console_config": {
            "color_system": "auto",
            "force_terminal": None,
            "force_jupyter": None,
            "force_interactive": None,
            "soft_wrap": False,
            "theme": create_log_theme(),
            "stderr": False,
            "file": None,
            "quiet": False,
            "width": None,
            "height": None,
            "style": None,
            "no_color": None,
            "tab_size": 4,
            "record": False,
            "markup": True,
            "emoji": True,
            "emoji_variant": "text",
            "highlight": True,
            "log_time": True,
            "log_path": True,
            "log_time_format": "[%Y-%m-%d %H:%M:%S]",
            "legacy_windows": None,
            "safe_box": True,
        },
        "file_console_config": {
            "color_system": None,
            "force_terminal": False,
            "force_jupyter": False,
            "force_interactive": False,
            "soft_wrap": False,
            "theme": create_log_theme(),
            "stderr": False,
            "file": None,
            "quiet": False,
            "width": None,
            "height": None,
            "style": None,
            "no_color": True,
            "tab_size": 4,
            "record": False,
            "markup": False,
            "emoji": True,
            "emoji_variant": "text",
            "highlight": False,
            "log_time": True,
            "log_path": True,
            "log_time_format": "%Y-%m-%d %H:%M:%S",
            "legacy_windows": None,
            "safe_box": True,
        },
        "traceback_config": {
            "width": 120,
            "code_width": 100,
            "extra_lines": 3,
            "theme": None,
            "word_wrap": True,
            "show_locals": False,
            "locals_max_length": 10,
            "locals_max_string": 120,
            "locals_max_depth": 2,
            "locals_hide_dunder": True,
            "locals_hide_sunder": False,
            "locals_overflow": "ellipsis",
            "indent_guides": True,
            "suppress": (),
            "max_frames": 100,
        },
    }


def _copy_console_config(config: ConsoleConfig) -> ConsoleConfig:
    copied = config.copy()
    theme = copied.get("theme")
    if theme is not None:
        copied["theme"] = Theme(theme.styles, inherit=False)
    return copied


def copy_pretty_config(config: PrettyLogConfig) -> PrettyLogConfig:
    """Copy every mutable section, including each Rich theme container."""
    copied: PrettyLogConfig = {}
    if "logger_config" in config:
        copied["logger_config"] = config["logger_config"].copy()
    if "file_manager_config" in config:
        copied["file_manager_config"] = config["file_manager_config"].copy()
    if "terminal_console_config" in config:
        copied["terminal_console_config"] = _copy_console_config(config["terminal_console_config"])
    if "file_console_config" in config:
        copied["file_console_config"] = _copy_console_config(config["file_console_config"])
    if "traceback_config" in config:
        copied["traceback_config"] = config["traceback_config"].copy()
    return copied


def merge_pretty_config(
    base: PrettyLogConfig | None = None, overrides: PrettyLogConfig | None = None
) -> PrettyLogConfig:
    """Deep-merge logger sections without mutating or aliasing either input."""
    merged = get_default_log_config() if base is None else copy_pretty_config(base)
    if overrides is None:
        return merged

    if "logger_config" in overrides:
        merged.setdefault("logger_config", {}).update(overrides["logger_config"])
    if "file_manager_config" in overrides:
        merged.setdefault("file_manager_config", {}).update(overrides["file_manager_config"])
    if "terminal_console_config" in overrides:
        terminal = merged.setdefault("terminal_console_config", {})
        terminal.update(_copy_console_config(overrides["terminal_console_config"]))
    if "file_console_config" in overrides:
        file_console = merged.setdefault("file_console_config", {})
        file_console.update(_copy_console_config(overrides["file_console_config"]))
    if "traceback_config" in overrides:
        merged.setdefault("traceback_config", {}).update(overrides["traceback_config"])
    return merged
