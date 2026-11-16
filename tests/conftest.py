# ruff: file-ignore[unnecessary-dunder-call]
import faulthandler
import io
import platform
import plistlib
import re
import subprocess
import sys
import time
import webbrowser
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Generator, Literal, TypedDict, Unpack, overload

import pytest
from _pytest.faulthandler import fault_handler_stderr_fd_key
from dotenv import load_dotenv
from rich.align import AlignMethod
from rich.color_triplet import ColorTriplet
from rich.console import Console, ConsoleRenderable, JustifyMethod, OverflowMethod, RichCast
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.terminal_theme import TerminalTheme
from rich.text import Text

from iterm2_api_wrapper.utils.env import Env


load_dotenv()
RUN_TIMEOUT = float(Env.get("IT2_INTEGRATION_TIMEOUT", "60"))
log_path_env = Env.get("IT2_INTEGRATION_LOG", "")
log_path = (
    Path(log_path_env).expanduser().resolve()
    if log_path_env
    else Path(__file__).resolve().parents[1] / "logs" / "pytest.log"
)
html_path = log_path.with_suffix(".html")
log_path.parent.mkdir(parents=True, exist_ok=True)

# Clear log files at import time (before session starts)
log_path.write_text("")

# Plain text console for .log file
_file_console = Console(
    record=False,
    log_path=False,
    log_time=False,
    file=log_path.open("a"),
    # width=100,
    force_terminal=False,
    no_color=True,
)

# Recording console for HTML export (captures with colors)
_html_buffer = io.StringIO()
_html_console = Console(
    record=True,
    log_path=False,
    log_time=False,
    file=_html_buffer,  # Write to buffer, not stdout
    # width=100,
    force_terminal=True,
    color_system="truecolor",
)

# Terminal console for colored stderr output (avoids pytest stdout capture)
_terminal_console = Console(
    record=False,
    log_path=False,
    log_time=False,
    stderr=True,
    color_system="truecolor",
    # width=100
)

BrowserChoice = Literal["default", "safari", "chrome", "firefox", "edge", "mozilla"]


class _PrintOptions(TypedDict, total=False):
    sep: str
    end: str
    style: str | Style | None
    justify: JustifyMethod | None
    overflow: OverflowMethod | None
    no_wrap: bool | None
    emoji: bool | None
    markup: bool | None
    highlight: bool | None
    width: int | None
    height: int | None
    crop: bool
    soft_wrap: bool | None
    new_line_start: bool


class MultiConsole:
    """Wrapper that writes to file (plain), HTML (colored), and terminal (colored) consoles."""

    def __init__(
        self,
        file_console: Console,
        html_console: Console,
        terminal_console: Console,
        *,
        browser: BrowserChoice = "default",
    ) -> None:
        self._file = file_console
        self._html = html_console
        self._terminal = terminal_console
        self._browser = browser

    def print(self, *objects: object, terminal: bool = True, **kwargs: Unpack[_PrintOptions]) -> None:
        targets = (self._file, self._html, self._terminal) if terminal else (self._file, self._html)
        for target in targets:
            prepared: list[object] = []
            for obj in objects:
                if isinstance(obj, str):
                    obj = target.render_str(
                        obj, markup=kwargs.get("markup"), emoji=kwargs.get("emoji"), highlight=kwargs.get("highlight")
                    )
                prepared.append(_linkify_text(obj))
            target.print(*prepared, **kwargs)

    def rule(
        self,
        title: str | Text = "",
        *,
        characters: str = "─",
        style: str | Style = "rule.line",
        align: AlignMethod = "center",
    ) -> None:
        linked_title = _linkify_text(title)
        for target in (self._file, self._html, self._terminal):
            target.rule(linked_title, characters=characters, style=style, align=align)

    def save_html(self, path: Path, show: bool = False) -> None:
        terminal_theme = _build_terminal_theme()
        html = self._html.export_html(theme=terminal_theme, clear=False, inline_styles=False)
        theme_css = _build_html_theme_css(terminal_theme)
        if theme_css:
            html = _inject_html_theme(html, theme_css)
        path.write_text(html, encoding="utf-8")
        if not show:
            return
        if self._browser == "default":
            webbrowser.open(path.as_uri(), 0, True)
        else:
            subprocess.Popen(["open", "-a", self._browser, path.as_uri()])


