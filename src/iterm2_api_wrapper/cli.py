"""Console script for iterm2_api_wrapper."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from pathlib import Path
from types import FunctionType
from typing import Annotated, Any, Concatenate, Coroutine

import typer
from iterm2 import profile

from iterm2_api_wrapper.alert import alert_handler, poly_modal_alert_handler, text_input_alert_handler
from iterm2_api_wrapper.client import create_iterm_client
from iterm2_api_wrapper._logging import PrettyLog
from iterm2_api_wrapper.state import iTermState
from iterm2_api_wrapper.connection import run_until_complete


app = typer.Typer(name="iterm2_api_wrapper")
log = PrettyLog.get_logger(__name__)
type CoroutineFn[T, R: Any] = Callable[Concatenate[T, ...], Coroutine[Any, Any, R]]


def run_coro[T](coro: Coroutine[Any, Any, T], event_loop: asyncio.AbstractEventLoop) -> T:
    """Run a coroutine in the given event loop and return a Future."""
    return asyncio.run_coroutine_threadsafe(coro, event_loop).result()


def profiles_completion(incomplete: str, ctx: typer.Context) -> list[tuple[str, str]]:
    profiles: list[profile.Profile] = run_until_complete(profile.Profile.async_get)
    return [(p.name, f"Profile: {p.name} ({p.guid})") for p in profiles if p.name.startswith(incomplete)]


def func_to_args_completion(incomplete: str, ctx: typer.Context) -> list[tuple[str, str]]:
    functions: dict[str, CoroutineFn[iTermState, Any]] = {
        "send_command": send_command,
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


async def test_poly_modal_alert(state: iTermState) -> dict[str, Any]:
    poly_modal_alert = await poly_modal_alert_handler(
        title="Poly Modal Alert",
        subtitle="This is a poly modal alert with multiple options.",
        connection=state.connection,
        window_id=state.window.window_id,
        button_names=["OK", "Cancel"],
        checkboxes=[("Option 1", 0), ("Option 2", 1), ("Option 3", 0), ("Option 4", 1)],
        comboboxes=(["Choice 1", "Choice 2", "Choice 3"], "Choice 2"),
        text_fields=(["Field 1", "Field 2", "Field 3"], ["Default Value 1", "Default Value 2", "Default Value 3"]),
    )

    log.info("Poly Modal Alert Response: \n")
    log.info(poly_modal_alert)
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


async def test_all_alerts(state: iTermState) -> tuple[int, str | None, dict[str, Any]]:
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


async def send_command(
    state: iTermState, command: str | None = None, path: str | None = None, timeout: float = 120.0
) -> str:
    """Send a command to the iTerm2 session."""

    default_command = "echo 'Hello from iTerm2 API Wrapper!'"
    output = await state.run_command(
        command or default_command,
        path=str(Path(path).expanduser().resolve()) if path else None,
        broadcast=False,
        timeout=float(timeout),
    )
    return output


@app.command()
def main(
    func_name: Annotated[
        str,
        typer.Argument(
            ...,
            help="The function to run: alert, text_input_alert, poly_modal_alert, all_alerts, show_capabilities, send_command",
            autocompletion=lambda: [
                "send_command",
                "show_capabilities",
                "alert",
                "text_input_alert",
                "poly_modal_alert",
                "all_alerts",
            ],
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
            envvar="ITERM_DEDICATED_PROFILE",
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
            envvar="ITERM_DEBUG",
            metavar="DEBUG?",
            rich_help_panel="iTerm Setup Options",
        ),
    ],
):
    """Main function - runs the async code."""

    log.info(f":rocket: [green]Running function:[/green] [bold]{func_name}[/bold]")

    selected_fn: CoroutineFn[iTermState, Any]
    fn_args, fn_kwargs = kwarg_conversion(tuple(args or []))
    log.info(f"{fn_args=}\n{fn_kwargs=}")
    match func_name:
        case "show_capabilities":
            selected_fn = show_capabilities
        case "send_command":
            selected_fn = send_command
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
        log.info(output)


if __name__ == "__main__":
    app()
