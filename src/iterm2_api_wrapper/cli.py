"""Console script for iterm2_api_wrapper."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Coroutine
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from shlex import quote
from types import FunctionType
from typing import TYPE_CHECKING, Annotated, Any, Concatenate, Literal, ParamSpec, TypeVar

import typer
from iterm2 import alert, profile

from ._logging import PrettyLog
from .alert import alert_handler, poly_modal_alert_handler, text_input_alert_handler
from .api.it2connection import run_until_complete
from .api.it2variable import AppVarEnum, SessionVarEnum, TabVarEnum, UserVarEnum, WindowVarEnum
from .client import create_iterm_client
from .typings import HexCodeEnum


if TYPE_CHECKING:
    from .api import Variable
    from .state import iTermState
    from .typings import CommandExecutionResult, HexCode, StrEnum


app = typer.Typer(name="iterm2_api_wrapper")
log = PrettyLog.get_logger(__name__)
T = TypeVar("T")
R = TypeVar("R")
P = ParamSpec("P")
CoroutineFn = Callable[Concatenate[T, P], Coroutine[Any, Any, R]]
VariableScopeName = Literal["iterm2", "window", "tab", "session", "user"]
VARIABLE_SCOPE_COMPLETIONS: tuple[tuple[VariableScopeName, str], ...] = (
    ("iterm2", "Global iTerm2 application variables"),
    ("window", "Variables for the active window"),
    ("tab", "Variables for the active tab"),
    ("session", "Variables for the active session"),
    ("user", "User-defined session variables"),
)
VARIABLE_ENUMS_BY_SCOPE: dict[VariableScopeName, type[StrEnum]] = {
    "iterm2": AppVarEnum,
    "window": WindowVarEnum,
    "tab": TabVarEnum,
    "session": SessionVarEnum,
    "user": UserVarEnum,
}
FUNCTION_NAME_COMPLETIONS: tuple[tuple[str, str], ...] = (
    ("send_command", "Run a shell command in the active iTerm2 session"),
    ("send_hex_codes", "Send HexCodeEnum control or escape sequence members"),
    ("inject", "Inject text into the active session via printf"),
    ("get_variable", "Read an iTerm2 variable"),
    ("show_capabilities", "Show iTerm2 Python API capabilities"),
    ("alert", "Show a simple alert"),
    ("text_input_alert", "Show a text input alert"),
    ("poly_modal_alert", "Show a poly modal alert"),
    ("all_alerts", "Run all alert examples"),
)


def _strip_kwarg_prefix(value: str, name: str) -> str:
    prefix = f"{name}="
    return value[len(prefix) :] if value.startswith(prefix) else value


def _unquote_completion_value(value: str) -> str:
    return value.strip("'\"")


def _get_arg_value(args: tuple[str, ...] | list[str], name: str, position: int) -> str | None:
    for arg in args:
        if arg.startswith(f"{name}="):
            return _unquote_completion_value(_strip_kwarg_prefix(arg, name))

    if len(args) > position:
        return _unquote_completion_value(args[position])

    return None


def _coerce_cli_bool(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError(f"Expected a boolean value, got {value!r}")


_SCOPE_VARIABLE_CACHE: dict[VariableScopeName, list[str]] = {}


def _static_variable_values_for_scope(scope: VariableScopeName) -> list[str]:
    enum_type = VARIABLE_ENUMS_BY_SCOPE[scope]
    return sorted({str(member.value) for member in enum_type})


def _variable_values_for_scope(scope: VariableScopeName, *, refresh: bool = False) -> list[str]:
    if not refresh and (cached_values := _SCOPE_VARIABLE_CACHE.get(scope)) is not None:
        return cached_values

    try:
        # Shell completion is a strict stdout protocol. The iTerm client setup can
        # emit Rich debug logs while connecting, which zsh then tries to parse as
        # completion script text and reports as `(eval):1: parse error near ";;"`.
        # Keep dynamic extraction, but make the probe completely silent.
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            with create_iterm_client(timeout=2.0) as client:
                state = client.get_state()
                scope_vars = run_coro(state.get_variable(scope, "*"), client.loop)

        if not isinstance(scope_vars, dict):
            return _static_variable_values_for_scope(scope)

        values = sorted(str(key) for key in scope_vars if str(key))
        _SCOPE_VARIABLE_CACHE[scope] = values
        return values

    except Exception:
        return _static_variable_values_for_scope(scope)


def _complete_get_variable_arg(incomplete: str, ctx: typer.Context) -> list[tuple[str, str]]:
    args = tuple(ctx.params.get("args") or ())
    scope = _get_arg_value(args, "scope", 0)

    # If scope is not known yet, complete scope.
    if scope not in VARIABLE_ENUMS_BY_SCOPE:
        incomplete_scope = _strip_kwarg_prefix(incomplete, "scope")
        prefix = "scope=" if incomplete.startswith("scope=") else ""

        return [
            (f"{prefix}{scope_name}", help_text)
            for scope_name, help_text in VARIABLE_SCOPE_COMPLETIONS
            if scope_name.startswith(incomplete_scope)
        ]

    # Scope is known; complete variable.
    incomplete_variable = _strip_kwarg_prefix(incomplete, "variable")
    prefix = "variable=" if incomplete.startswith("variable=") else ""

    return [
        (f"{prefix}{value}", f"{scope} variable")
        for value in _variable_values_for_scope(scope)
        if value.startswith(incomplete_variable)
    ]


def _complete_hex_code_arg(incomplete: str, ctx: typer.Context) -> list[tuple[str, str]]:
    return [
        (name, f"Hex code {member.value!r}")
        for name, member in HexCodeEnum.__members__.items()
        if name.startswith(incomplete)
    ]


def function_name_completion(incomplete: str) -> list[tuple[str, str]]:
    return [(name, help_text) for name, help_text in FUNCTION_NAME_COMPLETIONS if name.startswith(incomplete)]


def run_coro(coro: Coroutine[Any, Any, T], event_loop: asyncio.AbstractEventLoop) -> T:
    """Run a coroutine in the given event loop and return a Future."""
    return asyncio.run_coroutine_threadsafe(coro, event_loop).result()


def profiles_completion(incomplete: str, ctx: typer.Context) -> list[tuple[str, str]]:
    profiles: list[profile.Profile] = run_until_complete(profile.Profile.async_get)
    return [(p.name, f"Profile: {p.name} ({p.guid})") for p in profiles if p.name.startswith(incomplete)]


def func_to_args_completion(incomplete: str, ctx: typer.Context) -> list[tuple[str, str]]:
    func_name: str = ctx.params.get("func_name", "")
    if func_name == "get_variable":
        return _complete_get_variable_arg(incomplete, ctx)
    if func_name == "send_hex_codes":
        return _complete_hex_code_arg(incomplete, ctx)

    functions: dict[str, CoroutineFn[iTermState, ..., Any]] = {
        "send_command": send_command,
        "send_hex_codes": send_hex_codes,
        "inject": inject,
        "get_variable": get_variable,
        "show_capabilities": show_capabilities,
        "alert": test_alerts,
        "text_input_alert": test_text_input_alert,
        "poly_modal_alert": test_poly_modal_alert,
        "all_alerts": test_all_alerts,
    }

    func_name: str = ctx.params.get("func_name", "")
    func: Callable[..., Any] | None = functions.get(func_name)
    if func is None:
        return []

    sig = inspect.signature(func).parameters
    func_params = [
        (f"{name}='", f"{param} ({param.kind.description})")
        for name, param in sig.items()
        if name not in ("return", "state", "client")
    ]
    return [
        (value, help_text)
        for value, help_text in func_params[len(ctx.params.get("args", ()) or ()) :]
        if value.startswith(incomplete)
    ]


def kwarg_conversion(maybe_kwargs: tuple[str, ...]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Convert a tuple of strings in the form key=value to a dict."""
    kwargs: dict[str, Any] = {}
    args = tuple(item for item in maybe_kwargs if "=" not in item)
    for item in maybe_kwargs:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        kwargs[key] = value

    return args, kwargs


