from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, ClassVar, Concatenate, Coroutine, Literal, overload

import iterm2
from dotenv import load_dotenv
from iterm2 import (
    app,
    connection,
    profile,
    prompt,
    session,
    tab,
    transaction,
    util,
    window,
)

# from websockets import ClientConnection, ConnectionClosed, ConnectionClosedError
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from websockets.legacy.client import WebSocketClientProtocol

from iterm2_api_wrapper.logging import PrettyLog
from iterm2_api_wrapper.typings import (
    GlobalVar,
    GlobalVariable,
    SessionVar,
    SessionVariable,
    TabVar,
    TabVariable,
    Variable,
    VariableContext,
    WindowVar,
    WindowVariable,
)


load_dotenv()
log = PrettyLog.get_logger(__name__)


def _validate_state[**P, T](
    method: Callable[Concatenate[iTermState, P], Coroutine[Any, Any, T]],
) -> Callable[Concatenate[iTermState, P], Coroutine[Any, Any, T]]:
    """Decorator that validates state and auto-routes to the correct event loop."""

    @wraps(method)
    async def async_wrapper(self: iTermState, *args: P.args, **kwargs: P.kwargs) -> T:
        # Auto-route: if we're on the wrong loop, hop to the correct one
        if not self._on_correct_loop():
            loop = self.loop
            if loop is None:
                raise RuntimeError("No event loop available on connection")
            future = asyncio.run_coroutine_threadsafe(
                async_wrapper(
                    self, *args, **kwargs
                ),  # recurse into self on the right loop
                loop,
            )
            return await asyncio.get_running_loop().run_in_executor(None, future.result)

        # We're on the correct loop — validate + execute
        try:
            await self.ensure_state()
            return await method(self, *args, **kwargs)
        except (ConnectionClosed, ConnectionClosedError):
            log.warning("Connection closed, refreshing state and retrying...")
            await self.ensure_state()
            return await method(self, *args, **kwargs)

    if not asyncio.iscoroutinefunction(method):
        raise TypeError(
            "The _validate_state decorator can only be applied to async methods. "
            f"iTermState.{method!r} is not asynchronous."
        )

    return async_wrapper