console: MultiConsole = MultiConsole(
    file_console=_file_console, html_console=_html_console, terminal_console=_terminal_console
)


_LINK_CONSOLE = Console()
_TOKEN = re.compile(r"""https?://[^\s<>"']+|"[^"\n]+"|'[^'\n]+'|[^\s<>"']+""")
_PATH_COLOR = "rgb(0,200,200)"


def _path_style(uri: str) -> Style:
    return Style(color=_PATH_COLOR, link=uri)


def _path_text(path: Path, *, label: str | None = None) -> Text:
    expanded = path.expanduser().absolute()
    resolved = expanded.resolve()

    if label is None:
        try:
            relative = expanded.relative_to(Path.cwd())
            label = str(relative) if relative.parts else expanded.name
        except ValueError:
            label = str(Path(expanded.parent.name) / expanded.name)

    text = Text(label)
    text.stylize(_path_style(resolved.as_uri()), 0, len(text))
    return text


def _existing_path(value: str) -> Path | None:
    if not value:
        return None
    try:
        path = Path(value).expanduser().resolve()
        return path if path.exists() else None
    except (OSError, ValueError, RuntimeError):
        return None


@overload
def _linkify_text(obj: Path | Text | str) -> Text: ...
@overload
def _linkify_text(obj: ConsoleRenderable | RichCast) -> ConsoleRenderable | RichCast: ...
@overload
def _linkify_text(obj: object) -> object: ...
def _linkify_text(obj: object) -> object:
    if isinstance(obj, Path):
        return _path_text(obj)
    if isinstance(obj, Text):
        text = obj.copy()
    elif isinstance(obj, str):
        text = Text.from_markup(obj)
    else:
        return obj

    for match in _TOKEN.finditer(text.plain):
        token = match.group()
        value = token.strip("\"'")
        start = match.start() + len(token) - len(token.lstrip("\"'"))
        if value.startswith(("https://", "http://")):
            value = value.rstrip(".,;!?)")
            href = value
        else:
            value = value.partition("::")[0]
            path = _existing_path(value)
            if path is None:
                stripped = value.lstrip("(").rstrip(".,;:!?)")
                start += len(value) - len(value.lstrip("("))
                value = stripped
                path = _existing_path(value)
            if path is None:
                continue
            href = path.as_uri()
        end = start + len(value)
        if not any(text.get_style_at_offset(_LINK_CONSOLE, i).link for i in range(start, end)):
            style = Style(link=href) if value.startswith(("https://", "http://")) else _path_style(href)
            text.stylize(style, start, end)
    return text


def _argument_text(arguments: Sequence[str]) -> Text:
    result = Text()
    for index, argument in enumerate(arguments):
        if index:
            result.append(" ")
        # Keep each argv element intact: paths may contain spaces or brackets.
        path_part = argument.partition("::")[0]
        path = _existing_path(path_part)
        argument_text = Text(argument)
        if path is not None:
            argument_text.stylize(_path_style(path.as_uri()), 0, len(path_part))
        result.append(argument_text)
    return result


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _triplet_to_rgb(color: ColorTriplet) -> tuple[int, int, int]:
    return (int(color.red), int(color.green), int(color.blue))


def _iterm_color_to_rgb(color: dict[str, Any]) -> tuple[int, int, int] | None:
    try:
        red = float(color.get("Red Component", 0.0))
        green = float(color.get("Green Component", 0.0))
        blue = float(color.get("Blue Component", 0.0))
    except (TypeError, ValueError):
        return None

    def _clamp(value: float) -> int:
        return max(0, min(255, round(value * 255)))

    return _clamp(red), _clamp(green), _clamp(blue)