async def test_poly_modal_alert(state: iTermState) -> alert.PolyModalResult:
    poly_modal_alert = await poly_modal_alert_handler(
        title="Poly Modal Alert",
        subtitle="This is a poly modal alert with multiple options.",
        connection=state.connection,
        window_id=state.window.window_id,
        button_names=["OK", "Cancel"],
        checkboxes=[("Option 1", 0), ("Option 2", 1), ("Option 3", 0), ("Option 4", 1)],
        combobox=(["Choice 1", "Choice 2", "Choice 3"], "Choice 2"),
        text_field=(("Field Placeholder", "Default Value")),
    )

    log.info("Poly Modal Alert Response:\n", poly_modal_alert)
    return poly_modal_alert


async def test_text_input_alert(state: iTermState) -> str | None:
    text_input_alert = await text_input_alert_handler(
        title="Text Input Alert",
        subtitle="Please enter some text:",
        placeholder="Type here...",
        default_value="Default Text",
        connection=state.connection,
        window_id=state.window.window_id,
    )

    log.info("Text Input Alert Response: \n")
    log.info(text_input_alert)
    return text_input_alert


async def test_alerts(state: iTermState) -> int:
    """Test simple alerts."""

    simple_alert: int = await alert_handler(
        title="iTerm2 Scripts",
        subtitle=f"iTerm2 script is running in profile {state.profile.name}!",
        window_id=state.window.window_id,
        connection=state.connection,
    )

    log.info("Simple Alert Response: \n")
    log.info(simple_alert)
    return simple_alert


