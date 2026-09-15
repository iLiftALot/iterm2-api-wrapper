from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path

from rich.console import Console
from rich.text import Text

from iterm2_api_wrapper._logging._render import CallerInfo, LogRenderer
from iterm2_api_wrapper._logging._sinks import OutputSinks, _FileSink, _TerminalSink
from iterm2_api_wrapper._logging.config import ConsoleConfig, FileManagerConfig, LogConfig, LogLevel
from iterm2_api_wrapper._logging.styles import create_log_theme


def _terminal_config(file: StringIO) -> ConsoleConfig:
    return {
        "file": file,
        "force_terminal": True,
        "color_system": "truecolor",
        "theme": create_log_theme(),
        "width": 200,
        "record": True,
        "log_time": False,
        "log_path": False,
    }


def _file_config() -> ConsoleConfig:
    return {
        "force_terminal": False,
        "color_system": None,
        "no_color": True,
        "markup": False,
        "highlight": False,
        "width": 200,
        "log_time": False,
        "log_path": False,
    }


def _file_manager(path: Path, *, clear: bool = True) -> FileManagerConfig:
    return {"path": path, "encoding": "utf-8", "clear_file_on_init": clear, "flush_each_write": True}


def test_sinks_are_lazy_and_lifecycle_operations_are_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "application.log"
    terminal_buffer = StringIO()
    terminal = _TerminalSink(_terminal_config(terminal_buffer))
    file_sink = _FileSink(_file_manager(path), _file_config())

    assert terminal.initialized is False
    assert file_sink.initialized is False
    assert not path.exists()

    terminal.emit(Text("terminal"))
    file_sink.emit(Text("file"))
    terminal.flush()
    file_sink.flush()
    terminal.close()
    terminal.close()
    file_sink.close()
    file_sink.close()

    assert "terminal" in terminal_buffer.getvalue()
    assert path.read_text(encoding="utf-8") == "file\n"


def test_file_clear_request_applies_only_once_per_process_path(tmp_path: Path) -> None:
    path = tmp_path / "clear-once.log"
    path.write_text("stale\n", encoding="utf-8")

    first = _FileSink(_file_manager(path), _file_config())
    second = _FileSink(_file_manager(path), _file_config())
    first.emit(Text("first"))
    second.emit(Text("second"))
    first.close()
    second.close()

    assert path.read_text(encoding="utf-8") == "first\nsecond\n"


def test_output_sinks_share_ownership_by_reference(tmp_path: Path) -> None:
    output = OutputSinks(_terminal_config(StringIO()), _file_config(), _file_manager(tmp_path / "owned.log"))

    assert output.reference_count == 1
    assert output.acquire() is output
    assert output.reference_count == 2
    output.release()
    assert output.reference_count == 1
    output.release()
    assert output.reference_count == 0
    output.release()


def test_independent_file_sinks_serialize_complete_plain_entries(tmp_path: Path) -> None:
    path = tmp_path / "concurrent.log"
    first = _FileSink(_file_manager(path), _file_config())
    second = _FileSink(_file_manager(path), _file_config())
    expected = {f"entry-{index:03d}" for index in range(100)}

    def emit(index: int) -> None:
        sink = first if index % 2 == 0 else second
        sink.emit(Text(f"entry-{index:03d}", style="bold red"))

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(emit, range(100)))
    first.close()
    second.close()

    content = path.read_text(encoding="utf-8")
    assert set(content.splitlines()) == expected
    assert len(content.splitlines()) == len(expected)
    assert "\x1b" not in content


