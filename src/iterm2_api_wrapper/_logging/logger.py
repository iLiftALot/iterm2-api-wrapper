from __future__ import annotations

import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import RLock
from typing import ClassVar, Generator
from weakref import WeakSet

from rich.console import Console
from rich.pretty import pprint
from rich.traceback import install as install_rich_traceback
from typing_extensions import Unpack

from ._render import LogRenderer
from ._sinks import OutputSinks, _TerminalSink
from .config import (
    DEFAULT_LOG_PATH,
    ConsoleConfig,
    FileManagerConfig,
    LogCallConfig,
    LogConfig,
    LogLevel,
    LogLevelLike,
    LogMode,
    PrettyLogConfig,
    TracebackConfig,
    _resolve_level,
    _severity,
    copy_pretty_config,
    get_default_log_config,
    merge_pretty_config,
)


LOG_PATH = DEFAULT_LOG_PATH
LogFilter = Callable[[LogLevel, tuple[object, ...]], bool]

_standalone_terminal_lock = RLock()
_standalone_terminal: _TerminalSink | None = None


def get_terminal_console() -> Console:
    """Return a lazily constructed terminal Console using fresh defaults."""
    global _standalone_terminal

    with _standalone_terminal_lock:
        if _standalone_terminal is None:
            defaults = get_default_log_config()
            terminal_config = defaults.get("terminal_console_config", {})
            _standalone_terminal = _TerminalSink(terminal_config)

        return _standalone_terminal.console


def pp(
    *objects: object,
    console: Console | None = None,
    indent_guides: bool = True,
    max_length: int | None = None,
    max_string: int | None = None,
    max_depth: int | None = None,
    expand_all: bool = True,
) -> None:
    """Pretty-print one object or a tuple of objects to a lazy terminal Console."""
    value: object = objects[0] if len(objects) == 1 else objects
    pprint(
        value,
        console=console or get_terminal_console(),
        indent_guides=indent_guides,
        max_length=max_length,
        max_string=max_string,
        max_depth=max_depth,
        expand_all=expand_all,
    )


def install_pretty_tracebacks(config: TracebackConfig | None = None) -> None:
    """Explicitly install Rich's process-wide exception hook with safe defaults."""
    defaults = get_default_log_config().get("traceback_config", {})
    resolved = defaults.copy()

    if config is not None:
        resolved.update(config)

    install_rich_traceback(**resolved)


def _validate_mode(mode: str) -> LogMode:
    log_modes = ("terminal", "file", "all")

    if mode not in log_modes:
        raise ValueError(f"Invalid log mode: {mode!r}. Expected 'terminal', 'file', or 'all'.")

    return mode


def _log_overrides(call: LogCallConfig) -> LogConfig:
    """Copy direct per-entry keys from the combined per-call contract."""
    result: LogConfig = {}

    if "sep" in call:
        result["sep"] = call["sep"]
    if "end" in call:
        result["end"] = call["end"]
    if "style" in call:
        result["style"] = call["style"]
    if "justify" in call:
        result["justify"] = call["justify"]
    if "overflow" in call:
        result["overflow"] = call["overflow"]
    if "no_wrap" in call:
        result["no_wrap"] = call["no_wrap"]
    if "emoji" in call:
        result["emoji"] = call["emoji"]
    if "markup" in call:
        result["markup"] = call["markup"]
    if "highlight" in call:
        result["highlight"] = call["highlight"]
    if "width" in call:
        result["width"] = call["width"]
    if "height" in call:
        result["height"] = call["height"]
    if "crop" in call:
        result["crop"] = call["crop"]
    if "soft_wrap" in call:
        result["soft_wrap"] = call["soft_wrap"]
    if "new_line_start" in call:
        result["new_line_start"] = call["new_line_start"]
    if "log_locals" in call:
        result["log_locals"] = call["log_locals"]
    if "source_link" in call:
        result["source_link"] = call["source_link"]

    return result


@dataclass(slots=True)
class _ResolvedCall:
    log_config: LogConfig
    terminal_config: ConsoleConfig
    file_config: ConsoleConfig
    traceback_config: TracebackConfig
    sinks: OutputSinks
    _released: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        if self._released:
            return

        self.sinks.release()
        self._released = True