async def test_all_alerts(state: iTermState) -> tuple[int, str | None, alert.PolyModalResult]:
    """Async main function."""

    simple_alert = await test_alerts(state)
    text_input_alert = await test_text_input_alert(state)
    poly_modal_alert = await test_poly_modal_alert(state)

    log.info(f"Simple Alert Response: {simple_alert}\n")
    log.info(f"Text Input Alert Response: {text_input_alert}\n")
    log.info("Poly Modal Alert Response: \n")
    log.info(poly_modal_alert)
    return (simple_alert, text_input_alert, poly_modal_alert)


async def show_capabilities(state: iTermState, capability: str | None = None) -> dict[str, Any]:
    """Retrieve and print iTerm2 capabilities."""
    import iterm2.capabilities

    capabilities: dict[str, Any] = {}
    for capability in dir(iterm2.capabilities):
        if not capability.startswith("supports_"):
            continue
        func = getattr(iterm2.capabilities, capability)
        if not isinstance(func, FunctionType):
            continue
        is_supported = func(state.connection)
        log.info(f"{capability}: {is_supported}")
        capabilities[capability] = is_supported

    return capabilities


async def get_variable(
    state: iTermState, scope: Literal["iterm2", "window", "tab", "session", "user"], variable: Variable
):
    match scope:
        case "iterm2":
            return await state.get_global_var(variable)
        case "window":
            return await state.get_window_var(variable)
        case "tab":
            return await state.get_tab_var(variable)
        case "session":
            return await state.get_session_var(variable)
        case "user":
            return await state.get_user_var(variable)
        case _:
            raise RuntimeError(f"Unknown variable scope: {scope}")


async def inject(state: iTermState, text: str) -> str:
    """Inject text into the active session as a printf command."""

    text_injection = quote(text)
    await state.session.async_inject(text_injection.encode())
    return text_injection


async def send_command(
    state: iTermState, command: str | None = None, path: str | None = None, timeout: float = 5.0
) -> CommandExecutionResult:
    """Send a command to the iTerm2 session."""

    default_command = "echo 'Hello from iTerm2 API Wrapper!'"
    resolved_path = (
        None
        if path is None or str(path).strip().lower() in {"", "none", "null"}
        else str(Path(path).expanduser().resolve())
    )
    output = await state.run_command(
        command or default_command, path=resolved_path, broadcast=False, timeout=float(timeout)
    )
    return output


