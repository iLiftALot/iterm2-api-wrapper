"""Console script for iterm2_scripts."""

import asyncio
from types import FunctionType

import typer
from rich.console import Console

from iterm2_scripts.main import main as item2_run
from iterm2_scripts.message import (
    alert_handler,
    poly_modal_alert_handler,
    text_input_alert_handler,
)
from iterm2_scripts.webview_server import run_webview_browser


app = typer.Typer(name="iterm2_scripts")
console = Console()


async def test_poly_modal_alert():
    global_state = await item2_run()
    poly_modal_alert = await poly_modal_alert_handler(
        title="Poly Modal Alert",
        subtitle="This is a poly modal alert with multiple options.",
        connection=global_state.connection,
        window_id=global_state.window.window_id,
        button_names=["OK", "Cancel"],
        checkboxes=[("Option 1", 0), ("Option 2", 1), ("Option 3", 0), ("Option 4", 1)],
        comboboxes=(["Choice 1", "Choice 2", "Choice 3"], "Choice 2"),
        text_fields=(
            ["Field 1", "Field 2", "Field 3"],
            ["Default Value 1", "Default Value 2", "Default Value 3"],
        ),
    )

    console.log("Poly Modal Alert Response: \n")
    console.log(poly_modal_alert)


async def test_text_input_alert():
    global_state = await item2_run()

    text_input_alert = await text_input_alert_handler(
        title="Text Input Alert",
        subtitle="Please enter some text:",
        placeholder="Type here...",
        default_value="Default Text",
        connection=global_state.connection,
        window_id=global_state.window.window_id,
    )
    console.log("Text Input Alert Response: \n")
    console.log(text_input_alert)


async def test_alerts():
    """Test simple alerts."""
    global_state = await item2_run()

    simple_alert = await alert_handler(
        title="iTerm2 Scripts",
        subtitle=f"iTerm2 script is running in profile {global_state.profile.name}!",
        windowId=global_state.window.window_id,
        connection=global_state.connection,
    )

    console.log("Simple Alert Response: \n")
    console.log(simple_alert)


async def async_main():
    """Async main function."""

    global_state = await item2_run()
    simple_alert = await alert_handler(
        title="iTerm2 Scripts",
        subtitle=f"iTerm2 script is running in profile {global_state.profile.name}!",
        windowId=global_state.window.window_id,
        connection=global_state.connection,
    )
    text_input_alert = await text_input_alert_handler(
        title="Text Input Alert",
        subtitle="Please enter some text:",
        placeholder="Type here...",
        default_value="Default Text",
        connection=global_state.connection,
        window_id=global_state.window.window_id,
    )
    poly_modal_alert = await poly_modal_alert_handler(
        title="Poly Modal Alert",
        subtitle="This is a poly modal alert with multiple options.",
        connection=global_state.connection,
        window_id=global_state.window.window_id,
        button_names=["OK", "Cancel"],
        checkboxes=[("Option 1", 0), ("Option 2", 1), ("Option 3", 0), ("Option 4", 1)],
        comboboxes=(["Choice 1", "Choice 2", "Choice 3"], "Choice 2"),
        text_fields=(
            ["Field 1", "Field 2", "Field 3"],
            ["Default Value 1", "Default Value 2", "Default Value 3"],
        ),
    )

    console.log(f"Simple Alert Response: {simple_alert}\n")

    console.log(f"Text Input Alert Response: {text_input_alert}\n")

    console.log("Poly Modal Alert Response: \n")
    console.log(poly_modal_alert)


@app.command()
def rerieve_capabilties():
    """Retrieve and print iTerm2 capabilities."""
    import iterm2.capabilities

    async def _inner():
        global_state = await item2_run()

        for capability in dir(iterm2.capabilities):
            if not capability.startswith("supports_"):
                continue
            func = getattr(iterm2.capabilities, capability)
            if not isinstance(func, FunctionType):
                continue
            is_supported = func(global_state.connection)
            console.log(f"{capability}: {is_supported}")

    asyncio.run(_inner())


@app.command()
def webview():
    """Run the webview browser as a daemon.

    This starts a local web server and registers a webview tool in iTerm2's
    toolbelt. The browser uses native WKWebView for full site compatibility.

    - Use the address bar on the landing page to navigate
    - Click the 🏠 status bar component to return home from any page
    """
    console.print("[bold blue]Starting iTerm2 Web Browser...[/bold blue]")
    console.print("• Landing page with address bar and bookmarks")
    console.print("• Native WKWebView - all sites work (Google, GitHub, etc.)")
    console.print("• 🏠 status bar component to return home")
    console.print("\n[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        asyncio.run(run_webview_browser())
    except KeyboardInterrupt:
        console.print("\n[yellow]Webview browser stopped.[/yellow]")


@app.command()
def main(
    func: str = typer.Option(
        help="The function to run: alert, text_input_alert, poly_modal_alert, all",
        autocompletion=lambda: ["alert", "text_input_alert", "poly_modal_alert", "all"],
    ),
):
    """Main function - runs the async code."""

    match func:
        case "alert":
            selected_fn = test_alerts()
        case "text_input_alert":
            selected_fn = test_text_input_alert()
        case "poly_modal_alert":
            selected_fn = test_poly_modal_alert()
        case "all":
            selected_fn = async_main()
        case _:
            console.print(f"[red]Unknown function: {func}[/red]")
            raise typer.Exit(code=1)

    asyncio.run(selected_fn)


if __name__ == "__main__":
    app()