class PrettyLog:
    """A typed, hierarchical Rich logger with terminal and plain-file sinks."""

    _registry: ClassVar[dict[str, PrettyLog]] = {}
    _registry_lock: ClassVar[RLock] = RLock()
    _instances: ClassVar[WeakSet[PrettyLog]] = WeakSet()

    def __init__(
        self,
        name: str = "root",
        mode: LogMode = "all",
        level: LogLevelLike = LogLevel.INFO,
        *,
        pretty_config: PrettyLogConfig | None = None,
        _shared_sinks: OutputSinks | None = None,
    ) -> None:
        defaults = get_default_log_config()
        defaults.setdefault("file_manager_config", {})["path"] = LOG_PATH

        with self._registry_lock:
            inferred_parent = self._find_existing_ancestor(name)

        base_config = inferred_parent.pretty_config if inferred_parent is not None else defaults
        config = merge_pretty_config(base_config, pretty_config)
        output_override = pretty_config is not None and any(
            key in pretty_config for key in ("terminal_console_config", "file_console_config", "file_manager_config")
        )
        inherited_sinks = (
            _shared_sinks
            if _shared_sinks is not None
            else inferred_parent._sinks
            if inferred_parent is not None and not output_override
            else None
        )

        self.name = name
        self.mode: LogMode = _validate_mode(mode)
        self.level = _resolve_level(level)
        self._lock = RLock()
        self._enabled = True
        self._closed = False
        self._context: dict[str, object] = {}
        self._filters: list[LogFilter] = []
        self._children: dict[str, PrettyLog] = {}
        self._renderer = LogRenderer()
        self._replace_config(config)
        self._sinks = inherited_sinks.acquire() if inherited_sinks is not None else self._create_sinks(config)

        with self._registry_lock:
            self._parent = inferred_parent or self

            if self._parent is not self:
                self._parent._children[name] = self

            self._registry[name] = self
            self._instances.add(self)

    @staticmethod
    def _create_sinks(config: PrettyLogConfig) -> OutputSinks:
        terminal = config.get("terminal_console_config", {})
        file_console = config.get("file_console_config", {})
        file_manager = config.get("file_manager_config", {})

        if "path" not in file_manager:
            file_manager = file_manager.copy()
            file_manager["path"] = LOG_PATH

        return OutputSinks(terminal, file_console, file_manager)

    def _replace_config(self, config: PrettyLogConfig) -> None:
        self._log_config = config.get("logger_config", {}).copy()
        self._terminal_console_config = config.get("terminal_console_config", {}).copy()
        self._file_console_config = config.get("file_console_config", {}).copy()
        self._file_manager_config = config.get("file_manager_config", {}).copy()
        self._traceback_config = config.get("traceback_config", {}).copy()

    @property
    def pretty_config(self) -> PrettyLogConfig:
        """Return a deep, mutation-isolated configuration snapshot."""
        with self._lock:
            return copy_pretty_config(
                {
                    "logger_config": self._log_config,
                    "terminal_console_config": self._terminal_console_config,
                    "file_console_config": self._file_console_config,
                    "file_manager_config": self._file_manager_config,
                    "traceback_config": self._traceback_config,
                }
            )

    @classmethod
    def _find_existing_ancestor(cls, name: str) -> PrettyLog | None:
        parent_name = name.rsplit(".", 1)[0] if "." in name else ""
        while parent_name:
            parent = cls._registry.get(parent_name)
            if parent is not None:
                return parent
            parent_name = parent_name.rsplit(".", 1)[0] if "." in parent_name else ""
        return cls._registry.get("root")

    @classmethod
    def _find_ancestor(cls, name: str) -> PrettyLog:
        """Return the closest registered ancestor, creating root if necessary."""
        with cls._registry_lock:
            ancestor = cls._find_existing_ancestor(name)
            return ancestor if ancestor is not None else PrettyLog(name="root")

    @classmethod
    def get_logger(
        cls,
        name: str | None = None,
        *,
        level: LogLevelLike | None = None,
        mode: LogMode | None = None,
        pretty_config: PrettyLogConfig | None = None,
    ) -> PrettyLog:
        """Return or create a logger using dot-separated hierarchy inheritance."""
        target_name = name or "root"

        with cls._registry_lock:
            existing = cls._registry.get(target_name)

            if existing is not None:
                if level is not None:
                    existing.set_level(level)

                if mode is not None:
                    existing.mode = _validate_mode(mode)

                if pretty_config is not None:
                    existing.configure(**pretty_config)

                return existing

            if target_name == "root":
                return PrettyLog(
                    name="root", level=level or LogLevel.INFO, mode=mode or "all", pretty_config=pretty_config
                )

            parent = cls._find_ancestor(target_name)
            suffix = target_name[len(parent.name) + 1 :] if target_name.startswith(f"{parent.name}.") else target_name

            return parent.child(suffix, level=level, mode=mode, pretty_config=pretty_config)

    @classmethod
    def list_loggers(cls) -> dict[str, PrettyLog]:
        """Return a registry snapshot."""
        with cls._registry_lock:
            return dict(cls._registry)

    @property
    def children(self) -> dict[str, PrettyLog]:
        """Return a snapshot of direct child loggers."""
        with self._lock:
            return dict(self._children)

    @property
    def parent(self) -> PrettyLog:
        """Return the parent logger; a root logger is its own parent."""
        return self._parent

    def __iter__(self) -> Iterator[PrettyLog]:
        with self._lock:
            children = tuple(self._children.values())

        for child in children:
            yield child
            yield from child

    def __repr__(self) -> str:
        return (
            f"PrettyLog(name={self.name!r}, mode={self.mode!r}, "
            f"level={self.level.value!r}, children={len(self._children)})"
        )

    def set_level(self, level: LogLevelLike, *, propagate: bool = False) -> None:
        """Set the minimum severity, optionally for every descendant."""
        resolved = _resolve_level(level)

        with self._lock:
            self.level = resolved
            children = tuple(self._children.values()) if propagate else ()

        for child in children:
            child.set_level(resolved, propagate=True)

    def set_mode(self, mode: LogMode, *, propagate: bool = False):
        """Set the mode, optionally for every descendant."""
        with self._lock:
            self.mode = mode
            children = tuple(self._children.values()) if propagate else ()

        for child in children:
            child.set_mode(mode, propagate=True)

    def is_enabled_for(self, level: LogLevelLike) -> bool:
        """Return whether this logger would admit the supplied severity."""
        resolved = _resolve_level(level)
        with self._lock:
            return not self._closed and self._enabled and _severity(resolved) >= _severity(self.level)

    def configure(
        self,
        *,
        logger_config: LogConfig | None = None,
        terminal_console_config: ConsoleConfig | None = None,
        file_console_config: ConsoleConfig | None = None,
        file_manager_config: FileManagerConfig | None = None,
        traceback_config: TracebackConfig | None = None,
    ) -> None:
        """Apply isolated configuration updates to this logger."""
        overrides: PrettyLogConfig = {}
        if logger_config is not None:
            overrides["logger_config"] = logger_config
        if terminal_console_config is not None:
            overrides["terminal_console_config"] = terminal_console_config
        if file_console_config is not None:
            overrides["file_console_config"] = file_console_config
        if file_manager_config is not None:
            overrides["file_manager_config"] = file_manager_config
        if traceback_config is not None:
            overrides["traceback_config"] = traceback_config

        output_changed = any(
            value is not None for value in (terminal_console_config, file_console_config, file_manager_config)
        )
        with self._lock:
            if self._closed:
                raise RuntimeError("logger is closed")
            merged = merge_pretty_config(self.pretty_config, overrides)
            if output_changed:
                previous = self._sinks
                self._sinks = self._create_sinks(merged)
                previous.release()
            self._replace_config(merged)

    def enable(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("logger is closed")
            self._enabled = True

    def disable(self) -> None:
        with self._lock:
            self._enabled = False

    def add_context(self, **context: object) -> None:
        with self._lock:
            self._context.update(context)

    def remove_context(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._context.pop(key, None)

    def add_filter(self, filter_function: LogFilter) -> None:
        with self._lock:
            self._filters.append(filter_function)

    def remove_filter(self, filter_function: LogFilter) -> bool:
        """Remove one filter and report whether it was registered."""
        with self._lock:
            try:
                self._filters.remove(filter_function)
            except ValueError:
                return False
            return True

    def clear_filters(self) -> None:
        with self._lock:
            self._filters.clear()

    @contextmanager
    def scoped_level(self, level: LogLevelLike) -> Generator[PrettyLog]:
        previous = self.level
        self.set_level(level)
        try:
            yield self
        finally:
            self.set_level(previous)

    @contextmanager
    def scoped_context(self, **context: object) -> Generator[PrettyLog]:
        missing = object()
        with self._lock:
            previous = {key: self._context.get(key, missing) for key in context}
            self._context.update(context)
        try:
            yield self
        finally:
            with self._lock:
                for key, value in previous.items():
                    if value is missing:
                        self._context.pop(key, None)
                    else:
                        self._context[key] = value

    @contextmanager
    def timer(self, label: str, level: LogLevelLike | None = None) -> Generator[PrettyLog]:
        """Log success/failure elapsed time and re-raise failures unchanged."""
        start = time.perf_counter()
        try:
            yield self
        except Exception as exception:
            elapsed = time.perf_counter() - start
            self.error(f"{label} failed after {elapsed:.3f}s: {exception}", stack_offset=1)
            raise
        else:
            elapsed = time.perf_counter() - start
            self(f"{label} completed in {elapsed:.3f}s", level=level or self.level, stack_offset=1)

    def _passes_filters(self, level: LogLevel, messages: tuple[object, ...]) -> bool:
        with self._lock:
            filters = tuple(self._filters)
        return all(filter_function(level, messages) for filter_function in filters)

    def _resolve_call(self, call: LogCallConfig) -> _ResolvedCall:
        owns_sinks = any(
            key in call for key in ("terminal_console_config", "file_console_config", "file_manager_config")
        )
        with self._lock:
            if self._closed:
                raise RuntimeError("logger is closed")
            base = self.pretty_config
            shared_sinks = None if owns_sinks else self._sinks.acquire()
        log_config = base.get("logger_config", {}).copy()
        log_config.update(_log_overrides(call))

        sink_overrides: PrettyLogConfig = {}
        if "terminal_console_config" in call:
            sink_overrides["terminal_console_config"] = call["terminal_console_config"]
        if "file_console_config" in call:
            sink_overrides["file_console_config"] = call["file_console_config"]
        if "file_manager_config" in call:
            sink_overrides["file_manager_config"] = call["file_manager_config"]
        if "traceback_config" in call:
            sink_overrides["traceback_config"] = call["traceback_config"]
        resolved = merge_pretty_config(base, sink_overrides)

        terminal_config = resolved.get("terminal_console_config", {}).copy()
        file_config = resolved.get("file_console_config", {}).copy()
        traceback_config = resolved.get("traceback_config", {}).copy()
        if "log_locals" in call and ("traceback_config" not in call or "show_locals" not in call["traceback_config"]):
            traceback_config["show_locals"] = call["log_locals"]

        sinks = self._create_sinks(resolved) if owns_sinks else shared_sinks
        if sinks is None:  # pragma: no cover - guarded by owns_sinks
            raise RuntimeError("log call failed to acquire output sinks")
        return _ResolvedCall(
            log_config=log_config,
            terminal_config=terminal_config,
            file_config=file_config,
            traceback_config=traceback_config,
            sinks=sinks,
        )

    def _emit_entry(
        self,
        messages: tuple[object, ...],
        *,
        level: LogLevel,
        mode: LogMode | None,
        stack_offset: int,
        call: LogCallConfig,
        exception: BaseException | None = None,
    ) -> bool:
        if not self.is_enabled_for(level) or not self._passes_filters(level, messages):
            return False
        effective_mode = self.mode if mode is None else _validate_mode(mode)
        resolved = self._resolve_call(call)
        try:
            caller = self._renderer.capture_caller(stack_offset + 2)
            locals_map = (
                self._renderer.capture_locals(stack_offset + 2)
                if resolved.log_config.get("log_locals", False)
                else None
            )
            with self._lock:
                context = dict(self._context)
            if messages or exception is None:
                terminal_renderable = self._renderer.render_entry(
                    messages,
                    level=level,
                    logger_name=self.name,
                    context=context,
                    caller=caller,
                    config=resolved.log_config,
                    console_config=resolved.terminal_config,
                    locals_map=locals_map,
                )
                file_renderable = self._renderer.render_entry(
                    messages,
                    level=level,
                    logger_name=self.name,
                    context=context,
                    caller=caller,
                    config=resolved.log_config,
                    console_config=resolved.file_config,
                    locals_map=locals_map,
                )
                resolved.sinks.emit(
                    effective_mode,
                    terminal_renderable,
                    file_renderable,
                    end=resolved.log_config.get("end", "\n"),
                    config=resolved.log_config,
                )
            if exception is not None:
                traceback_renderable = self._renderer.render_exception(exception, resolved.traceback_config)
                resolved.sinks.emit(
                    effective_mode, traceback_renderable, traceback_renderable, config=resolved.log_config
                )
            return True
        finally:
            resolved.close()

    def __call__(
        self,
        *messages: object,
        mode: LogMode | None = None,
        level: LogLevelLike = LogLevel.INFO,
        stack_offset: int = 0,
        **kwargs: Unpack[LogCallConfig],
    ) -> None:
        self._emit_entry(messages, level=_resolve_level(level), mode=mode, stack_offset=stack_offset, call=kwargs)

    def debug(
        self, *messages: object, mode: LogMode | None = None, stack_offset: int = 0, **kwargs: Unpack[LogCallConfig]
    ) -> None:
        self._emit_entry(messages, level=LogLevel.DEBUG, mode=mode, stack_offset=stack_offset, call=kwargs)

    def info(
        self, *messages: object, mode: LogMode | None = None, stack_offset: int = 0, **kwargs: Unpack[LogCallConfig]
    ) -> None:
        self._emit_entry(messages, level=LogLevel.INFO, mode=mode, stack_offset=stack_offset, call=kwargs)

    def warning(
        self, *messages: object, mode: LogMode | None = None, stack_offset: int = 0, **kwargs: Unpack[LogCallConfig]
    ) -> None:
        self._emit_entry(messages, level=LogLevel.WARNING, mode=mode, stack_offset=stack_offset, call=kwargs)

    def error(
        self, *messages: object, mode: LogMode | None = None, stack_offset: int = 0, **kwargs: Unpack[LogCallConfig]
    ) -> None:
        self._emit_entry(messages, level=LogLevel.ERROR, mode=mode, stack_offset=stack_offset, call=kwargs)

    def critical(
        self, *messages: object, mode: LogMode | None = None, stack_offset: int = 0, **kwargs: Unpack[LogCallConfig]
    ) -> None:
        self._emit_entry(messages, level=LogLevel.CRITICAL, mode=mode, stack_offset=stack_offset, call=kwargs)

    def exception(
        self, *messages: object, mode: LogMode | None = None, stack_offset: int = 0, **kwargs: Unpack[LogCallConfig]
    ) -> None:
        current_exception = sys.exc_info()[1]
        self._emit_entry(
            messages,
            level=LogLevel.ERROR,
            mode=mode,
            stack_offset=stack_offset,
            call=kwargs,
            exception=current_exception,
        )

    def child(
        self,
        name: str | None = None,
        *,
        level: LogLevelLike | None = None,
        mode: LogMode | None = None,
        pretty_config: PrettyLogConfig | None = None,
        **context: object,
    ) -> PrettyLog:
        """Create a registered child with isolated policy and inherited output."""
        if name is None:
            suffix = ".".join(str(value) for value in context.values()) if context else f"child_{len(self.children)}"
        else:
            suffix = name

        child_name = f"{self.name}.{suffix}" if self.name and self.name != "root" else suffix

        inherited = self.pretty_config
        child_config = merge_pretty_config(inherited, pretty_config)
        output_override = pretty_config is not None and any(
            key in pretty_config for key in ("terminal_console_config", "file_console_config", "file_manager_config")
        )
        child = PrettyLog(
            child_name,
            mode=mode or self.mode,
            level=level or self.level,
            pretty_config=child_config,
            _shared_sinks=None if output_override else self._sinks,
        )
        with self._lock:
            child._context = {**self._context, **context}
            child._filters = list(self._filters)
            child._enabled = self._enabled
            child._parent = self
            self._children[child_name] = child
        return child

    def flush(self) -> None:
        """Flush initialized output streams without forcing lazy creation."""
        with self._lock:
            self._sinks.flush()

    def close(self) -> None:
        """Release this logger's sink ownership and registry links once."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._sinks.release()
        with self._registry_lock:
            if self._registry.get(self.name) is self:
                self._registry.pop(self.name, None)
            if self._parent is not self:
                self._parent._children.pop(self.name, None)

    @classmethod
    def shutdown_all(cls) -> None:
        """Close every live logger and clear the registry."""
        with cls._registry_lock:
            instances = tuple(cls._instances)
        for logger in instances:
            logger.close()
        with cls._registry_lock:
            cls._registry.clear()