async def send_hex_codes(
    state: iTermState,
    *sequences: HexCode | str,
    broadcast: bool | str = False,
    timeout: float | str = 2.0,
    wait: bool | str = False,
) -> bool:
    """Send one or more HexCodeEnum names or raw escape sequences."""

    return await state.send_escape_sequence(
        *sequences,
        broadcast=_coerce_cli_bool(broadcast),
        timeout=float(timeout),
        wait=_coerce_cli_bool(wait),
    )


@app.command()
def main(
    func_name: Annotated[
        str,
        typer.Argument(
            ...,
            help=(
                "The function to run: alert, text_input_alert, poly_modal_alert, all_alerts, "
                "show_capabilities, get_variable, send_command, send_hex_codes, inject"
            ),
            autocompletion=function_name_completion,
            metavar="FUNCTION_NAME",
            rich_help_panel="Function Options",
        ),
    ],
    args: Annotated[
        list[str],
        typer.Argument(
            help="Arguments for the function.",
            autocompletion=func_to_args_completion,
            default_factory=list,
            metavar="*FUNCTION_ARGS",
            rich_help_panel="Function Options",
        ),
    ],
    new_tab: Annotated[
        bool,
        typer.Option(
            "--new-tab/--no-new-tab",
            "-t/-T",
            default_factory=lambda: False,
            help="Whether to open a new tab for the session.",
            rich_help_panel="iTerm Setup Options",
            metavar="NEW_TAB?",
        ),
    ],
    profile_name: Annotated[
        str,
        typer.Option(
            "--profile",
            "-p",
            help="The iTerm2 profile to use for the session.",
            autocompletion=profiles_completion,
            envvar="IT2_DEFAULT_PROFILE",
            default_factory=lambda: run_until_complete(profile.Profile.async_get_default).name,
            metavar="PROFILE_NAME",
            rich_help_panel="iTerm Setup Options",
        ),
    ],
    debug: Annotated[
        bool,
        typer.Option(
            "--debug/--no-debug",
            "-d/-D",
            default_factory=lambda: False,
            help="Enable debug logging.",
            envvar="IT2_DEBUG",
            metavar="DEBUG?",
            rich_help_panel="iTerm Setup Options",
        ),
    ],
):
    """Main function - runs the async code."""

    log.info(f":rocket: [green]Running function:[/green] [bold]{func_name}[/bold]")

    selected_fn: CoroutineFn[iTermState, ..., Any]
    fn_args, fn_kwargs = kwarg_conversion(tuple(args or []))
    log.info(f"{fn_args=}\n{fn_kwargs=}")

    match func_name:
        case "send_command":
            selected_fn = send_command
        case "send_hex_codes":
            selected_fn = send_hex_codes
        case "inject":
            selected_fn = inject
        case "get_variable":
            selected_fn = get_variable
        case "show_capabilities":
            selected_fn = show_capabilities
        case "alert":
            selected_fn = test_alerts
        case "text_input_alert":
            selected_fn = test_text_input_alert
        case "poly_modal_alert":
            selected_fn = test_poly_modal_alert
        case "all_alerts":
            selected_fn = test_all_alerts
        case _:
            log.error(f":warning: [red]Unknown function: {func_name}[/red]")
            raise typer.Exit(code=1)

    with create_iterm_client(timeout=None, debug=debug, new_tab=new_tab, dedicated_profile_name=profile_name) as client:
        state = client.get_state()
        event_loop = client.loop
        output = run_coro(selected_fn(state, *fn_args, **fn_kwargs), event_loop)
        output_style = (str(output), output, type(output)) if not isinstance(output, (int, str)) else f"{output=}"
        log.info(output_style)


if __name__ == "__main__":
    app()
