from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import IO, ClassVar

from rich.console import Console, RenderableType

from .config import ConsoleConfig, FileManagerConfig, LogConfig, LogMode


def _print(console: Console, renderable: RenderableType, *, end: str, config: LogConfig | None) -> None:
    options: LogConfig = {} if config is None else config
    console.print(
        renderable,
        end=end,
        justify=options.get("justify"),
        overflow=options.get("overflow"),
        no_wrap=options.get("no_wrap"),
        emoji=options.get("emoji"),
        markup=options.get("markup"),
        highlight=options.get("highlight"),
        width=options.get("width"),
        height=options.get("height"),
        crop=options.get("crop", True),
        soft_wrap=options.get("soft_wrap"),
        new_line_start=options.get("new_line_start", False),
    )


@dataclass(slots=True)
class _PathState:
    """Process-local synchronization state for one resolved output path."""

    lock: RLock = field(default_factory=RLock)
    cleared: bool = False


class _TerminalSink:
    """A terminal Console that is constructed only on first use."""

    def __init__(self, config: ConsoleConfig) -> None:
        self._config = config.copy()
        self._console: Console | None = None
        self._lock = RLock()
        self._closed = False

    @property
    def console(self) -> Console:
        with self._lock:
            if self._closed:
                raise RuntimeError("terminal sink is closed")
            if self._console is None:
                self._console = Console(**self._config)
            return self._console

    @property
    def initialized(self) -> bool:
        return self._console is not None

    def emit(self, renderable: RenderableType, *, end: str = "\n", config: LogConfig | None = None) -> None:
        with self._lock:
            _print(self.console, renderable, end=end, config=config)

    def flush(self) -> None:
        with self._lock:
            if self._console is not None:
                self._console.file.flush()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self.flush()
            self._console = None
            self._closed = True


class _FileSink:
    """A synchronized, lazy Rich Console backed by one UTF-8 text file."""

    _path_states_lock: ClassVar[RLock] = RLock()
    _path_states: ClassVar[dict[Path, _PathState]] = {}

    def __init__(self, manager_config: FileManagerConfig, console_config: ConsoleConfig) -> None:
        configured_path = manager_config.get("path")
        if configured_path is None:
            raise ValueError("file_manager_config.path is required")
        self.path = Path(configured_path).expanduser().resolve()
        self._manager_config = manager_config.copy()
        self._console_config = console_config.copy()
        self._handle: IO[str] | None = None
        self._console: Console | None = None
        self._lock = RLock()
        self._closed = False
        self._path_state = self._get_path_state(self.path)

    @classmethod
    def _get_path_state(cls, path: Path) -> _PathState:
        with cls._path_states_lock:
            state = cls._path_states.get(path)
            if state is None:
                state = _PathState()
                cls._path_states[path] = state
            return state

    def _open(self) -> None:
        if self._closed:
            raise RuntimeError("file sink is closed")
        if self._console is not None:
            return

        with self._path_state.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            clear_requested = self._manager_config.get("clear_file_on_init", False)
            encoding = self._manager_config.get("encoding", "utf-8")
            if clear_requested and not self._path_state.cleared:
                with self.path.open(mode="w", encoding=encoding):
                    pass
                self._path_state.cleared = True
            handle = self.path.open(mode="a", encoding=encoding)
            console_config = self._console_config.copy()
            console_config["file"] = handle
            self._handle = handle
            self._console = Console(**console_config)

    @property
    def console(self) -> Console:
        with self._lock:
            self._open()
            if self._console is None:  # pragma: no cover - guarded by _open
                raise RuntimeError("file Console failed to initialize")
            return self._console

    @property
    def initialized(self) -> bool:
        return self._console is not None

    def emit(self, renderable: RenderableType, *, end: str = "\n", config: LogConfig | None = None) -> None:
        with self._lock, self._path_state.lock:
            _print(self.console, renderable, end=end, config=config)
            if self._manager_config.get("flush_each_write", True):
                self.flush()

    def flush(self) -> None:
        with self._lock:
            if self._handle is not None:
                self._handle.flush()

    def close(self) -> None:
        with self._lock, self._path_state.lock:
            if self._closed:
                return
            self.flush()
            if self._handle is not None:
                self._handle.close()
            self._handle = None
            self._console = None
            self._closed = True


class OutputSinks:
    """Reference-counted terminal and file output ownership for a logger tree."""

    def __init__(
        self, terminal_config: ConsoleConfig, file_config: ConsoleConfig, file_manager_config: FileManagerConfig
    ) -> None:
        self.terminal = _TerminalSink(terminal_config)
        self.file = _FileSink(file_manager_config, file_config)
        self._references = 1
        self._lock = RLock()
        self._closed = False

    @property
    def reference_count(self) -> int:
        with self._lock:
            return self._references

    def acquire(self) -> OutputSinks:
        with self._lock:
            if self._closed:
                raise RuntimeError("output sinks are closed")
            self._references += 1
            return self

    def release(self) -> None:
        with self._lock:
            if self._references == 0:
                return
            self._references -= 1
            if self._references == 0:
                self._close_unlocked()

    def emit(
        self,
        mode: LogMode,
        terminal_renderable: RenderableType,
        file_renderable: RenderableType,
        *,
        end: str = "\n",
        config: LogConfig | None = None,
    ) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("output sinks are closed")
            if mode in ("terminal", "all"):
                self.terminal.emit(terminal_renderable, end=end, config=config)
            if mode in ("file", "all"):
                self.file.emit(file_renderable, end=end, config=config)

    def flush(self) -> None:
        with self._lock:
            self.terminal.flush()
            self.file.flush()

    def _close_unlocked(self) -> None:
        if self._closed:
            return
        self.terminal.close()
        self.file.close()
        self._closed = True

    def force_close(self) -> None:
        with self._lock:
            self._references = 0
            self._close_unlocked()