@dataclass
class iTermState:
    """Global iTerm2 state."""

    connection: connection.Connection
    app: app.App
    window: window.Window
    tab: tab.Tab
    session: session.Session
    profile: profile.Profile

    is_hotkey_window: bool = False

    # Variable accessors to avoid further imports; use for get_variable methods
    SESSION_VAR: ClassVar[type[SessionVar]] = SessionVar
    GLOBAL_VAR: ClassVar[type[GlobalVar]] = GlobalVar
    TAB_VAR: ClassVar[type[TabVar]] = TabVar
    WINDOW_VAR: ClassVar[type[WindowVar]] = WindowVar

    # refresh_callback and _event_loop are set in client.py after initialization
    _refresh_callback: (
        Callable[[], Awaitable[iTermState]] | Awaitable[iTermState] | None
    ) = field(default=None, init=False, repr=False)
    _event_loop: asyncio.AbstractEventLoop | None = field(
        default=None, init=False, repr=False
    )
    # One lock per instance
    _run_command_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False
    )

    def refresh_from(self, new_state: iTermState) -> None:
        """
        Refresh this state in-place from another state instance.

        `iTermClient` uses this to preserve the identity of `client.state` while
        still updating all underlying iTerm2 objects after a reconnect.
        """
        if not isinstance(new_state, iTermState):
            raise TypeError(
                f"refresh_from expects an iTermState; got {type(new_state).__name__!r}"
            )

        self.connection = new_state.connection
        self.app = new_state.app
        self.window = new_state.window
        self.tab = new_state.tab
        self.session = new_state.session
        self.profile = new_state.profile
        self.is_hotkey_window = new_state.is_hotkey_window
        self._refresh_callback = new_state._refresh_callback
        # Preserve _event_loop from existing state if new_state doesn't have one
        if new_state._event_loop is not None:
            self._event_loop = new_state._event_loop

    async def ensure_state(
        self,
        refresh_callback: Callable[[], Awaitable[iTermState]]
        | Awaitable[iTermState]
        | None = None,
    ) -> None:
        """Ensure the state is valid, refreshing if needed."""
        if await self.validated_state():
            return

        callback = refresh_callback or self._refresh_callback
        if callback is None:
            raise RuntimeError("No refresh callback provided to ensure_state")

        new_state = await (callback() if callable(callback) else callback)
        self.refresh_from(new_state)

    async def validated_state(self) -> bool:
        """Validate state by checking if iTerm2 objects are still active.

        Checks (in order):
        1. Websocket connection is open/event loop is available and not closed
        2. App instance responds
        3. Session, window, and tab still exist
        """
        try:
            # Check connection is alive and event loop is usable
            if not self.online:
                return False

            # Check app still responds
            if (
                current_app := await app.async_get_app(
                    self.connection, create_if_needed=False
                )
            ) is None:
                return False
            self.app = current_app

            # Check session still exists
            if (
                new_session := current_app.get_session_by_id(
                    self.session.session_id, include_buried=False
                )
            ) is None:
                return False
            self.session = new_session

            # Refresh owning window/tab from the session
            new_window, new_tab = current_app.get_window_and_tab_for_session(new_session)
            if new_window is None or new_tab is None:
                return False
            self.window = new_window
            self.tab = new_tab

            return True
        except Exception:
            return False

    @property
    def online(self) -> bool:
        """Check if connection is online and event loop is running.

        Returns False if:
        - The websocket is not open
        - The event loop is closed or not set
        """
        websocket_open: WebSocketClientProtocol | None = getattr(
            self.connection.websocket, "open", False
        )
        if not websocket_open:
            return False
        # Also check if event loop is still usable
        loop = self.loop
        if loop is None or loop.is_closed():
            return False
        return True

    @property
    def debug(self) -> bool:
        """Check if connection is in debug mode."""
        loop = self.loop
        if loop is None:
            return False
        return loop.get_debug()

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """Get the event loop associated with this state.

        This is the loop that all iTerm2 API calls must run on.
        Prefers the explicitly set _event_loop, falling back to connection.loop.
        """
        return self._event_loop or self.connection.loop

    def _on_correct_loop(self) -> bool:
        """Check if the current context is running on the connection's event loop.

        Returns:
            True if currently on the connection's loop, False otherwise.
            Also returns False if there's no running loop or no connection loop.
        """
        conn_loop = self.loop
        if conn_loop is None:
            return False
        try:
            current_loop = asyncio.get_running_loop()
            return current_loop is conn_loop
        except RuntimeError:
            # No running loop
            return False

    async def get_session_var(self, name: SessionVariable) -> str:
        """Get a session variable."""
        return await self.get_variable(ctx="session", variable=name)

    async def get_window_var(self, name: WindowVariable) -> str:
        """Get a window variable."""
        return await self.get_variable(ctx="window", variable=name)

    async def get_tab_var(self, name: TabVariable) -> str:
        """Get a tab variable."""
        return await self.get_variable(ctx="tab", variable=name)

    async def get_global_var(self, name: GlobalVariable) -> str:
        """Get a global variable."""
        return await self.get_variable(ctx="iterm2", variable=name)

    @overload
    @_validate_state
    async def get_variable(
        self, ctx: Literal["session"], variable: SessionVariable
    ) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: Literal["tab"], variable: TabVariable) -> str: ...
    @overload
    @_validate_state
    async def get_variable(
        self, ctx: Literal["window"], variable: WindowVariable
    ) -> str: ...
    @overload
    @_validate_state
    async def get_variable(
        self, ctx: Literal["iterm2"], variable: GlobalVariable
    ) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: Literal["user"], variable: str) -> str: ...
    @_validate_state
    async def get_variable(self, ctx: VariableContext, variable: Variable) -> str:
        """Get a variable from the specified context."""

        target: tab.Tab | window.Window | session.Session | app.App
        match ctx:
            case x if x in ["session", "user"]:
                target = self.session
            case "tab":
                target = self.tab
            case "window":
                target = self.window
            case "iterm2":
                target = self.app
            case _:
                raise ValueError(f"Invalid context: {ctx!r}")

        return await target.async_get_variable(variable)

    @staticmethod
    def _last_nonempty_line(lines: list[str]) -> str | None:
        """Return the last non-empty terminal line (trimmed), if any."""
        for line in reversed(lines):
            stripped = line.strip()
            if stripped:
                return stripped
        return None

    @staticmethod
    def _changed_slice(before: list[str], after: list[str]) -> list[str]:
        """Return the changed block between two terminal snapshots."""
        prefix = 0
        max_prefix = min(len(before), len(after))
        while prefix < max_prefix and before[prefix] == after[prefix]:
            prefix += 1

        suffix = 0
        max_suffix = min(len(before) - prefix, len(after) - prefix)
        while suffix < max_suffix and before[-(suffix + 1)] == after[-(suffix + 1)]:
            suffix += 1

        end = len(after) - suffix if suffix else len(after)
        return after[prefix:end]

    @staticmethod
    def _extract_output_from_changed_block(
        changed: list[str], *, prompt_line: str, command: str
    ) -> str:
        """
        Trim command echo + trailing prompt from changed block and return output.
        """
        start = 0
        end = len(changed)
        while start < end and not changed[start].strip():
            start += 1
        while end > start and not changed[end - 1].strip():
            end -= 1
        block = changed[start:end]

        if not block:
            return ""

        prompt_norm = prompt_line.strip()
        command_norm = command.strip()

        # Drop echoed command line (e.g. "<prompt> <command>")
        first = block[0].strip()
        if (
            command_norm
            and first.endswith(command_norm)
            and prompt_norm
            and prompt_norm in first
        ):
            block = block[1:]

        # Drop trailing prompt line
        while block and not block[-1].strip():
            block.pop()
        if block and block[-1].strip() == prompt_norm:
            block.pop()

        return "\n".join(line.rstrip("\n") for line in block).strip()

    async def _get_prompt_candidate(
        self, *, suppress_broadcast: bool, retries: int = 2, retry_delay: float = 0.1
    ) -> tuple[list[str], str]:
        """
        Get terminal snapshot + prompt candidate.

        Works even when scrollback height is 0 by scanning for the last non-empty line.
        If no candidate exists, nudge with Enter a small bounded number of times.
        """
        lines = await self._get_terminal_contents()
        prompt_line = self._last_nonempty_line(lines)

        attempts = 0
        while prompt_line is None and attempts < retries:
            await self.session.async_send_text(
                "\r", suppress_broadcast=suppress_broadcast
            )
            await asyncio.sleep(retry_delay)
            lines = await self._get_terminal_contents()
            prompt_line = self._last_nonempty_line(lines)
            attempts += 1

        if prompt_line is None:
            raise RuntimeError(
                "Unable to identify prompt line in terminal contents for fallback execution."
            )

        return lines, prompt_line

    async def _run_command_without_shell_integration(
        self, *, command: str, suppress_broadcast: bool, timeout: float = 10.0
    ) -> str:
        """
        Run command without shell integration by snapshot-diff + prompt reappearance.

        Key points:
        - No dependency on scrollback_buffer_height > 0
        - Uses last non-empty line as prompt candidate
        - Bounded by timeout
        - Requires prompt match to be stable across 2 polls
        """
        start_lines, prompt_line = await self._get_prompt_candidate(
            suppress_broadcast=suppress_broadcast
        )

        log.debug(
            f"Fallback run start: line_count={len(start_lines)}, prompt={prompt_line!r}"
        )

        await self.session.async_send_text(
            command + "\r", suppress_broadcast=suppress_broadcast
        )

        loop = self.loop or asyncio.get_running_loop()
        deadline = loop.time() + max(0.1, timeout)
        poll_interval = 0.1

        saw_change = False
        stable_prompt_polls = 0
        end_lines = start_lines

        while True:
            end_lines = await self._get_terminal_contents()

            if not saw_change and end_lines != start_lines:
                saw_change = True

            last_nonempty = self._last_nonempty_line(end_lines)
            if saw_change and last_nonempty == prompt_line:
                stable_prompt_polls += 1
                if stable_prompt_polls >= 2:
                    break
            else:
                stable_prompt_polls = 0

            if loop.time() >= deadline:
                raise TimeoutError(
                    "Timeout waiting for command completion (shell integration disabled)."
                )

            await asyncio.sleep(poll_interval)

        changed = self._changed_slice(start_lines, end_lines)
        output = self._extract_output_from_changed_block(
            changed, prompt_line=prompt_line, command=command
        )

        log.debug(
            f"Fallback run end: line_count={len(end_lines)}, output_len={len(output)}"
        )
        return output

    @_validate_state
    async def run_command(
        self,
        command: str,
        path: str | None = None,
        broadcast: bool = False,
        timeout: float = 10.0,
    ) -> str:
        """Run a command and return its output"""
        suppress = not broadcast

        async with self._run_command_lock:
            current_path = await self.get_session_var("path")
            if path and current_path != path:
                await self.session.async_send_text(
                    f"cd '{path}'\r", suppress_broadcast=suppress
                )
            shell_integration_enabled = await self._shell_integration_enabled()
            if not shell_integration_enabled:
                log.warning(
                    "Shell integration not enabled; falling back to non-shell-integration method."
                )
                return await self._run_command_without_shell_integration(
                    command=command, suppress_broadcast=suppress, timeout=timeout
                )

            async with transaction.Transaction(self.connection):
                await self.session.async_send_text(
                    command + "\r", suppress_broadcast=suppress
                )
                last_prompt: prompt.Prompt | None = await self._get_prompt()
                if last_prompt is None:
                    log.warning(
                        ":warning: Shell integration appears broken (fresh tab?); Unable to get last prompt. "
                        "Running command without shell integration."
                    )
                    return await self._run_command_without_shell_integration(
                        command=command, suppress_broadcast=suppress, timeout=timeout
                    )

                task = asyncio.create_task(self._wait_for_prompt(timeout=timeout))

            # Wait for the command to end.
            result = await task
            if not result:
                log.warning(
                    ":warning: Command timeout; Running command without shell integration."
                )
                return await self._run_command_without_shell_integration(
                    command=command, suppress_broadcast=suppress, timeout=timeout
                )

            # Re-fetch the prompt for the command we sent to get the output range
            async with transaction.Transaction(self.connection):
                content = await self._string_in_lines(last_prompt)
            return content

    async def _get_prompt(self, unique_id: str | None = None) -> None | prompt.Prompt:
        """Get prompt history from the session."""
        prompt_obj: Callable[..., Coroutine[Any, Any, None | prompt.Prompt]]
        call_args: dict[str, Any] = {
            "connection": self.connection,
            "session_id": self.session.session_id,
        }
        if unique_id:
            prompt_obj = iterm2.async_get_prompt_by_id
            call_args["prompt_unique_id"] = unique_id
        else:
            prompt_obj = iterm2.async_get_last_prompt
        last_prompt: None | prompt.Prompt = await prompt_obj(**call_args)
        return last_prompt

    async def _wait_for_prompt(self, *, timeout: float = 30.0) -> bool:
        """Block until the running command terminates. Returns True if command ended, False on timeout."""
        modes = [prompt.PromptMonitor.Mode.COMMAND_END]
        try:
            async with prompt.PromptMonitor(
                self.connection, self.session.session_id, modes
            ) as monitor:
                while True:
                    _type, _ = await asyncio.wait_for(
                        monitor.async_get(), timeout=timeout
                    )
                    if _type == prompt.PromptMonitor.Mode.COMMAND_END:
                        return True
        except TimeoutError:
            return False

    async def _string_in_lines(self, prompt: prompt.Prompt) -> str:
        """Returns a string with the content in a range of lines."""
        updated_prompt = await self._get_prompt(getattr(prompt, "unique_id", ""))
        if updated_prompt is None:
            log.error(":error: Unable to get updated prompt; raising RuntimeError.")
            raise RuntimeError("Failed to retrieve prompt after command execution.")

        output_range: util.CoordRange = updated_prompt.output_range
        cmd_range: util.CoordRange = updated_prompt.command_range
        start_y = output_range.start.y
        end_y = output_range.end.y
        if start_y == 0 and end_y == 0:
            # output_range not populated; fall back to command_range
            log.debug("Prompt output range is empty; falling back to command range.")
            # Add 1 to avoid including the prompt line itself, which is not part of the command output
            start_y = cmd_range.start.y + 1
            end_y = cmd_range.end.y + 1

        contents = await self.session.async_get_contents(start_y, max(1, end_y - start_y))
        result = ""
        for line in contents:
            if not line.string.strip():
                continue
            result += line.string
            if line.hard_eol:
                result += "\n"
        return result

    async def _shell_integration_enabled(self, new_tab_timeout: float = 30.0) -> bool:
        """Use shell-integration-only features to check if shell integration is enabled."""

        async def check_terminal_content() -> list[str]:
            current_terminal_content = [
                line.strip()
                for line in await self._get_terminal_contents()
                if line.strip()
            ]

            return current_terminal_content

        def is_empty_tab(content: list[str]) -> bool:
            # Consider freshly cleared tabs, which doesn't reset the prompt
            return len(content) == 1 and not any(
                "last login" in line.lower() for line in content
            )

        terminal_content = await check_terminal_content()

        if len(terminal_content) <= 1:
            while new_tab_timeout > 0:
                log.debug(
                    f"Terminal content appears empty; waiting for shell integration to initialize... ({new_tab_timeout:.0f}s remaining)"
                )
                await asyncio.sleep(5)
                terminal_content = await check_terminal_content()

                if is_empty_tab(terminal_content):
                    log.debug("Terminal content is empty; no new tab.")
                    break
                elif len(terminal_content) > 1:
                    log.debug("New tab detected based on terminal content.")
                    break
                new_tab_timeout -= 5
            else:
                log.warning(
                    "Timeout waiting for shell integration initialization; "
                    "treating shell integration as unavailable."
                )
                return False

        user_found = (
            user_var := await self.get_session_var("username")
        ) is not None and user_var.strip() != ""
        host_found = (
            host_var := await self.get_session_var("hostname")
        ) is not None and host_var.strip() != ""
        prompt_check = await self._get_prompt() is not None

        log.debug(
            f"prompt_check={prompt_check}",
            f"user_found={user_found} - user_var={user_var}",
            f"host_found={host_found} - host_var={host_var}",
            sep="\n",
        )

        return prompt_check and user_found and host_found

    async def _get_terminal_contents(self) -> list[str]:
        """Get the terminal screen contents."""
        line_info = await self.session.async_get_line_info()
        start = line_info.overflow
        total_lines = line_info.scrollback_buffer_height + line_info.mutable_area_height
        # log.debug(
        #     "Getting terminal contents: "
        #     f"overflow={line_info.overflow}, scrollback_buffer_height={line_info.scrollback_buffer_height}, mutable_area_height={line_info.mutable_area_height}"
        # )
        contents = [
            line.string
            for line in await self.session.async_get_contents(
                first_line=start, number_of_lines=total_lines
            )
        ]
        return contents

    def asdict(self) -> dict[str, Any]:
        """Convert iTermState to dictionary."""
        return {
            key: {k: v for k, v in value.__dict__.items()}
            if hasattr(value, "__dict__")
            else value
            for key, value in self.__dict__.items()
            if not key.startswith("_")
        }