def test_renderer_builds_semantic_terminal_and_plain_file_entries(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text("raise RuntimeError\n", encoding="utf-8")
    renderer = LogRenderer()
    caller = CallerInfo(str(source), 17)
    log_config: LogConfig = {"markup": False, "highlight": True, "source_link": "vscode", "sep": " | "}
    terminal_config = _terminal_config(StringIO())
    terminal_config["log_path"] = True
    file_config = _file_config()
    file_config["log_path"] = True
    terminal_renderable = renderer.render_entry(
        ["success in 25ms", {"attempt": 2}],
        level=LogLevel.INFO,
        logger_name="application.worker",
        context={"request_id": "abc"},
        caller=caller,
        config=log_config,
        console_config=terminal_config,
    )
    file_renderable = renderer.render_entry(
        ["success in 25ms", {"attempt": 2}],
        level=LogLevel.INFO,
        logger_name="application.worker",
        context={"request_id": "abc"},
        caller=caller,
        config=log_config,
        console_config=file_config,
    )
    terminal_buffer = StringIO()
    terminal_console = Console(**_terminal_config(terminal_buffer))
    file_buffer = StringIO()
    plain_config = _file_config()
    plain_config["file"] = file_buffer
    plain_console = Console(**plain_config)

    terminal_console.print(terminal_renderable)
    plain_console.print(file_renderable)

    terminal_output = terminal_buffer.getvalue()
    terminal_text = terminal_console.export_text()
    plain_output = file_buffer.getvalue()
    assert "application.worker" in terminal_text
    assert "request_id=abc" in terminal_text
    assert "service.py:17" in terminal_text
    assert "\x1b[" in terminal_output
    assert "success in 25ms" in plain_output
    assert "{'attempt': 2}" in plain_output
    assert "success in 25ms | {'attempt': 2}" in plain_output
    assert "\x1b" not in plain_output


def test_renderer_copies_text_and_respects_time_path_and_explicit_style(tmp_path: Path) -> None:
    message = Text("success 42")
    original_spans = list(message.spans)
    renderer = LogRenderer()
    renderable = renderer.render_entry(
        [message],
        level=LogLevel.WARNING,
        logger_name="application",
        context={},
        caller=CallerInfo(str(tmp_path / "source.py"), 9),
        config={"style": "bold red", "highlight": True},
        console_config={"log_time": False, "log_path": False},
    )
    buffer = StringIO()
    console = Console(
        file=buffer, force_terminal=True, color_system="standard", theme=create_log_theme(), no_color=False, width=120
    )

    console.print(renderable)

    assert message.spans == original_spans
    assert "source.py" not in buffer.getvalue()
    assert re.search(r"\x1b\[[0-9;]*31m", buffer.getvalue()) is not None


def test_source_links_support_vscode_file_and_disabled_modes(tmp_path: Path) -> None:
    source = tmp_path / "a file.py"
    caller = CallerInfo(str(source), 12)

    vscode = LogRenderer.source_uri(caller.filename, caller.line_number, "vscode")
    file_uri = LogRenderer.source_uri(caller.filename, caller.line_number, "file")

    assert vscode is not None and vscode.startswith("vscode://file")
    assert "%20" in vscode and vscode.endswith(":12:1")
    assert file_uri is not None and file_uri.startswith("file://") and file_uri.endswith("#L12")
    assert LogRenderer.source_uri(caller.filename, caller.line_number, "none") is None


def _captured_exception() -> RuntimeError:
    local_secret = "-".join(("sensitive", "local", "value"))
    try:
        raise RuntimeError("traceback test")
    except RuntimeError as exception:
        assert local_secret
        return exception


def test_traceback_locals_are_explicitly_opt_in() -> None:
    exception = _captured_exception()
    hidden_buffer = StringIO()
    visible_buffer = StringIO()
    plain = {"force_terminal": False, "color_system": None, "no_color": True, "width": 160}

    Console(file=hidden_buffer, **plain).print(
        LogRenderer.render_exception(exception, {"show_locals": False, "width": 160})
    )
    Console(file=visible_buffer, **plain).print(
        LogRenderer.render_exception(exception, {"show_locals": True, "width": 160})
    )

    assert "sensitive-local-value" not in hidden_buffer.getvalue()
    assert "sensitive-local-value" in visible_buffer.getvalue()