def _iterm_color_to_hex(color: dict[str, Any]) -> str | None:
    rgb = _iterm_color_to_rgb(color)
    if rgb is None:
        return None
    return _rgb_to_hex(rgb)


def _terminal_theme_from_iterm_dict(data: dict[str, Any]) -> TerminalTheme | None:
    def _get_color(name: str) -> tuple[int, int, int] | None:
        value = data.get(name)
        if not isinstance(value, dict):
            return None
        return _iterm_color_to_rgb(value)

    background = _get_color("Background Color")
    foreground = _get_color("Foreground Color")
    if background is None or foreground is None:
        return None

    normal = [_get_color(f"Ansi {index} Color") for index in range(8)]
    if any(color is None for color in normal):
        return None
    normal_colors = [color for color in normal if color is not None]

    bright = [_get_color(f"Ansi {index} Color") for index in range(8, 16)]
    bright_colors: list[tuple[int, int, int]] | None
    if any(color is None for color in bright):
        bright_colors = None
    else:
        bright_colors = [color for color in bright if color is not None]

    return TerminalTheme(background, foreground, normal_colors, bright_colors)


def _terminal_theme_from_itermcolors(path: Path) -> TerminalTheme | None:
    try:
        with path.open("rb") as handle:
            data = plistlib.load(handle)
    except Exception as e:
        console.print(Text.assemble("Failed to load iTerm colors from ", _path_text(path), f": {e}"), style="red")
        return None

    if not isinstance(data, dict):
        console.print(Text.assemble("Invalid iTerm colors format in ", _path_text(path), f": {data}"), style="red")
        return None

    return _terminal_theme_from_iterm_dict(data)


def _load_iterm_profile() -> dict[str, object] | None:
    if not (Env.get("TERM_PROGRAM") == "iTerm.app" or Env.get("IT2_PROFILE") or Env.get("IT2_DEFAULT_PROFILE")):
        return None

    prefs_path = Path("~/Library/Preferences/com.googlecode.iterm2.plist").expanduser()
    if not prefs_path.exists():
        console.print(Text.assemble("iTerm preferences file not found at ", _path_text(prefs_path)), style="red")
        return None

    try:
        with prefs_path.open("rb") as handle:
            data = plistlib.load(handle)
    except Exception as e:
        console.print(
            Text.assemble("Failed to load iTerm preferences from ", _path_text(prefs_path), f": {e}"), style="red"
        )
        return None

    if not isinstance(data, dict):
        return None

    profiles = data.get("New Bookmarks")
    if not isinstance(profiles, list):
        return None

    profile_id = Env.get("PYTEST_HTML_THEME_PROFILE_ID") or Env.get("IT2_PROFILE_GUID")
    profile_name = Env.get("PYTEST_HTML_THEME_PROFILE") or Env.get("IT2_PROFILE")

    if profile_id:
        for profile in profiles:
            if isinstance(profile, dict) and profile.get("Guid") == profile_id:
                return profile

    if profile_name:
        for profile in profiles:
            if isinstance(profile, dict) and profile.get("Name") == profile_name:
                return profile

    default_guid = data.get("Default Bookmark Guid")
    if default_guid:
        for profile in profiles:
            if isinstance(profile, dict) and profile.get("Guid") == default_guid:
                return profile

    for profile in profiles:
        if isinstance(profile, dict):
            return profile

    return None


def _build_terminal_theme() -> TerminalTheme | None:
    theme_path = Env.get("PYTEST_THEME_PATH")
    if theme_path:
        theme_file = Path(theme_path)
        path_label = _path_text(theme_file, label=theme_file.name)
        # path_label.stylize("bold rgb(255,190,90)", 0, len(path_label))
        console.print("[blue]Loading terminal theme from[/blue]:", path_label)
        path = Path(theme_path).expanduser()
        if path.suffix.lower() == ".itermcolors":
            theme = _terminal_theme_from_itermcolors(path)
            if theme:
                return theme

    profile = _load_iterm_profile()
    if profile:
        console.print(f"[blue]Loading terminal theme from iTerm profile {profile.get('Name', 'unknown')}[/blue]")
        return _terminal_theme_from_iterm_dict(profile)

    return None


