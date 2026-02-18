from enum import IntEnum, StrEnum
from typing import Any, Callable, Literal, TypedDict

from rich.console import JustifyMethod, OverflowMethod

from .styles import StyleLike, LOG_THEME


class _LogLevel(IntEnum):
    """Log severity levels, compatible with stdlib ``logging`` value scale."""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class LogLevel(StrEnum):
    """Log severity levels as strings for user-friendly configuration and display."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


_LOG_LEVEL_MAP: dict[LogLevel, _LogLevel] = {
    LogLevel.DEBUG: _LogLevel.DEBUG,
    LogLevel.INFO: _LogLevel.INFO,
    LogLevel.WARNING: _LogLevel.WARNING,
    LogLevel.ERROR: _LogLevel.ERROR,
    LogLevel.CRITICAL: _LogLevel.CRITICAL,
}


def _severity(level: LogLevel | str) -> int:
    """Return the numeric severity for a ``LogLevel`` or raw string."""
    resolved = level if isinstance(level, LogLevel) else _log_level_from_str(level)
    return _LOG_LEVEL_MAP[resolved]


def _log_level_from_str(level_str: str) -> LogLevel:
    """Convert a string to a LogLevel, case-insensitively."""
    try:
        return LogLevel(level_str.upper())
    except ValueError:
        raise ValueError(
            f"Invalid log level: {level_str!r}. "
            f"Expected one of: {', '.join(m.value for m in LogLevel)}"
        ) from None


def _resolve_level(level: LogLevel | str) -> LogLevel:
    """Coerce a string or LogLevel member to a canonical ``LogLevel``."""
    return level if isinstance(level, LogLevel) else _log_level_from_str(level)


type LogLevelLike = LogLevel | Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


_LEVEL_STYLES: dict[LogLevel, str] = {
    LogLevel.DEBUG: "dim",
    LogLevel.INFO: "",
    LogLevel.WARNING: "yellow",
    LogLevel.ERROR: "red bold",
    LogLevel.CRITICAL: "red bold reverse",
}


class ConsoleConfig(TypedDict, total=False):
    """Configuration options for ``rich.console.Console`` initialization."""

    color_system: Literal["auto", "standard", "256", "truecolor", "windows"] | None
    force_terminal: bool | None
    force_jupyter: bool | None
    force_interactive: bool | None
    soft_wrap: bool
    theme: Any
    stderr: bool
    file: Any
    quiet: bool
    width: int | None
    height: int | None
    style: StyleLike | None
    no_color: bool | None
    tab_size: int
    record: bool
    markup: bool
    emoji: bool
    emoji_variant: str | None
    highlight: bool
    log_time: bool
    log_path: bool
    log_time_format: Any
    highlighter: Any
    legacy_windows: bool | None
    safe_box: bool
    get_datetime: Callable[[], Any]
    get_time: Callable[[], float]


class FileManagerConfig(TypedDict, total=False):
    clear_file_on_init: bool


class LogConfig(TypedDict, total=False):
    sep: str
    """String to write between print data. Defaults to " "."""
    end: str
    """String to write at end of print data. Defaults to "\\\\n"."""
    style: StyleLike | None
    """A style to apply to output.
    ``str`` or ``ThemeStyle | StyleType`` or ``Style(*StyleType)`` or ``None``. Defaults to None."""
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
    log_locals: bool
    """Boolean to enable logging of locals where ``log()`` was called. Defaults to False."""
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


class AllLogConfig(TypedDict, total=False):
    """Bundle of per-log, console, and file manager configuration."""

    logger_config: LogConfig
    """Per-call rendering settings (style, markup, highlighting, etc.)."""
    file_manager_config: FileManagerConfig
    """File lifecycle behavior (e.g., clear/truncate on init)."""
    terminal_console_config: ConsoleConfig
    """Rich Console settings for terminal output."""
    file_console_config: ConsoleConfig
    """Rich Console settings for file output."""


def get_default_log_config() -> AllLogConfig:
    """Return the default log configuration."""
    return AllLogConfig(
        logger_config=LogConfig(
            sep=" ",
            end="\n",
            style=None,
            justify="left",
            overflow=None,
            no_wrap=None,
            emoji=True,
            markup=None,
            highlight=None,
            log_locals=False,
            width=None,
            height=None,
            crop=False,
            soft_wrap=None,
            new_line_start=True,
        ),
        file_manager_config=FileManagerConfig(clear_file_on_init=True),
        terminal_console_config=ConsoleConfig(
            color_system="auto",
            force_terminal=True,
            force_jupyter=False,
            force_interactive=False,
            soft_wrap=False,
            theme=LOG_THEME,
            stderr=False,
            file=None,
            quiet=False,
            width=None,
            height=None,
            style=None,
            no_color=None,
            tab_size=4,
            record=False,
            markup=True,
            emoji=True,
            emoji_variant="text",
            highlight=True,
            log_time=True,
            log_path=True,
        ),
        file_console_config=ConsoleConfig(
            color_system="auto",
            force_terminal=False,
            force_jupyter=False,
            force_interactive=False,
            soft_wrap=False,
            theme=None,
            stderr=False,
            file=None,  # Set to actual file in PrettyLog initialization
            quiet=False,
            width=None,
            height=None,
            style=None,
            no_color=None,  # Disable color in file output by default
            tab_size=4,
            record=False,  # Disable rich's internal recording since we're managing it ourselves
            markup=False,  # Disable markup in file output by default
            emoji=True,  # Keep emojis in file output by default
            emoji_variant="text",
            highlight=False,  # Disable automatic highlighting in file output by default
            log_time=True,
            log_time_format="%Y-%m-%d %H:%M:%S",
        ),
    )
