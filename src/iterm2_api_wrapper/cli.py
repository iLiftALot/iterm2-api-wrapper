"""Console script for iterm2_api_wrapper."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from collections.abc import Callable, Coroutine, Iterator
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from shlex import quote
from types import FunctionType
from typing import TYPE_CHECKING, Annotated, Any, Concatenate, Literal, ParamSpec, TypeVar, cast

import typer
from iterm2 import alert, profile

from ._logging import PrettyLog
from .alert import alert_handler, poly_modal_alert_handler, text_input_alert_handler
from .api.it2connection import run_until_complete
from .api.it2variable import AppVarEnum, SessionVarEnum, TabVarEnum, UserVarEnum, WindowVarEnum
from .core.client import create_iterm_client
from .core.typings import HexCodeEnum


if TYPE_CHECKING:
    from .api import Variable
    from .core.client import ITermClient
    from .core.typings import CommandExecutionResult, HexCode, StrEnum
    from .state import iTermState


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
    ("inject", "Inject text into the active session."),
    ("get_variable", "Read an iTerm2 variable"),
    ("show_capabilities", "Show iTerm2 Python API capabilities"),
    ("alert", "Show a simple alert"),
    ("text_input_alert", "Show a text input alert"),
    ("poly_modal_alert", "Show a poly modal alert"),
    ("all_alerts", "Run all alert examples"),
)


def _strip_kwarg_prefix(value: str, name: str) -> str:
    prefix = f"{name}="
    return value.removeprefix(prefix)


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


def _extract_enum_member_docstring(enum_member: StrEnum) -> str:
    # Only accept a docstring explicitly stored on this member. getattr()
    # may return the inherited multiline docstring from str or the enum class.
    docstring = vars(enum_member).get("__doc__")
    if isinstance(docstring, str) and (description := " ".join(docstring.split())):
        return description

    return f"{enum_member.value!s} variable"


_SCOPE_VARIABLE_CACHE_TTL_SECONDS = 30.0
_SCOPE_VARIABLE_CACHE_DIR = Path.home() / "Library" / "Caches" / "iterm2-api-wrapper" / "completion"
_SCOPE_VARIABLE_CACHE: dict[VariableScopeName, tuple[float, list[tuple[str, str]]]] = {}

_COMPLETION_PROFILE_NAME = os.getenv("IT2_DEFAULT_PROFILE", run_until_complete(profile.Profile.async_get_default).name)
_DEBUG = bool(int(os.getenv("IT2_DEBUG", "0")))
_CLI_CLIENT_TIMEOUT: float | None = None


@dataclass(frozen=True, slots=True)
class _CliClientConfig:
    """Configuration used to acquire an iTerm client for a CLI operation."""

    dedicated_profile_name: str = _COMPLETION_PROFILE_NAME
    timeout: float | None = _CLI_CLIENT_TIMEOUT
    debug: bool = _DEBUG
    new_tab: bool = False
    activate: bool = False
    suppress_output: bool = False


def _completion_client_config() -> _CliClientConfig:
    """Return the non-interactive client configuration used by completion."""

    return _CliClientConfig(
        dedicated_profile_name=_COMPLETION_PROFILE_NAME,
        debug=False,
        new_tab=False,
        activate=False,
        suppress_output=True,
    )


def _command_client_config(*, profile_name: str, debug: bool, new_tab: bool) -> _CliClientConfig:
    """Return the client configuration for a normal CLI command."""

    return _CliClientConfig(
        dedicated_profile_name=profile_name, debug=debug, new_tab=new_tab, activate=False, suppress_output=False
    )


@contextmanager
def _cli_client_state(config: _CliClientConfig) -> Iterator[tuple[ITermClient, iTermState]]:
    """Acquire the client and validated state for one CLI operation.

    Output suppression, construction, state acquisition, and cleanup are all
    owned by this boundary. The caller only supplies operation-specific policy.
    """

    with ExitStack() as stack:
        if config.suppress_output:
            stack.enter_context(redirect_stdout(StringIO()))
            stack.enter_context(redirect_stderr(StringIO()))

        client = stack.enter_context(
            create_iterm_client(
                timeout=config.timeout,
                debug=config.debug,
                new_tab=config.new_tab,
                activate=config.activate,
                dedicated_profile_name=config.dedicated_profile_name,
            )
        )
        state = client.get_state()

        yield client, state


def _scope_variable_cache_file(scope: VariableScopeName) -> Path:
    return _SCOPE_VARIABLE_CACHE_DIR / f"{scope}.json"


def _scope_variable_cache_is_fresh(cached_at: float, now: float) -> bool:
    age = now - cached_at
    return 0.0 <= age <= _SCOPE_VARIABLE_CACHE_TTL_SECONDS


def _read_cached_scope_variable_values(scope: VariableScopeName) -> list[tuple[str, str]] | None:
    now = time.time()

    if (memory_entry := _SCOPE_VARIABLE_CACHE.get(scope)) is not None:
        cached_at, values = memory_entry
        if _scope_variable_cache_is_fresh(cached_at, now):
            log.debug(f"Using cached scope variable values for scope '{scope!r}' from memory: {len(values)} values.")
            return values.copy()

        _SCOPE_VARIABLE_CACHE.pop(scope, None)

    try:
        payload: object = json.loads(_scope_variable_cache_file(scope).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        log.error(f"Failed to read cached scope variable values for scope '{scope!r}' due to an error: {exc}")
        return None

    if not isinstance(payload, dict):
        log.warning(f"Cached scope variable values for scope '{scope!r}' are not a valid JSON object.")
        return None

    cache_data = cast(dict[str, object], payload)
    cached_at = cache_data.get("cached_at")
    raw_values = cache_data.get("values")

    if (
        isinstance(cached_at, bool)
        or not isinstance(cached_at, (int, float))
        or not isinstance(raw_values, list)
        or not all(
            isinstance(value, list) and len(value) == 2 and all(isinstance(item, str) for item in value)
            for value in raw_values
        )
    ):
        log.warning(f"Cached scope variable values for scope '{scope!r}' are not in the expected format.")
        return None

    cached_at_float = float(cached_at)
    if not _scope_variable_cache_is_fresh(cached_at_float, now):
        log.debug(f"Cached scope variable values for scope '{scope!r}' are stale: {now - cached_at_float:.2f}s old.")
        return None

    values = cast(list[tuple[str, str]], raw_values).copy()
    _SCOPE_VARIABLE_CACHE[scope] = (cached_at_float, values)

    return values.copy()


def _write_cached_scope_variable_values(scope: VariableScopeName, values: list[tuple[str, str]]) -> None:
    cached_at = time.time()
    cached_values = values.copy()
    _SCOPE_VARIABLE_CACHE[scope] = (cached_at, cached_values)

    cache_file = _scope_variable_cache_file(scope)
    temporary_file = cache_file.with_name(f".{cache_file.name}.{os.getpid()}.tmp")
    payload = {"cached_at": cached_at, "values": cached_values}

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_file.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temporary_file.replace(cache_file)
        log.debug(f"Wrote cached scope variable values for scope '{scope!r}' to disk: {len(values)} values.")
    except OSError as exc:
        # Cache writes must never break shell completion.
        log.error(f"Failed to write cached scope variable values for scope '{scope!r}' to disk due to an error: {exc}")
        # pass
    finally:
        try:
            temporary_file.unlink(missing_ok=True)
        except OSError:
            pass


def _static_variable_values_for_scope(scope: VariableScopeName) -> list[tuple[str, str]]:
    enum_type = VARIABLE_ENUMS_BY_SCOPE[scope]
    return sorted({(str(member.value), _extract_enum_member_docstring(member)) for member in enum_type})


def _variable_values_for_scope(scope: VariableScopeName, *, refresh: bool = False) -> list[tuple[str, str]]:
    if not refresh and (cached_values := _read_cached_scope_variable_values(scope)) is not None:
        return cached_values

    try:
        # Completion stdout is interpreted as shell code, so suppress everything
        # emitted while establishing the temporary iTerm2 connection.
        with _cli_client_state(_completion_client_config()) as (client, state):
            scope_vars = run_coro(state.get_variable(scope, "*"), client.loop)

        if not isinstance(scope_vars, dict):
            log.warning(f"Expected a dict of variables for scope '{scope!r}', but got {type(scope_vars).__name__}.")
            return [(value, doc) for value, doc in _static_variable_values_for_scope(scope)]

        enum_type = VARIABLE_ENUMS_BY_SCOPE[scope]
        values: list[tuple[str, str]] = []

        for key in scope_vars:
            variable_name = str(key)

            try:
                enum_member = enum_type(variable_name)
            except ValueError:
                description = f"{scope!r} variable {variable_name!r}"
            else:
                description = _extract_enum_member_docstring(enum_member)

            values.append((variable_name, description))

        values.sort()

        _write_cached_scope_variable_values(scope, values)
        return values
    except Exception as exc:
        log.error(f"Failed to retrieve variable values for scope '{scope!r}' due to an error: {exc}")
        return [(value, doc) for value, doc in _static_variable_values_for_scope(scope)]


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

    # Zsh evaluates completion stdout as shell code. Nothing involved in
    # constructing candidates may write to stdout or stderr.
    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
        values = _variable_values_for_scope(scope, refresh=False)

    return [(f"{prefix}{value}", doc) for value, doc in values if value.startswith(incomplete_variable)]


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


async def show_capabilities(state: iTermState) -> dict[str, Any]:
    """Retrieve and print iTerm2 capabilities."""
    from iterm2 import capabilities

    supported_functions: dict[str, bool] = {}

    for capability in dir(capabilities):
        if not capability.startswith("supports_"):
            continue

        func = getattr(capabilities, capability)
        if not isinstance(func, FunctionType):
            continue

        is_supported: bool = func(state.connection)
        supported_functions[capability] = is_supported
        log.info(f"{capability}: {is_supported}")

    return supported_functions


async def get_variable(
    state: iTermState, scope: Literal["iterm2", "window", "tab", "session", "user"], variable: Variable
):
    log.debug(f"{scope=} | {variable=}")
    return await state.get_variable(scope, variable)


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
        *sequences, broadcast=_coerce_cli_bool(broadcast), timeout=float(timeout), wait=_coerce_cli_bool(wait)
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
            "--new-tab",
            "-t",
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
            "--debug",
            "-d",
            default_factory=lambda: False,
            help="Enable debug logging.",
            envvar="IT2_DEBUG",
            metavar="DEBUG?",
            rich_help_panel="iTerm Setup Options",
        ),
    ],
):
    log.set_level("DEBUG" if debug is True else "INFO", propagate=True)
    log.set_mode("all")
    log.debug(f":rocket: [green]Running function:[/green] [bold]{func_name}[/bold]", mode="all")

    selected_fn: CoroutineFn[iTermState, ..., Any]
    fn_args, fn_kwargs = kwarg_conversion(tuple(args))

    log.debug(f"{fn_args=}\n{fn_kwargs=}", mode="all")

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
            log.error(f":warning: [red]Unknown function: {func_name}[/red]", mode="all")
            raise typer.Exit(code=1)

    client_config = _command_client_config(profile_name=profile_name, debug=debug, new_tab=new_tab)

    with _cli_client_state(client_config) as (client, state):
        output = run_coro(selected_fn(state, *fn_args, **fn_kwargs), client.loop)
        output_style = (str(output), output, type(output)) if not isinstance(output, (int, str)) else f"{output=}"

        log.debug(output_style)
        print(output)


if __name__ == "__main__":
    app()
