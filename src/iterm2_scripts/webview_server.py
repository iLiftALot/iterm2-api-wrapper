"""Web browser for iTerm2 toolbelt using URL re-registration.

This uses the native WKWebView by re-registering the tool with new URLs,
avoiding all iframe/proxy issues. Sites are loaded directly by the native
webview, so ALL sites work including Google, GitHub, etc.
"""
from __future__ import annotations

import asyncio
import signal
from typing import TYPE_CHECKING

import iterm2
import iterm2.mainmenu
import iterm2.tool
from aiohttp import web

if TYPE_CHECKING:
    from iterm2 import Connection

# Configuration
WEBVIEW_PORT = 9998
WEBVIEW_URL = f"http://localhost:{WEBVIEW_PORT}/"
TOOL_IDENTIFIER = "com.iterm2scripts.webbrowser"
TOOL_NAME = "Web Browser"
STATUSBAR_IDENTIFIER = "com.iterm2scripts.webbrowser.home"
MENUBAR_IDENTIFIER = "com.iterm2scripts.webbrowser.home.menu"

# Global connection reference for re-registration
_connection: Connection | None = None

# Track web server for cleanup
_web_runner: web.AppRunner | None = None


# Landing page HTML - clean, simple
LANDING_PAGE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Web Browser</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            background: #1e1e1e;
            color: #fff;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .toolbar {
            display: flex;
            padding: 10px;
            background: #2d2d2d;
            gap: 8px;
        }
        .nav-btn {
            background: #007acc;
            border: none;
            color: #fff;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
        }
        .nav-btn:hover { background: #005a9e; }
        #url-input {
            flex: 1;
            padding: 8px 12px;
            border: 1px solid #404040;
            border-radius: 4px;
            background: #1e1e1e;
            color: #fff;
            font-size: 14px;
        }
        #url-input:focus { outline: none; border-color: #007acc; }
        .bookmarks {
            display: flex;
            padding: 10px;
            background: #252525;
            gap: 8px;
            flex-wrap: wrap;
        }
        .bookmark {
            background: #353535;
            border: none;
            color: #ccc;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            text-decoration: none;
        }
        .bookmark:hover { background: #454545; color: #fff; }
        .content {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            gap: 20px;
            padding: 40px;
        }
        h1 { font-weight: 300; font-size: 28px; color: #888; }
        p { color: #666; font-size: 14px; max-width: 500px; text-align: center; line-height: 1.6; }
        .note { background: #2a2a2a; padding: 15px; border-radius: 8px; margin-top: 10px; }
    </style>
</head>
<body>
    <form class="toolbar" action="/navigate" method="POST">
        <input type="text" id="url-input" name="url" placeholder="Enter URL or search term..." autofocus>
        <button type="submit" class="nav-btn">Go</button>
    </form>
    <div class="bookmarks">
        <a class="bookmark" href="/go?url=https://www.google.com/">Google</a>
        <a class="bookmark" href="/go?url=https://docs.python.org/3/">Python Docs</a>
        <a class="bookmark" href="/go?url=https://iterm2.com/python-api/">iTerm2 API</a>
        <a class="bookmark" href="/go?url=https://github.com/">GitHub</a>
        <a class="bookmark" href="/go?url=https://developer.mozilla.org/">MDN</a>
        <a class="bookmark" href="/go?url=https://en.wikipedia.org/">Wikipedia</a>
        <a class="bookmark" href="/go?url=https://news.ycombinator.com/">Hacker News</a>
        <a class="bookmark" href="/go?url=https://lite.duckduckgo.com/">DuckDuckGo</a>
    </div>
    <div class="content">
        <h1>iTerm2 Web Browser</h1>
        <p>Enter a URL above or click a bookmark. The page will load directly
           in iTerm2's native webview - all sites work, including Google and GitHub!</p>
        <div class="note">
            <p><strong>Tip:</strong> Use the 🏠 status bar component to return here from any page.</p>
        </div>
    </div>
</body>
</html>
"""


async def navigate_to_url(url: str) -> bool:
    """Re-register the webview tool with a new URL."""
    global _connection
    if _connection is None:
        return False

    # Ensure URL has a scheme
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        await iterm2.tool.async_register_web_view_tool(
            connection=_connection,
            display_name=TOOL_NAME,
            identifier=TOOL_IDENTIFIER,
            reveal_if_already_registered=True,
            url=url,
        )
        return True
    except Exception as e:
        print(f"Failed to navigate: {e}")
        return False


async def go_home() -> bool:
    """Navigate back to the landing page."""
    return await navigate_to_url(WEBVIEW_URL)


def create_app() -> web.Application:
    """Create the aiohttp web application."""

    async def index(request: web.Request) -> web.Response:
        """Serve the landing page."""
        return web.Response(text=LANDING_PAGE, content_type="text/html")

    async def navigate_post(request: web.Request) -> web.Response:
        """Handle form POST to navigate to a URL."""
        data = await request.post()
        url = str(data.get("url", "")).strip()
        if url:
            await navigate_to_url(url)
        # Return a page with a Home link while navigating
        return web.Response(
            text="""<html><head><meta charset="utf-8"></head>
            <body style='background:#1e1e1e;color:#888;font-family:sans-serif;padding:40px;text-align:center;'>
            <p>Navigating...</p>
            <p style='margin-top:20px;'><a href='/' style='color:#007acc;'>← Back to Home</a></p>
            </body></html>""",
            content_type="text/html",
        )

    async def navigate_get(request: web.Request) -> web.Response:
        """Handle GET navigation (for bookmarks)."""
        url = request.query.get("url", "").strip()
        if url:
            await navigate_to_url(url)
        return web.Response(
            text="""<html><head><meta charset="utf-8"></head>
            <body style='background:#1e1e1e;color:#888;font-family:sans-serif;padding:40px;text-align:center;'>
            <p>Navigating...</p>
            <p style='margin-top:20px;'><a href='/' style='color:#007acc;'>← Back to Home</a></p>
            </body></html>""",
            content_type="text/html",
        )

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/navigate", navigate_post)
    app.router.add_get("/go", navigate_get)
    return app


async def register_home_components(connection: Connection) -> None:
    """Register a status bar component that acts as a Home button."""
    status_bar_component = iterm2.StatusBarComponent(
        short_description="Browser Home",
        detailed_description="Click to return to the web browser home page",
        knobs=[],
        exemplar="🏠",
        update_cadence=None,
        identifier=STATUSBAR_IDENTIFIER,
    )

    @iterm2.StatusBarRPC
    async def home_coro(knobs):
        return "🏠"

    @iterm2.RPC
    async def home_click(session_id):
        await go_home()

    @iterm2.ContextMenuProviderRPC
    async def browser_home_menu(session_id=iterm2.Reference("id")):  # noqa: B008
        """Context menu item to go back to browser home."""
        await go_home()

    # Register status bar and context menu components
    await status_bar_component.async_register(connection, home_coro, onclick=home_click)

    # Register context menu item
    await browser_home_menu.async_register(
        connection=connection,
        display_name="🏠 Browser Home",
        unique_identifier=MENUBAR_IDENTIFIER,
    )

    # Note: RPC tokens are set on the decorated functions after registration,
    # but the iterm2 library doesn't expose a reliable way to unsubscribe them.
    # The RPCs will be cleaned up when the connection closes.

async def start_webview_server(connection: Connection) -> None:
    """Start the web server and register the webview tool."""
    global _connection, _web_runner
    _connection = connection

    # Start the web server
    app = create_app()
    _web_runner = web.AppRunner(app)
    await _web_runner.setup()
    site = web.TCPSite(_web_runner, "localhost", WEBVIEW_PORT)
    await site.start()
    print(f"Web server started at {WEBVIEW_URL}")

    # Register the webview tool pointing to our landing page
    await iterm2.tool.async_register_web_view_tool(
        connection=connection,
        display_name=TOOL_NAME,
        identifier=TOOL_IDENTIFIER,
        reveal_if_already_registered=True,
        url=WEBVIEW_URL,
    )
    print(f"Registered webview tool: {TOOL_NAME}")

    # Register the Home status bar and context menu components
    await register_home_components(connection)
    print("Registered Home status bar and context menu components")


# Simple goodbye page - complex data URLs cause REQUEST_MALFORMED errors
GOODBYE_URL = "about:blank"


async def cleanup(hide_toolbelt: bool = False) -> None:
    """Clean up all registered components and stop the web server.

    Args:
        hide_toolbelt: If True, hide the entire toolbelt (affects all tools).
    """
    global _connection, _web_runner

    print("\nCleaning up...")

    # Navigate to blank page before stopping the server
    # This clears the content so it doesn't show an error when localhost is gone
    if _connection:
        try:
            await iterm2.tool.async_register_web_view_tool(
                connection=_connection,
                display_name=TOOL_NAME,
                identifier=TOOL_IDENTIFIER,
                reveal_if_already_registered=False,
                url=GOODBYE_URL,
            )
            print("  Navigated to blank page")
        except Exception as e:
            print(f"  Failed to show blank page: {e}")

    # Optionally hide the toolbelt
    if hide_toolbelt and _connection:
        try:
            await iterm2.mainmenu.MainMenu.async_select_menu_item(_connection, "Show Toolbelt")
            print("  Toggled toolbelt visibility")
        except Exception as e:
            print(f"  Failed to toggle toolbelt: {e}")

    # Note: RPCs are automatically cleaned up when the connection closes.
    # There's no need to manually unsubscribe them.

    # Stop the web server
    if _web_runner:
        await _web_runner.cleanup()
        print("  Stopped web server")
        _web_runner = None

    # Note: There's no API to unregister a webview tool - it persists until
    # iTerm2 restarts or the user manually removes it from the Toolbelt menu.

    _connection = None
    print("Cleanup complete")


async def run_webview_browser() -> None:
    """Main entry point - connect to iTerm2 and run the browser."""
    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def signal_handler():
        """Handle shutdown signals."""
        shutdown_event.set()

    # Register signal handlers for graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    connection: Connection | None = None
    try:
        # Connect to iTerm2
        connection = await iterm2.Connection().async_create()
        await start_webview_server(connection)

        # Wait for shutdown signal
        print("Webview browser running. Press Ctrl+C to stop.")
        await shutdown_event.wait()

    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Always run cleanup
        await cleanup()

        # Remove signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
