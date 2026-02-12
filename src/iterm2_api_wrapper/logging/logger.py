from __future__ import annotations

import atexit
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from io import TextIOWrapper
from pathlib import Path
from typing import Any, ClassVar, Literal, Unpack, cast, overload

from rich.console import Console, JustifyMethod
from rich.pretty import pprint
from rich.scope import render_scope
from rich.style import Style
from rich.styled import Styled
from rich.text import Text
from rich.traceback import install as install_rich_traceback

# from .styles import StyleAttributes, ColorLike, ThemeStyle
from .config import (
    _LEVEL_STYLES,
    AllLogConfig,
    ConsoleConfig,
    FileManagerConfig,
    LogConfig,
    LogLevel,
    LogLevelLike,
    StyleLike,
    _resolve_level,
    _severity,
)
from .styles import StyleType, LEVEL_PROFILES, GradientHighlighter, LOG_THEME # , LogRegexHighlighter


# Install rich tracebacks globally for better error output
install_rich_traceback(show_locals=True, width=120)


LOG_PATH = Path(__file__).resolve().parents[3] / "logs" / "iterm2_api_wrapper.log"


class _FileConsoleManager:
    """Lazy, atexit-safe manager for the file-backed Rich Console.

    The log file is created and truncated on first write, not on import.
    The underlying file handle is closed automatically at interpreter exit.

    Config updates are merged dynamically without destroying the active
    console or re-truncating the log file. Console instance options are
    applied on (re)build and may trigger a rebuild if changed.
    """

    # Per-path singleton registry so every PrettyLog that targets the same
    # file shares ONE file handle (and one truncation decision).
    _instances: ClassVar[dict[Path, _FileConsoleManager]] = {}

    def __init__(
        self,
        path: Path,
        *,
        file_manager_config: FileManagerConfig | None = None,
        console_config: ConsoleConfig | None = None,
    ) -> None:
        self._path = path
        self._handle: TextIOWrapper | None = None
        self._console: Console | None = None
        self._file_manager_config: FileManagerConfig = file_manager_config or {}
        self._console_config: ConsoleConfig = console_config or {}
        self._initialized: bool = False
        atexit.register(self.close)

    @classmethod
    def get_or_create(
        cls,
        path: Path,
        *,
        file_manager_config: FileManagerConfig | None = None,
        console_config: ConsoleConfig | None = None,
    ) -> _FileConsoleManager:
        """Return the singleton instance for *path*, creating it on first call.

        Subsequent calls with the same resolved path merge config into the
        existing instance without re-truncating the log file.
        """
        resolved = path.resolve()
        if resolved in cls._instances:
            instance = cls._instances[resolved]
            instance.reset_config(
                file_manager_config=file_manager_config, console_config=console_config
            )
            return instance
        instance = cls(
            path, file_manager_config=file_manager_config, console_config=console_config
        )
        cls._instances[resolved] = instance
        return instance

    @property
    def console(self) -> Console:
        """Return the Console, lazily creating the file handle on first access.

        The log file is only truncated on the *true* first initialisation
        (when ``clear_file_on_init`` is ``True``).  Subsequent rebuilds
        triggered by config changes append to the existing file.
        """
        if self._console is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if not self._initialized and self._file_manager_config.get(
                "clear_file_on_init", True
            ):
                self._path.write_text("")
            self._handle = open(self._path, "a")
            base_console_config: ConsoleConfig = {
                "log_time": True,
                "log_time_format": "%Y-%m-%d %H:%M:%S",
            }
            console_config = {**base_console_config, **self._console_config}
            console_config["file"] = self._handle
            self._console = Console(**console_config)
            self._initialized = True
        return self._console

    def reset_config(
        self,
        *,
        file_manager_config: FileManagerConfig | None = None,
        console_config: ConsoleConfig | None = None,
    ) -> None:
        """Merge new config values without destroying the active console.

        Console instance changes trigger a rebuild when the console is
        already active. File manager config changes never re-truncate
        the log file.
        """
        if not file_manager_config and not console_config:
            return
        needs_rebuild = False
        if console_config:
            needs_rebuild = any(
                self._console_config.get(k) != v for k, v in console_config.items()
            )
            self._console_config.update(console_config)
        if file_manager_config:
            self._file_manager_config.update(file_manager_config)
        if needs_rebuild and self._console is not None:
            self._rebuild()

    def _rebuild(self) -> None:
        """Tear down the current Console and file handle.

        The next ``.console`` access will re-create them.  Because
        ``_initialized`` remains ``True``, the file will **not** be
        re-truncated.
        """
        if self._handle is not None:
            self._handle.flush()
            self._handle.close()
            self._handle = None
        self._console = None

    def close(self) -> None:
        """Flush and close the file handle (idempotent)."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None
            self._console = None


class _TerminalConsoleManager:
    """Lazy, atexit-safe manager for the terminal Rich Console.

    Allows dynamic updates to Console instance settings by rebuilding the
    Console when configuration changes.
    """

    _instance: ClassVar[_TerminalConsoleManager | None] = None

    def __init__(self, **config: Unpack[ConsoleConfig]) -> None:
        self._config: ConsoleConfig = config
        self._console: Console | None = None
        atexit.register(self.close)

    @classmethod
    def get_or_create(cls, **config: Unpack[ConsoleConfig]) -> _TerminalConsoleManager:
        if cls._instance is None:
            cls._instance = cls(**config)
        else:
            cls._instance.reset_config(**config)
        return cls._instance

    @property
    def console(self) -> Console:
        if self._console is None:
            self._console = Console(**self._config)
        return self._console

    def reset_config(self, **config: Unpack[ConsoleConfig]) -> None:
        if not config:
            return
        needs_rebuild = any(self._config.get(k) != v for k, v in config.items())
        self._config.update(config)
        if needs_rebuild and self._console is not None:
            self._rebuild()

    def _rebuild(self) -> None:
        self._console = None

    def close(self) -> None:
        self._console = None


_terminal_console_manager = _TerminalConsoleManager.get_or_create()


def get_terminal_console() -> Console:
    """Return the active terminal console (recreated on config updates)."""
    global terminal_console
    terminal_console = _terminal_console_manager.console
    return terminal_console


terminal_console = get_terminal_console()


def pp(*objects: object, **kwargs: Any) -> None:
    """Pretty print to the active terminal console."""
    pprint(*objects, console=get_terminal_console(), expand_all=True, **kwargs)


class PrettyLog:
    """Dual-output Rich logger with log-level filtering, timing, and context.

    Supports writing to the terminal, a log file, or both simultaneously.
    Messages below the configured *level* threshold are silently discarded.
    Thread-safe via an internal lock.

    :param name: Logger name (dot-separated for hierarchy, e.g. ``"app.gateway"``).
    :param mode: Output destination — ``"terminal"``, ``"file"``, or ``"all"``.
    :param level: Minimum severity required for a message to be emitted.
    :param pretty_config: Optional config bundle with keys:
        - ``logger_config``: default ``Console.log`` kwargs
        - ``terminal_console_config``: terminal ``Console`` instance settings
        - ``file_console_config``: file ``Console`` instance settings
        - ``file_manager_config``: file manager settings (e.g., truncation)
    """

    _LEVEL_LABELS: ClassVar[dict[LogLevel, str]] = {
        LogLevel.DEBUG: "DEBUG",
        LogLevel.INFO: "INFO",
        LogLevel.WARNING: "WARN",
        LogLevel.ERROR: "ERROR",
        LogLevel.CRITICAL: "CRITICAL",
    }

    _registry: ClassVar[dict[str, PrettyLog]] = {}

    _CALL_CONFIG_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "logger_config",
            "file_manager_config",
            "terminal_console_config",
            "file_console_config",
        }
    )

    _RENDER_KWARGS_KEYS: ClassVar[frozenset[str]] = frozenset(
        {"sep", "end", "style", "justify", "emoji", "markup", "highlight"}
    )

    @staticmethod
    def _normalize_pretty_config(pretty_config: dict[str, Any] | None) -> AllLogConfig:
        """Normalize legacy config keys and return a clean config dict."""
        if pretty_config is None:
            return {
                "file_manager_config": {"clear_file_on_init": True},
                "logger_config": {"emoji": True, "sep": "\n"},
            }

        normalized: dict[str, Any] = dict(pretty_config)
        legacy_common = normalized.pop("common_kwargs", None)
        legacy_terminal = normalized.pop("terminal_kwargs", None)
        legacy_file = normalized.pop("file_kwargs", None)
        legacy_print = normalized.pop("print_config", None)
        if legacy_common or legacy_terminal or legacy_file:
            legacy_logger = {
                **(legacy_common or {}),
                **(legacy_terminal or {}),
                **(legacy_file or {}),
            }
            if legacy_logger:
                normalized_logger = {**normalized.get("logger_config", {})}
                normalized_logger.update(legacy_logger)
                normalized["logger_config"] = normalized_logger
        if legacy_print:
            normalized_logger = {**normalized.get("logger_config", {})}
            normalized_logger.update(legacy_print)
            normalized["logger_config"] = normalized_logger

        allowed_keys = {
            "logger_config",
            "file_manager_config",
            "terminal_console_config",
            "file_console_config",
        }
        return cast(
            AllLogConfig, {k: v for k, v in normalized.items() if k in allowed_keys}
        )

    def __init__(
        self,
        name: str = "root",
        mode: Literal["terminal", "file", "all"] = "all",
        level: LogLevelLike = LogLevel.DEBUG,
        *,
        pretty_config: AllLogConfig | None = None,
    ) -> None:
        pretty_config = self._normalize_pretty_config(
            pretty_config if pretty_config is None else dict(pretty_config)
        )
        self.name = name
        self.mode = mode
        self.level: LogLevel = _resolve_level(level)
        self._log_config: LogConfig = pretty_config.get("logger_config", {})
        self._terminal_console_config: ConsoleConfig = pretty_config.get(
            "terminal_console_config", {}
        )
        self._file_console_config: ConsoleConfig = pretty_config.get(
            "file_console_config", {}
        )
        self._file_manager_config: FileManagerConfig = pretty_config.get(
            "file_manager_config", FileManagerConfig(clear_file_on_init=True)
        )
        self._terminal_console_manager = _TerminalConsoleManager.get_or_create(
            **self._terminal_console_config
        )
        self._terminal_console_config.setdefault("theme", LOG_THEME)
        self._file_manager = _FileConsoleManager.get_or_create(
            LOG_PATH,
            file_manager_config=self._file_manager_config,
            console_config=self._file_console_config,
        )
        self._lock = threading.Lock()
        self._enabled = True
        self._context: dict[str, str] = {}
        self._filters: list[Callable[[LogLevel, tuple[object, ...]], bool]] = []
        self._children: dict[str, PrettyLog] = {}
        self._parent: PrettyLog | None = None
        PrettyLog._registry[name] = self

    # -- configuration --------------------------------------------------------

    @classmethod
    def get_logger(
        cls,
        name: str | None = None,
        *,
        level: LogLevelLike | None = None,
        mode: Literal["terminal", "file", "all"] | None = None,
        pretty_config: AllLogConfig | None = None,
    ) -> PrettyLog:
        """Retrieve a logger by name, or create one inheriting from the closest ancestor.

        Uses dot-separated hierarchy: ``get_logger("app.gateway")`` will inherit
        from ``"app"`` if it exists, then ``"root"``.

        Optional *level*, *mode*, and *pretty_config* override the inherited
        defaults for the newly created child logger.

        Example::

            gw = PrettyLog.get_logger("app.gateway")
            gw.info("ready")  # inherits root settings + adds "app.gateway" name

            # With per-module overrides:
            dbg = PrettyLog.get_logger("app.debug", level="DEBUG")
        """
        if name is None:
            return (
                cls._registry["root"]
                if "root" in cls._registry
                else PrettyLog(name="root")
            )
        if name in cls._registry:
            logger = cls._registry[name]
            # Apply overrides to an existing logger if provided
            if level is not None:
                logger.set_level(level)
            if mode is not None:
                logger.mode = mode
            if pretty_config is not None:
                normalized = cls._normalize_pretty_config(dict(pretty_config))
                logger.configure(**normalized)
            return logger

        # Walk up the dot hierarchy to find the closest ancestor
        parent = cls._find_ancestor(name)
        # Strip parent prefix so child() doesn't double it
        suffix = (
            name[len(parent.name) + 1 :] if name.startswith(parent.name + ".") else name
        )
        child = parent.child(suffix, level=level, mode=mode, pretty_config=pretty_config)
        return child

    @classmethod
    def _find_ancestor(cls, name: str) -> PrettyLog:
        """Walk up the dot-separated name hierarchy to find the closest registered ancestor."""
        parts = name.rsplit(".", 1)
        while len(parts) > 1:
            parent_name = parts[0]
            if parent_name in cls._registry:
                return cls._registry[parent_name]
            parts = parent_name.rsplit(".", 1)
        return (
            cls._registry["root"] if "root" in cls._registry else PrettyLog(name="root")
        )

    @classmethod
    def list_loggers(cls) -> dict[str, PrettyLog]:
        """Return a snapshot of all registered loggers."""
        return dict(cls._registry)

    @property
    def children(self) -> dict[str, PrettyLog]:
        """Return direct children of this logger."""
        return dict(self._children)

    @property
    def parent(self) -> PrettyLog | None:
        """Return the parent logger, or ``None`` for root."""
        return self._parent

    def __iter__(self) -> Iterator[PrettyLog]:
        """Iterate over all descendants (depth-first)."""
        for child in self._children.values():
            yield child
            yield from child

    def __repr__(self) -> str:
        return (
            f"PrettyLog(name={self.name!r}, mode={self.mode!r}, "
            f"level={self.level.value!r}, children={len(self._children)})"
        )

    def set_level(self, level: LogLevelLike) -> None:
        """Change the minimum log level at runtime."""
        self.level = _resolve_level(level)

    def configure(
        self,
        *,
        logger_config: LogConfig | None = None,
        terminal_console_config: ConsoleConfig | None = None,
        file_console_config: ConsoleConfig | None = None,
        file_manager_config: FileManagerConfig | None = None,
    ) -> None:
        """Apply configuration updates to this logger instance."""
        if logger_config:
            self._log_config.update(logger_config)
        if terminal_console_config:
            self._terminal_console_config.update(terminal_console_config)
            self._terminal_console_manager.reset_config(**self._terminal_console_config)
        if file_console_config:
            self._file_console_config.update(file_console_config)
            self._file_manager.reset_config(console_config=self._file_console_config)
        if file_manager_config:
            self._file_manager_config.update(file_manager_config)
            self._file_manager.reset_config(file_manager_config=self._file_manager_config)

    def enable(self) -> None:
        """Enable log output."""
        self._enabled = True

    def disable(self) -> None:
        """Suppress all log output until :meth:`enable` is called."""
        self._enabled = False

    def add_context(self, **ctx: str) -> None:
        """Add persistent key-value context that prefixes every message.

        Example::

            log.add_context(component="gateway")
            log.info("Connected")  # terminal shows: [gateway] Connected
        """
        self._context.update(ctx)

    def remove_context(self, *keys: str) -> None:
        """Remove previously added context keys."""
        for key in keys:
            self._context.pop(key, None)

    def add_filter(self, fn: Callable[[LogLevel, tuple[object, ...]], bool]) -> None:
        """Register a filter function.

        *fn* receives ``(level, messages)`` and should return ``True`` to
        allow the message, ``False`` to suppress it.
        """
        self._filters.append(fn)

    # -- context manager for temporary overrides ------------------------------

    @contextmanager
    def scoped_level(self, level: LogLevelLike):
        """Temporarily override the log level within a ``with`` block.

        Example::

            with log.scoped_level(LogLevel.DEBUG):
                log.debug("verbose details only inside this block")
        """
        previous = self.level
        self.level = _resolve_level(level)
        try:
            yield self
        finally:
            self.level = previous

    @contextmanager
    def scoped_context(self, **ctx: str):
        """Temporarily add context keys within a ``with`` block.

        Example::

            with log.scoped_context(request_id="abc-123"):
                log.info("processing")
        """
        self.add_context(**ctx)
        try:
            yield self
        finally:
            self.remove_context(*ctx)

    @contextmanager
    def timer(self, label: str, level: LogLevelLike | LogLevel | None = None):
        """Context manager that logs elapsed wall-clock time on exit.

        Example::

            with log.timer("database query"):
                await db.fetch(...)
            # logs: "database query completed in 0.123s"
        """
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        self(
            f"{label} completed in {elapsed:.3f}s",
            level=level or self.level,
            stack_offset=5,
        )

    # -- internal helpers -----------------------------------------------------

    def _build_prefix(self, level: LogLevel) -> Text:
        """Build a Rich ``Text`` prefix with level label, logger name, and context tags."""
        label = self._LEVEL_LABELS.get(level, "???")
        style = _LEVEL_STYLES.get(level, "")
        parts = Text.assemble((f"[{label}]", style or "bold"))
        parts.append(f" [{self.name}]", style="dim magenta")
        if self._context:
            ctx_str = " ".join(f"[{v}]" for v in self._context.values())
            parts.append(f" {ctx_str}", style="dim cyan")
        parts.append(" ")
        return parts

    def _merge_log_config(
        self, call_kwargs: dict[str, Any], level: LogLevel
    ) -> dict[str, Any]:
        """Merge init-common → init-terminal → call-time kwargs for terminal."""
        merged = {**self._log_config, **call_kwargs}
        level_style = _LEVEL_STYLES.get(level, "")
        if level_style and "style" not in merged:
            merged["style"] = level_style
        return merged

    def _merge_file_manager_config(self, call_kwargs: dict[str, Any]) -> None:
        """Merge init-time file config with call-time overrides.

        Short-circuits when *call_kwargs* is empty to avoid unnecessary
        diff checks on every log call.
        """
        if not call_kwargs:
            return
        merged_file_manager = {**self._file_manager_config, **call_kwargs}
        self._file_manager.reset_config(
            file_manager_config=cast(FileManagerConfig, merged_file_manager)
        )

    def _merge_terminal_console_config(self, call_kwargs: dict[str, Any]) -> None:
        """Merge init-time terminal Console config with call-time overrides."""
        if not call_kwargs:
            return
        self._terminal_console_config.update(cast(ConsoleConfig, call_kwargs))
        self._terminal_console_manager.reset_config(**self._terminal_console_config)

    def _merge_file_console_config(self, call_kwargs: dict[str, Any]) -> None:
        """Merge init-time file Console config with call-time overrides."""
        if not call_kwargs:
            return
        self._file_console_config.update(cast(ConsoleConfig, call_kwargs))
        self._file_manager.reset_config(console_config=self._file_console_config)

    def _extract_log_kwargs(self, call_kwargs: dict[str, Any]) -> dict[str, Any]:
        """Extract Console.log kwargs from a mixed call-time dict."""
        if "logger_config" in call_kwargs:
            return dict(call_kwargs.get("logger_config", {}))
        return {k: v for k, v in call_kwargs.items() if k not in self._CALL_CONFIG_KEYS}

    def _select_render_kwargs(self, log_kwargs: dict[str, Any]) -> dict[str, Any]:
        """Return render kwargs from log config."""
        return {k: log_kwargs[k] for k in self._RENDER_KWARGS_KEYS if k in log_kwargs}

    def _build_log_renderable(
        self,
        console: Console,
        renderables: list[Any],
        *,
        stack_offset: int,
        log_locals: bool,
        include_path: bool,
    ) -> Any:
        """Build a Rich log-style renderable with time/path columns."""
        filename, line_no, locals_map = console._caller_frame_info(stack_offset + 1)
        link_path = None if filename.startswith("<") else os.path.abspath(filename)
        path = filename.rpartition(os.sep)[-1] if include_path else None
        if log_locals:
            locals_display = {
                key: value
                for key, value in locals_map.items()
                if not key.startswith("__")
            }
            renderables.append(render_scope(locals_display, title="[i]locals"))
        return console._log_render(
            console,
            renderables,
            log_time=console.get_datetime(),
            path=path,
            line_no=line_no if include_path else None,
            link_path=link_path if include_path else None,
        )

    def _emit(
        self,
        *messages: object,
        mode: Literal["terminal", "file", "all"] | None,
        resolved_level: LogLevel,
        stack_offset: int,
        include_path: bool,
        **kwargs: Any,
    ) -> None:
        """Emit a log-style entry using Console.print with full customization."""
        effective_mode = mode or self.mode

        log_kwargs = self._extract_log_kwargs(kwargs)

        self._merge_terminal_console_config(kwargs.get("terminal_console_config", {}))
        self._merge_file_console_config(kwargs.get("file_console_config", {}))
        self._merge_file_manager_config(kwargs.get("file_manager_config", {}))

        merged_log = self._merge_log_config(log_kwargs, resolved_level)
        log_locals = bool(merged_log.pop("log_locals", False))

        render_kwargs = self._select_render_kwargs(merged_log)
        sep: str = render_kwargs.get("sep", " ")
        end: str = render_kwargs.get("end", "\n")
        justify: JustifyMethod | None = render_kwargs.get("justify")
        emoji: bool | None = render_kwargs.get("emoji")
        markup: bool | None = render_kwargs.get("markup")
        highlight: bool | None = render_kwargs.get("highlight")
        style: StyleLike | None = render_kwargs.get("style")

        level_profile = LEVEL_PROFILES[resolved_level]
        if style is None and level_profile and level_profile.base:
            style = level_profile.base

        print_kwargs = {
            k: v for k, v in merged_log.items() if k not in self._RENDER_KWARGS_KEYS
        }

        prefix = self._build_prefix(resolved_level)
        prefix_width = len(prefix.plain)

        render_messages: list[object] = []
        gradient = None
        if level_profile and level_profile.gradient:
            gradient = GradientHighlighter(level_profile.gradient)
        text: Text = Text("")
        for msg in messages:
            if isinstance(msg, Text):
                text = msg
            elif isinstance(msg, str):
                text = Text.from_markup(msg) if markup is not False else Text(msg)
            else:
                render_messages.append(msg)
            continue
        if level_profile and level_profile.highlighter:
            level_profile.highlighter.highlight(text)
        if gradient:
            gradient.highlight(text)
        render_messages.append(text)

        aligned = tuple(self._indent_continuation(m, prefix_width) for m in render_messages)
        objects = (prefix, *aligned) if aligned else (prefix,)

        def emit_to_console(console: Console) -> None:
            nonlocal style
            renderables = console._collect_renderables(
                objects,
                sep,
                end,
                justify=justify,
                emoji=emoji,
                markup=markup,
                highlight=highlight,
            )
            if style is not None:
                if isinstance(style, StyleType):
                    style = Style(
                        color=style.color,
                        bgcolor=style.bgcolor,
                        link=style.link,
                        **{s: True for s in (style.attributes or []) if s},
                    )
                renderables = [Styled(renderable, style) for renderable in renderables]
            log_renderable = self._build_log_renderable(
                console,
                list(renderables),
                stack_offset=stack_offset,
                log_locals=log_locals,
                include_path=include_path,
            )

            console.print(log_renderable, **print_kwargs)

        with self._lock:
            if effective_mode in ["terminal", "file"]:
                if effective_mode == "terminal":
                    emit_to_console(self._terminal_console_manager.console)
                elif effective_mode == "file":
                    emit_to_console(self._file_manager.console)
            elif effective_mode == "all":
                emit_to_console(self._terminal_console_manager.console)
                emit_to_console(self._file_manager.console)
            else:
                raise ValueError(f"Invalid log mode: {effective_mode}")

    def _passes_filters(self, level: LogLevel, messages: tuple[object, ...]) -> bool:
        """Return True if all registered filters allow this message."""
        return all(fn(level, messages) for fn in self._filters)

    @staticmethod
    def _indent_continuation(message: object, prefix_width: int) -> object:
        """Pad newlines in string messages so continuation lines align with the first."""
        if not isinstance(message, str) or "\n" not in message:
            return message
        pad = " " * prefix_width
        return message.replace("\n", f"\n{pad}")

    # -- overloads for per-mode type safety -----------------------------------

    @overload
    def __call__(
        self,
        *messages: object,
        mode: Literal["terminal", "file"],
        level: LogLevelLike = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[LogConfig],
    ) -> None: ...
    @overload
    def __call__(
        self,
        *messages: object,
        mode: Literal["all"] = "all",
        level: LogLevelLike = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[AllLogConfig],
    ) -> None: ...
    @overload
    def __call__(
        self,
        *messages: object,
        mode: Literal["terminal", "file", "all"] | None = ...,
        level: LogLevelLike = ...,
        stack_offset: int = ...,
        **kwargs: Any,
    ) -> None: ...

    def __call__(
        self,
        *messages: object,
        mode: Literal["terminal", "file", "all"] | None = None,
        level: LogLevelLike = LogLevel.INFO,
        stack_offset: int = 3,
        **kwargs: Any,
    ) -> None:
        resolved_level = _resolve_level(level)
        if not self._enabled or _severity(resolved_level) < _severity(self.level):
            return
        if not self._passes_filters(resolved_level, messages):
            return
        self._emit(
            *messages,
            mode=mode,
            resolved_level=resolved_level,
            stack_offset=stack_offset,
            include_path=True,
            **kwargs,
        )

    # -- convenience shortcuts ------------------------------------------------

    @overload
    def debug(
        self,
        *messages: object,
        mode: Literal["terminal", "file"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[LogConfig],
    ) -> None: ...
    @overload
    def debug(
        self,
        *messages: object,
        mode: Literal["all"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[AllLogConfig],
    ) -> None: ...
    def debug(
        self,
        *messages: object,
        mode: Literal["terminal", "file", "all"] | None = None,
        stack_offset: int = 4,
        **kwargs: Any,
    ) -> None:
        """Log at :attr:`LogLevel.DEBUG`."""
        if isinstance(kwargs.get("logger_config"), dict):
            if "style" not in kwargs["logger_config"]:
                kwargs["logger_config"]["style"] = LEVEL_PROFILES["DEBUG"].base
        else:
            if "style" not in kwargs:
                kwargs["style"] = LEVEL_PROFILES["DEBUG"].base
        self(
            *messages,
            mode=mode,
            level=LogLevel.DEBUG,
            stack_offset=stack_offset,
            **kwargs,
        )

    @overload
    def info(
        self,
        *messages: object,
        mode: Literal["terminal", "file"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[LogConfig],
    ) -> None: ...
    @overload
    def info(
        self,
        *messages: object,
        mode: Literal["all"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[AllLogConfig],
    ) -> None: ...
    def info(
        self,
        *messages: object,
        mode: Literal["terminal", "file", "all"] | None = None,
        stack_offset: int = 4,
        **kwargs: Any,
    ) -> None:
        """Log at :attr:`LogLevel.INFO`."""
        if isinstance(kwargs.get("logger_config"), dict):
            if "style" not in kwargs["logger_config"]:
                kwargs["logger_config"]["style"] = LEVEL_PROFILES["INFO"].base
        else:
            if "style" not in kwargs:
                kwargs["style"] = LEVEL_PROFILES["INFO"].base
        self(
            *messages, mode=mode, level=LogLevel.INFO, stack_offset=stack_offset, **kwargs
        )

    @overload
    def warning(
        self,
        *messages: object,
        mode: Literal["terminal", "file"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[LogConfig],
    ) -> None: ...
    @overload
    def warning(
        self,
        *messages: object,
        mode: Literal["all"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[AllLogConfig],
    ) -> None: ...
    def warning(
        self,
        *messages: object,
        mode: Literal["terminal", "file", "all"] | None = None,
        stack_offset: int = 4,
        **kwargs: Any,
    ) -> None:
        """Log at :attr:`LogLevel.WARNING`."""
        if isinstance(kwargs.get("logger_config"), dict):
            if "style" not in kwargs["logger_config"]:
                kwargs["logger_config"]["style"] = LEVEL_PROFILES["WARNING"].base
        else:
            if "style" not in kwargs:
                kwargs["style"] = LEVEL_PROFILES["WARNING"].base
        self(
            *messages,
            mode=mode,
            level=LogLevel.WARNING,
            stack_offset=stack_offset,
            **kwargs,
        )

    @overload
    def error(
        self,
        *messages: object,
        mode: Literal["terminal", "file"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[LogConfig],
    ) -> None: ...
    @overload
    def error(
        self,
        *messages: object,
        mode: Literal["all"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[AllLogConfig],
    ) -> None: ...
    def error(
        self,
        *messages: object,
        mode: Literal["terminal", "file", "all"] | None = None,
        stack_offset: int = 4,
        **kwargs: Any,
    ) -> None:
        """Log at :attr:`LogLevel.ERROR`."""
        if isinstance(kwargs.get("logger_config"), dict):
            if "log_locals" not in kwargs["logger_config"]:
                kwargs["logger_config"]["log_locals"] = True
            if "style" not in kwargs["logger_config"]:
                kwargs["logger_config"]["style"] = LEVEL_PROFILES["ERROR"].base
        else:
            if not kwargs:
                kwargs["log_locals"] = True
            if "style" not in kwargs:
                kwargs["style"] = LEVEL_PROFILES["ERROR"].base
        self(
            *messages,
            mode=mode,
            level=LogLevel.ERROR,
            stack_offset=stack_offset,
            **kwargs,
        )

    @overload
    def critical(
        self,
        *messages: object,
        mode: Literal["terminal", "file"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[LogConfig],
    ) -> None: ...
    @overload
    def critical(
        self,
        *messages: object,
        mode: Literal["all"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[AllLogConfig],
    ) -> None: ...
    def critical(
        self,
        *messages: object,
        mode: Literal["terminal", "file", "all"] | None = None,
        stack_offset: int = 3,
        **kwargs: Any,
    ) -> None:
        """Log at :attr:`LogLevel.CRITICAL`."""
        if isinstance(kwargs.get("logger_config"), dict):
            if "log_locals" not in kwargs["logger_config"]:
                kwargs["logger_config"]["log_locals"] = True
            if "style" not in kwargs["logger_config"]:
                kwargs["logger_config"]["style"] = LEVEL_PROFILES["CRITICAL"].base
        else:
            if "log_locals" not in kwargs:
                kwargs["log_locals"] = (
                    True  # Ensure locals are logged for error-level messages
                )
            if "style" not in kwargs:
                kwargs["style"] = LEVEL_PROFILES["CRITICAL"].base
        self(
            *messages,
            mode=mode,
            level=LogLevel.CRITICAL,
            stack_offset=stack_offset,
            **kwargs,
        )

    @overload
    def exception(
        self,
        *messages: object,
        mode: Literal["terminal", "file"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[LogConfig],
    ) -> None: ...
    @overload
    def exception(
        self,
        *messages: object,
        mode: Literal["all"] = ...,
        stack_offset: int = ...,
        **kwargs: Unpack[AllLogConfig],
    ) -> None: ...
    def exception(
        self,
        *messages: object,
        mode: Literal["terminal", "file", "all"] | None = None,
        stack_offset: int = 3,
        **kwargs: Any,
    ) -> None:
        """Log at :attr:`LogLevel.ERROR` and print the current exception traceback."""
        if isinstance(kwargs.get("logger_config"), dict):
            if "log_locals" not in kwargs["logger_config"]:
                kwargs["logger_config"]["log_locals"] = True
            if "style" not in kwargs["logger_config"]:
                kwargs["logger_config"]["style"] = LEVEL_PROFILES["ERROR"].base
        else:
            if "log_locals" not in kwargs:
                kwargs["log_locals"] = True  # Ensure locals are logged for error-level messages
            if "style" not in kwargs:
                kwargs["style"] = LEVEL_PROFILES["ERROR"].base

        self(
            *messages,
            mode=mode,
            level=LogLevel.ERROR,
            stack_offset=stack_offset,
            **kwargs,
        )
        self._terminal_console_manager.console.print_exception(show_locals=True)
        self._file_manager.console.print_exception(show_locals=False)

    # -- child logger ---------------------------------------------------------

    def child(
        self,
        name: str | None = None,
        *,
        level: LogLevelLike | None = None,
        mode: Literal["terminal", "file", "all"] | None = None,
        pretty_config: AllLogConfig | None = None,
        stack_offset: int = 3,
        **ctx: str,
    ) -> PrettyLog:
        """Create a child logger that inherits all settings and adds extra context.

        The child is automatically registered in the global logger registry and
        linked to this parent. If *name* is not given, a dot-separated name is
        generated from the context values.

        Optional *level*, *mode*, and *pretty_config* override the inherited
        defaults. Unspecified values are inherited from the parent.

        Example::

            gw_log = log.child("gateway")
            gw_log.info("ready")  # prints: [INFO] [gateway] ready

            # With overrides:
            dbg_log = log.child("debug", level="DEBUG", stack_offset=4)

            # Or with auto-name from context:
            gw_log = log.child(component="gateway")
        """
        if name is None:
            if ctx:
                suffix = ".".join(ctx.values())
            else:
                suffix = f"child_{len(self._children)}"
            child_name = (
                f"{self.name}.{suffix}" if self.name and self.name != "root" else suffix
            )
        else:
            child_name = (
                f"{self.name}.{name}" if self.name and self.name != "root" else name
            )

        # Merge parent config with overrides
        inherited_config: AllLogConfig = {
            "logger_config": self._log_config,
            "terminal_console_config": self._terminal_console_config,
            "file_console_config": self._file_console_config,
            "file_manager_config": self._file_manager_config,
        }
        if pretty_config is not None:
            cfg: dict[str, Any] = dict(inherited_config)  # type: ignore[arg-type]
            normalized = self._normalize_pretty_config(dict(pretty_config))
            for key in (
                "logger_config",
                "terminal_console_config",
                "file_console_config",
                "file_manager_config",
            ):
                if key in normalized:
                    cfg[key] = {**cfg.get(key, {}), **normalized[key]}
            inherited_config = cfg  # type: ignore[assignment]

        child_logger = PrettyLog(
            name=child_name,
            mode=mode or self.mode,
            level=level or self.level,
            pretty_config=inherited_config,
        )
        child_logger._context = {**self._context, **ctx}
        child_logger._filters = list(self._filters)
        child_logger._enabled = self._enabled
        child_logger._parent = self
        self._children[child_name] = child_logger
        return child_logger
