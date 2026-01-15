"""Main module."""

from asyncio import run
from dataclasses import dataclass

import iterm2
# import iterm2.api_pb2

# import iterm2.lifecycle
import iterm2.profile

# import iterm2.tool
from iterm2_scripts.webview_server import start_webview_server


@dataclass
class GlobaliTermState:
    """Global iTerm2 state."""

    connection: iterm2.Connection
    app: iterm2.App
    window: iterm2.Window
    tab: iterm2.Tab
    session: iterm2.Session
    profile: iterm2.Profile

    def __post_init__(self):
        # TODO: validate all fields are not None
        pass


async def register_toolbelt_tools(connection: iterm2.Connection) -> None:
    """Register toolbelt tools with a navigable web browser."""
    # Start the webview server with navigation support
    await start_webview_server(connection)

    # Register the tool pointing to our local server
    # await iterm2.tool.async_register_web_view_tool(
    #     connection=connection,
    #     display_name="Web Browser",
    #     identifier="iterm2.tool.webview",
    #     reveal_if_already_registered=True,
    #     url="https://www.google.com/",
    # )


async def get_default_profile(connection: iterm2.Connection) -> iterm2.Profile:
    """Get default profile."""
    default_profile = await iterm2.profile.Profile.async_get_default(connection)
    return default_profile


async def get_connection() -> iterm2.Connection:
    """Get connection and register tools."""
    connection = await iterm2.Connection().async_create()
    return connection


async def get_app(connection: iterm2.Connection) -> iterm2.App:
    """Get iTerm2 app."""
    app = await iterm2.async_get_app(connection, create_if_needed=True)
    if app is None:
        raise RuntimeError("Could not get iTerm2 app")
    return app


async def get_window(
    app: iterm2.App, connection: iterm2.Connection, profile: iterm2.Profile
) -> iterm2.Window:
    """Get current window."""
    window: iterm2.Window | None = app.current_window or await iterm2.Window.async_create(
        connection, profile.name
    )
    if window is None:
        window = app.windows[0]
    await window.async_activate()
    return window


async def get_tab(window: iterm2.Window) -> iterm2.Tab:
    """Get current tab."""
    tab = window.current_tab or (await window.async_create_tab())
    if tab is None:
        tab = window.tabs[0]
    await tab.async_activate(order_window_front=True)
    return tab


async def get_session(tab: iterm2.Tab) -> iterm2.Session:
    """Get current session."""
    session = tab.current_session or tab.all_sessions[0]
    await session.async_activate(select_tab=True, order_window_front=True)
    return session


async def setup_session() -> GlobaliTermState:
    """Setup window."""
    connection = await get_connection()
    app = await get_app(connection)
    profile = await get_default_profile(connection)
    window = await get_window(app, connection, profile)
    tab = await get_tab(window)
    session = await get_session(tab)

    return GlobaliTermState(
        connection=connection,
        app=app,
        profile=profile,
        window=window,
        tab=tab,
        session=session,
    )


async def main() -> GlobaliTermState:
    """Main function."""

    global_state = await setup_session()

    await global_state.session.async_activate(select_tab=True, order_window_front=True)
    await register_toolbelt_tools(global_state.connection)

    return global_state


if __name__ == "__main__":
    run(main())