def _load_html_extra_css() -> str | None:
    css_path = Env.get("PYTEST_HTML_THEME_CSS_PATH")
    if css_path:
        path = Path(css_path).expanduser()
        if path.is_file():
            return path.read_text(encoding="utf-8")

    theme_path = Env.get("PYTEST_THEME_PATH")
    if theme_path:
        theme_file = Path(theme_path)
        path_label = _path_text(theme_file, label=theme_file.name)
        # path_label.stylize("bold rgb(255,190,90)", 0, len(path_label))
        console.print("[blue]Loading HTML extra CSS from[/blue]:", path_label)
        path = Path(theme_path).expanduser()
        if path.suffix.lower() == ".css" and path.is_file():
            return path.read_text(encoding="utf-8")

    theme_inline = Env.get("PYTEST_HTML_THEME_CSS")
    if theme_inline:
        return theme_inline

    return None


def _theme_css_from_palette(bg: str, fg: str, link: str, panel: str, muted: str) -> str:
    return f"""\
:root {{
  --bg: {bg};
  --fg: {fg};
  --link: rgb(60 60 60 / 85%);
  --link-hover: {link};
  --panel: {panel};
  --muted: {muted};
}}
body {{
  background: var(--bg);
  color: var(--fg);
}}
a {{
  text-underline-offset: 2px;
  cursor: auto;
}}
a:has(:hover) {{
  color: var(--link-hover) !important;
  text-decoration: underline !important;
}}
a:not(:hover) {{
  color: var(--link) !important;
  text-decoration: none !important;
}}
pre {{
  background: var(--panel);
  color: var(--fg);
  padding: 12px 14px;
  border-radius: 8px;
}}
code{{
  color: var(--fg);
}}"""


def _build_html_theme_css(theme: TerminalTheme | None) -> str | None:
    extra_css = _load_html_extra_css()
    if theme is None:
        return extra_css

    bg = _rgb_to_hex(_triplet_to_rgb(theme.background_color))
    fg = _rgb_to_hex(_triplet_to_rgb(theme.foreground_color))
    ansi_colors = theme.ansi_colors

    link_rgb = _triplet_to_rgb(ansi_colors[12])
    muted_rgb = _triplet_to_rgb(ansi_colors[8])
    panel_rgb = _triplet_to_rgb(ansi_colors[0])

    base_css = _theme_css_from_palette(bg, fg, _rgb_to_hex(link_rgb), _rgb_to_hex(panel_rgb), _rgb_to_hex(muted_rgb))

    if extra_css:
        return f"{base_css}\n{extra_css}"
    return base_css


def _inject_html_theme(html: str, css: str) -> str:
    style_block = f'\n<style id="pytest-html-theme">\n{css}\n</style>\n'
    if "</head>" in html:
        return html.replace("</head>", f"{style_block}</head>", 1)
    return f"{style_block}{html}"


def _format_duration(seconds: float) -> str:
    """Format durations using milliseconds, seconds, or minutes."""
    if seconds < 1:
        return f"{seconds * 1000:.3f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"

    minutes, remaining = divmod(seconds, 60)
    return f"{int(minutes)}m {remaining:.1f}s"


def log_var(name: str, value: object) -> None:
    """Log a variable with consistent formatting."""
    console.print(f"    [dim]│[/] [cyan]{name}[/] = [yellow]{value!r}[/]")


