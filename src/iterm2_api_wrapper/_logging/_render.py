from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from rich.console import ConsoleRenderable, Group, RenderableType, RichCast
from rich.pretty import Pretty
from rich.scope import render_scope
from rich.style import StyleType as RichStyleType
from rich.styled import Styled
from rich.table import Table
from rich.text import Text
from rich.traceback import Traceback

from .config import _LEVEL_STYLES, ConsoleConfig, LogConfig, LogLevel, SourceLinkMode, TracebackConfig
from .styles import LEVEL_PROFILES, LogStyle, StyleLike, StyleSpec


@dataclass(frozen=True, slots=True)
class CallerInfo:
    """The source location associated with a log entry."""

    filename: str
    line_number: int | None


def _normalize_style(style: StyleLike | None) -> RichStyleType | None:
    if isinstance(style, StyleSpec):
        return style.to_rich_style()
    if isinstance(style, LogStyle):
        return style.value
    return style


class LogRenderer:
    """Build stable Rich renderables using public APIs only."""

    def capture_caller(self, stack_offset: int = 0) -> CallerInfo:
        """Capture a caller without retaining a frame reference."""
        if stack_offset < 0:
            raise ValueError("stack_offset must be greater than or equal to zero")
        frame = inspect.currentframe()
        try:
            for _ in range(stack_offset + 1):
                if frame is None:
                    break
                frame = frame.f_back
            if frame is None:
                return CallerInfo(filename="<unknown>", line_number=None)
            return CallerInfo(filename=frame.f_code.co_filename, line_number=frame.f_lineno)
        finally:
            del frame

    def capture_locals(self, stack_offset: int = 0) -> dict[str, object]:
        """Snapshot caller locals only when a log call explicitly requests them."""
        if stack_offset < 0:
            raise ValueError("stack_offset must be greater than or equal to zero")
        frame = inspect.currentframe()
        try:
            for _ in range(stack_offset + 1):
                if frame is None:
                    break
                frame = frame.f_back
            if frame is None:
                return {}
            return {key: value for key, value in frame.f_locals.items() if not key.startswith("__")}
        finally:
            del frame

    @staticmethod
    def source_uri(filename: str, line_number: int | None, mode: SourceLinkMode) -> str | None:
        """Return an editor/file URI for a source location."""
        if mode == "none" or filename.startswith("<"):
            return None
        resolved = Path(filename).expanduser().resolve()
        if mode == "file":
            uri = resolved.as_uri()
            return f"{uri}#L{line_number}" if line_number is not None else uri
        encoded = quote(str(resolved), safe="/")
        suffix = f":{line_number}:1" if line_number is not None else ""
        return f"vscode://file{encoded}{suffix}"

    @classmethod
    def source_text(cls, caller: CallerInfo, mode: SourceLinkMode) -> Text:
        """Build a compact source label with an optional clickable link."""
        label = Path(caller.filename).name
        if caller.line_number is not None:
            label = f"{label}:{caller.line_number}"
        uri = cls.source_uri(caller.filename, caller.line_number, mode)
        text = Text(label, style=LogStyle.PATH.value)
        if uri is not None:
            text.stylize(f"link {uri}")
        return text

    @staticmethod
    def _text_message(message: str | Text, config: LogConfig, console_config: ConsoleConfig) -> Text:
        if isinstance(message, Text):
            text = message.copy()
        else:
            markup = config.get("markup", console_config.get("markup", True))
            emoji = config.get("emoji", console_config.get("emoji", True))
            text = Text.from_markup(message, emoji=emoji is not False) if markup is not False else Text(message)

        text.justify = config.get("justify")
        text.overflow = config.get("overflow")
        text.no_wrap = config.get("no_wrap")
        return text

    @classmethod
    def _message_renderable(
        cls, messages: Sequence[object], level: LogLevel, config: LogConfig, console_config: ConsoleConfig
    ) -> RenderableType:
        converted: list[RenderableType] = []
        text_only = True
        for message in messages:
            if isinstance(message, (str, Text)):
                text = cls._text_message(message, config, console_config)
                highlighter = LEVEL_PROFILES[level.value].highlighter
                if (
                    config.get("style") is None
                    and config.get("highlight", console_config.get("highlight", True)) is not False
                ) and highlighter is not None:
                    highlighter.highlight(text)
                converted.append(text)
            elif isinstance(message, (ConsoleRenderable, RichCast)):
                converted.append(message)
                text_only = False
            else:
                converted.append(
                    Pretty(
                        message,
                        justify=config.get("justify"),
                        overflow=config.get("overflow"),
                        no_wrap=config.get("no_wrap", False),
                    )
                )
                text_only = False

        if not converted:
            converted.append(Text())
        if text_only:
            combined = Text()
            separator = config.get("sep", " ")
            for index, renderable in enumerate(converted):
                if index:
                    combined.append(separator)
                if isinstance(renderable, Text):
                    combined.append(renderable)
            message_renderable: RenderableType = combined
        else:
            inline = Table.grid(padding=0, collapse_padding=True, pad_edge=False, expand=False)
            inline_cells: list[RenderableType] = []
            separator = config.get("sep", " ")
            for index, renderable in enumerate(converted):
                if index:
                    inline.add_column()
                    inline_cells.append(Text(separator))
                inline.add_column()
                inline_cells.append(renderable)
            inline.add_row(*inline_cells)
            message_renderable = inline

        style = _normalize_style(config.get("style"))
        return Styled(message_renderable, style) if style is not None else message_renderable

    @staticmethod
    def _time_text(console_config: ConsoleConfig) -> Text:
        get_datetime = console_config.get("get_datetime")
        now = get_datetime() if get_datetime is not None else datetime.now().astimezone()
        formatter = console_config.get("log_time_format", "[%X]")
        if callable(formatter):
            result = formatter(now)
            return result.copy()
        return Text(now.strftime(formatter), style="log.time")

    @staticmethod
    def _logger_text(logger_name: str, context: Mapping[str, object]) -> Text:
        text = Text(logger_name, style=LogStyle.LOGGER.value)
        if context:
            text.append(" ")
            text.append("[", style=LogStyle.CONTEXT.value)
            for index, (key, value) in enumerate(context.items()):
                if index:
                    text.append(" ", style=LogStyle.CONTEXT.value)
                text.append(key, style=LogStyle.CONTEXT_KEY.value)
                text.append("=", style=LogStyle.CONTEXT.value)
                text.append(str(value), style=LogStyle.CONTEXT_VALUE.value)
            text.append("]", style=LogStyle.CONTEXT.value)
        return text

    def render_entry(
        self,
        messages: Sequence[object],
        *,
        level: LogLevel,
        logger_name: str,
        context: Mapping[str, object],
        caller: CallerInfo,
        config: LogConfig,
        console_config: ConsoleConfig,
        locals_map: Mapping[str, object] | None = None,
    ) -> ConsoleRenderable:
        """Render one compact, aligned log entry."""
        table = Table.grid(padding=(0, 1), collapse_padding=True, pad_edge=False, expand=False)
        cells: list[RenderableType] = []
        if console_config.get("log_time", True):
            table.add_column(no_wrap=True)
            cells.append(self._time_text(console_config))

        table.add_column(no_wrap=True)
        cells.append(Text(f"{level.value:<8}", style=_LEVEL_STYLES[level]))

        table.add_column(no_wrap=True)
        cells.append(self._logger_text(logger_name, context))

        table.add_column(ratio=1, overflow=config.get("overflow") or "fold")
        message = self._message_renderable(messages, level, config, console_config)
        if locals_map is not None:
            message = Group(
                message,
                render_scope(
                    locals_map,
                    title="[i]locals",
                    max_length=10,
                    max_string=120,
                    max_depth=2,
                    overflow=config.get("overflow"),
                ),
                fit=False,
            )
        cells.append(message)

        if console_config.get("log_path", True):
            table.add_column(no_wrap=True, justify="right")
            cells.append(self.source_text(caller, config.get("source_link", "vscode")))

        table.add_row(*cells)
        return table

    @staticmethod
    def render_exception(exception: BaseException, config: TracebackConfig) -> Traceback:
        """Build an explicit Rich traceback for the supplied exception."""
        return Traceback.from_exception(type(exception), exception, exception.__traceback__, **config)
