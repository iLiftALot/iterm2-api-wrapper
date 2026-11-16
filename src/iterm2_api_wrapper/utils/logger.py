from __future__ import annotations

import json
import sys
from functools import partialmethod
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Literal

from loguru import _logger as LoguruLoggerModule
from loguru import logger as loguru_logger
from rich.console import Console

from iterm2_api_wrapper.utils.env import Env


if TYPE_CHECKING:
    from loguru import BasicHandlerConfig, FileHandlerConfig, Record
    from loguru import Logger as LoguruLogger

_LogLevelName = Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "FATAL", "CRITICAL"] | str
_LogLevelNumber = Literal[5, 10, 20, 30, 40, 50] | int
LogLevel = _LogLevelName | _LogLevelNumber


def _json_argument(value: object) -> object:
    try:
        return json.dumps(value, indent=2)
    except (TypeError, ValueError):
        return value


class JsonLogger:
    def __init__(self, logger: LoguruLogger) -> None:
        self._logger = logger
        self._core = getattr(logger, "_core", LoguruLoggerModule.Core())
        self.disable = logger.disable
        self.enable = logger.enable
        self.level = logger.level
        self.bind = logger.bind
        self.add = logger.add
        self.remove = logger.remove
        self.opt = logger.opt
        self.catch = logger.catch
        self.complete = logger.complete
        self.configure = logger.configure
        self.contextualize = logger.contextualize
        self.parse = logger.parse
        self.patch = logger.patch
        self.reinstall = logger.reinstall
        self.start = logger.start
        self.stop = logger.stop

    def log(self, level: LogLevel, message: str, /, *args: object, **kwargs: object) -> None:
        # self._logger.bind(**kwargs).opt(depth=1, capture=False).log(
        self.bind(**kwargs).opt(depth=1, capture=False).log(
            level,
            message,
            *(_json_argument(value) for value in args),
            **{key: _json_argument(value) for key, value in kwargs.items()},
        )

    trace = partialmethod(log, "TRACE")
    debug = partialmethod(log, "DEBUG")
    info = partialmethod(log, "INFO")
    success = partialmethod(log, "SUCCESS")
    warning = partialmethod(log, "WARNING")
    error = partialmethod(log, "ERROR")
    fatal = partialmethod(log, "FATAL")
    critical = partialmethod(log, "CRITICAL")

    def exception(self, message: str, /, *args: object, **kwargs: object) -> None:
        # self._logger.bind(**kwargs).opt(depth=1, capture=False).exception(
        self.bind(**kwargs).opt(depth=1, capture=False).exception(
            message,
            *(_json_argument(value) for value in args),
            **{key: _json_argument(value) for key, value in kwargs.items()},
        )


console = Console()
_logger_lock = Lock()
_logger: JsonLogger | None = None


def get_logger() -> JsonLogger:
    with _logger_lock:
        return _spawn_logger()


def _spawn_logger() -> JsonLogger:
    global _logger

    if _logger is not None:
        return _logger

    def get_pkg_name(file_path: str = "pyproject.toml") -> str:
        from tomllib import load

        pkg_name = "app"
        path = Path(file_path).resolve()
        if not path.exists():
            return pkg_name

        data = load(path.open("rb"))

        if "project" in data and "name" in data["project"]:
            return data["project"]["name"]

        return pkg_name

    def build_file_hyperlink(record: Record, label: str) -> str:
        from urllib.parse import quote

        path = quote(str(Path(record["file"].path).resolve()), safe="/")
        lineno = record["line"]
        link = f"vscode://file{path}:{lineno}:1"
        osc_seq = f"\033]8;;{link}\a{label}\033]8;;\a"
        return osc_seq

    def module_name_patcher(record: Record) -> None:
        if record["name"] == "__main__":
            record["name"] = record["module"]

    def log_format(record: Record, *, hyperlinks: bool = False) -> str:
        time_format = "<green>{time:YYYY-MM-DD@HH:mm:ss.SSS}</green>"
        level_format = "<level>{level: <8}</level>"
        message_format = "<fg #56E045>{message}</fg #56E045>"
        location_format = ":".join([
            f"<light-cyan>{{name}}{'.{function}' if record['function'] != '<module>' else ''}</light-cyan>",
            "<dim>{line}</dim>",
        ])

        if hyperlinks is True:
            location_format = build_file_hyperlink(record, location_format)

        return f"{time_format} | {level_format} | {location_format} - {message_format}\n{{exception}}"

    def ensure_log_path(path: str = "logs/app.log") -> Path:
        log_path = (Path(__file__).parents[3] / path).resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return log_path

    console_handler_config: BasicHandlerConfig = {
        "sink": sys.stdout,
        "level": "DEBUG",
        "format": lambda record: "\n" + log_format(record, hyperlinks=sys.stdout.isatty()),
        "enqueue": True,
        "diagnose": Env.isDev(),
    }
    file_handler_config: FileHandlerConfig = {
        "sink": ensure_log_path(f"logs/{get_pkg_name()}.log"),
        "level": "WARNING",
        "rotation": "5 MB",
        "format": log_format,
        "colorize": False,
        "enqueue": True,
    }

    loguru_logger.configure(handlers=[file_handler_config, console_handler_config], patcher=module_name_patcher)
    _logger = JsonLogger(loguru_logger)
    return _logger