def log_info(message: str) -> None:
    """Log an info message with consistent formatting."""
    console.print(f"    [dim]│ {message}[/]")


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    # faulthandler_timeout only covers test execution; this also dumps stacks if collection/imports stall.
    stderr_fd = config.stash.get(fault_handler_stderr_fd_key, None)
    target = stderr_fd if stderr_fd is not None else sys.__stderr__
    if target is not None:
        faulthandler.dump_traceback_later(120, exit=True, file=target)


def pytest_collection_finish(session: pytest.Session) -> None:
    faulthandler.cancel_dump_traceback_later()


def pytest_sessionstart(session: pytest.Session) -> None:
    session.name = "iTerm2 API Wrapper Tests"
    object.__setattr__(session, "start_time", time.perf_counter())


def _addoption_if_missing(parser: pytest.Parser, *names: str, **kwargs: Any) -> None:
    try:
        parser.addoption(*names, **kwargs)
    except ValueError as exc:
        if "already added" not in str(exc):
            raise


def pytest_addoption(parser: pytest.Parser) -> None:
    _addoption_if_missing(
        parser,
        "--show",
        help="Show/open HTML log file after test session completes.",
        action="store_true",
        default=False,
        dest="SHOW_HTML_LOG",
    )
    _addoption_if_missing(
        parser,
        "--browser",
        help="Browser to use for opening HTML log file after test session completes.",
        choices=["default", "safari", "chrome", "firefox", "edge", "mozilla"],
        nargs="?",
        default="safari" if sys.platform == "darwin" else "default",
        dest="BROWSER",
        action="store",
    )


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtestloop(session: pytest.Session) -> Generator[None, object, object]:
    config = session.config
    sys.stdout.flush()
    session_name = getattr(session, "name", "iTerm2 API Wrapper Tests")
    start_time = getattr(session, "start_time", time.perf_counter())
    console._browser = f"{config.getoption('BROWSER', 'default')}"

    # Environment info table
    env_table = Table(show_header=False, box=None, padding=(0, 2))
    env_table.add_column("Key", style="dim")
    env_table.add_column("Value")
    env_table.add_row("Python", Text.assemble(sys.version.split()[0], " (", _path_text(Path(sys.executable)), ")"))
    env_table.add_row("Platform", platform.platform())
    env_table.add_row("Root", _linkify_text(config.rootpath))
    env_table.add_row("Log File", _linkify_text(log_path))
    env_table.add_row("HTML Log", _linkify_text(html_path))
    env_table.add_row("Config", _path_text(config.inipath) if config.inipath else Text("None"))
    env_table.add_row("Timeout", f"{RUN_TIMEOUT:.0f} seconds")
    env_table.add_row("Config Args", _argument_text(config.args))
    env_table.add_row("Invocation Args", _argument_text(["pytest", *config.invocation_params.args]))
    env_table.add_row(
        "Plugins",
        " ".join(str(p) for p in config.invocation_params.plugins) if config.invocation_params.plugins else "None",
    )

    console.print()
    console.print(
        Panel(
            env_table,
            title=f"[bold magenta]{session_name}[/]",
            subtitle=f"[dim]{time.strftime('%Y-%m-%d %H:%M:%S')}[/]",
            border_style="magenta",
            padding=(1, 2),
        )
    )

    result = yield

    duration = _format_duration(time.perf_counter() - start_time)

    # Results summary
    passed = session.testscollected - session.testsfailed
    status_style = "green" if session.testsfailed == 0 else "red"

    summary = Text()
    summary.append(f"✓ {passed} passed", style="green")
    if session.testsfailed:
        summary.append(f"  ✗ {session.testsfailed} failed", style="red")
    summary.append(f"  ⏱ {duration}", style="dim")

    console.print()
    console.print(Panel(summary, title="[bold]Session Complete[/]", border_style=status_style, padding=(0, 2)))
    console.print()

    # Save HTML version with colors
    console.save_html(html_path, bool(config.getoption("SHOW_HTML_LOG", False)))
    return result


_LOGGED_MODULE = pytest.StashKey[pytest.Module]()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> Generator[None, object, object]:
    module = item.getparent(pytest.Module)
    if module is None:
        return (yield)

    if item.session.stash.get(_LOGGED_MODULE, None) is not module:
        item.session.stash[_LOGGED_MODULE] = module

        module_path = module.path
        title = _path_text(module_path, label=module_path.stem)
        title.stylize("bold blue")

        console.print()
        console.rule(title, style="blue")
        console.print(module_path, style="dim", justify="center")
        console.print()

    result = yield

    next_module = nextitem.getparent(pytest.Module) if nextitem is not None else None
    if next_module is not module or item.session.shouldfail or item.session.shouldstop:
        console.print()
        console.rule(style="blue")

    return result


@pytest.fixture(autouse=True, scope="function")
def log_test_start_and_end(request: pytest.FixtureRequest) -> Generator:
    assert isinstance(request.node, pytest.Function)
    test_name = request.node.originalname
    start_time = time.perf_counter()
    info_parts: list[str] = []  # Build test info

    # Parametrize info
    if hasattr(request, "param"):
        info_parts.append(f"[cyan]param=[/]{request.param!r}")

    # Markers (only if present)
    markers = [m.name for m in request.node.iter_markers() if m.name != "usefixtures"]
    if markers:
        info_parts.append(f"[yellow]markers=[/]{', '.join(markers)}")

    console.print(terminal=False)
    console.print(f"  [bold]▶[/] [green]{test_name}[/]", terminal=False)

    if info_parts:
        console.print(f"  [dim]({', '.join(info_parts)})[/]", terminal=False)
    else:
        console.print(terminal=False)

    yield

    duration = _format_duration(time.perf_counter() - start_time)

    # Determine outcome
    if hasattr(request.node, "rep_call"):
        outcome: pytest.TestReport = object.__getattribute__(request.node, "rep_call")
        if outcome.passed:
            status = "[green]✓ PASSED[/]"
        elif outcome.failed:
            status = "[red]✗ FAILED[/]"
        else:
            status = "[yellow]⊘ SKIPPED[/]"
    else:
        status = "[green]✓[/]"

    console.print(f"    {status} [dim]({duration})[/]", terminal=False)


@pytest.hookimpl(tryfirst=True, wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Store test outcome on the item for access in fixtures.

    Accessible via `item.rep_call`.

    .. Example::
        .. code:: python
        import pytest

        use_test_item = pytest.mark.usefixtures("test_item")

        @pytest.fixture
        def test_item(request: pytest.FixtureRequest) -> Iterator[None]:
            item: pytest.Item = request.node
            yield
            setup_report: pytest.TestReport = getattr(item, "rep_setup")  # noqa: B009
            call_report: pytest.TestReport = getattr(item, "rep_call")  # noqa: B009
            teardown_report: pytest.TestReport | None = getattr(item, "rep_teardown", None)
            logger.info(
                f'''Test item: {item.name}\\n\r
                Setup Report: {setup_report}\\n\r
                Call Report: {call_report}\\n\r
                Teardown Report: {teardown_report}'''
            )

        @use_test_item
        def test_item_test() -> None:
            assert True
    """

    report: pytest.TestReport = yield
    setattr(item, f"rep_{report.when}", report)
    return report


@pytest.hookimpl(tryfirst=True)
def pytest_report_teststatus(report: pytest.TestReport) -> tuple[str, str, str] | None:
    """Return test status for console output."""

    # Preserve pytest's expected-failure handling
    if hasattr(report, "wasxfail"):
        return None

    duration = _format_duration(report.duration)

    if report.passed:
        if report.when == "call":
            return "passed", ".", f"✓ PASSED ({duration})"
        return None

    if report.skipped:
        return "skipped", "s", f"⊘ SKIPPED ({duration})"

    if report.failed:
        if report.when == "call":
            return "failed", "F", f"✗ FAILED ({duration})"
        return "error", "E", f"✗ ERROR ({duration})"

    return None
