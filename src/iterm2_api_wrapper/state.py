from __future__ import annotations

import asyncio
import base64
import os
import re
import time
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Concatenate, Coroutine, Literal, overload

import iterm2
from dotenv import load_dotenv
from iterm2 import app, connection, profile, prompt, screen, session, tab, util, window
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from iterm2_api_wrapper.typings import (
    GlobalVars,
    SessionVars,
    TabVars,
    VarContext,
    WindowVars,
)
from iterm2_api_wrapper.utils import log


load_dotenv()


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
                async_wrapper(self, *args, **kwargs),  # recurse into self on the right loop
                loop,
            )
            return await asyncio.get_running_loop().run_in_executor(None, future.result)

        # We're on the correct loop — validate + execute
        try:
            await self.ensure_state()
            return await method(self, *args, **kwargs)
        except (ConnectionClosed, ConnectionClosedError):
            log("Connection closed, refreshing state and retrying...")
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

    # refresh_callback is set in client.py after initialization
    refresh_callback: Callable[[], Awaitable[Any]] | None = None
    is_hotkey_window: bool = False
    _event_loop: asyncio.AbstractEventLoop | None = field(
        default=None, init=False, repr=False
    )
    _run_command_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False
    )

    def refresh_from(self, new_state: Any) -> None:
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
        self.refresh_callback = new_state.refresh_callback
        # Preserve _event_loop from existing state if new_state doesn't have one
        if new_state._event_loop is not None:
            self._event_loop = new_state._event_loop

    async def ensure_state(
        self,
        refresh_callback: Callable[[], Awaitable[Any]] | Awaitable[Any] | None = None,
    ) -> None:
        """Ensure the state is valid, refreshing if needed."""
        if await self.validated_state():
            return

        callback = refresh_callback or self.refresh_callback
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
        websocket_open = getattr(self.connection.websocket, "open", False)
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
        loop = self.connection.loop
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

    async def get_session_var(self, name: SessionVars) -> str:
        """Get a session variable."""
        return await self.get_variable(ctx="session", variable_name=name)

    async def get_window_var(self, name: WindowVars) -> str:
        """Get a window variable."""
        return await self.get_variable(ctx="window", variable_name=name)

    async def get_tab_var(self, name: TabVars) -> str:
        """Get a tab variable."""
        return await self.get_variable(ctx="tab", variable_name=name)

    async def get_global_var(self, name: GlobalVars) -> str:
        """Get a global variable."""
        return await self.get_variable(ctx="iterm2", variable_name=name)

    @overload
    @_validate_state
    async def get_variable(
        self, ctx: Literal["session"], variable_name: SessionVars
    ) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: Literal["tab"], variable_name: TabVars) -> str: ...
    @overload
    @_validate_state
    async def get_variable(
        self, ctx: Literal["window"], variable_name: WindowVars
    ) -> str: ...
    @overload
    @_validate_state
    async def get_variable(
        self, ctx: Literal["iterm2"], variable_name: GlobalVars
    ) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: Literal["user"], variable_name: str) -> str: ...
    @_validate_state
    async def get_variable(self, ctx: VarContext, variable_name: str) -> str:
        """Get a variable from the specified context."""

        target: tab.Tab | window.Window | session.Session | app.App
        match ctx:
            case "session" | "user":
                target = self.session
            case "tab":
                target = self.tab
            case "window":
                target = self.window
            case "iterm2":
                target = self.app
            case _:
                raise ValueError(f"Invalid context: {ctx!r}")
        return await target.async_get_variable(variable_name)

    @staticmethod
    def _sh_single_quote(value: str) -> str:
        """Return a POSIX-shell-safe single-quoted literal.

        This is used to embed an arbitrary command string inside a wrapper
        command without letting characters like `#` turn into comments.
        """
        if "\x00" in value:
            raise ValueError("Command contains NUL byte, which is not supported.")
        # Close quote, insert a literal single-quote, and reopen.
        return "'" + value.replace("'", "'\"'\"'") + "'"

    @staticmethod
    def _wrap_with_markers(command: str) -> tuple[str, str, str]:
        """Wrap a command with unique begin/end sentinels.

        Designed for the "shell integration off" fallback.

        Important details:
        - The *contiguous* marker strings we search for do NOT appear in the
          echoed command line because the token is passed as a separate printf
          argument. This prevents false positives when scanning scrollback.
                - We preserve the interactive shell's `$?` by ensuring the *final*
                    command in the wrapper exits with the user's command status. We do
                    this by running the user's command via `eval` inside an `if`, and
                    then using a tiny `sh -c ...; exit "$1"` trampoline to both print
                    the END marker and exit with that status.
                - We deliberately avoid wrapping the whole thing in a subshell like
                    `( ... )` because some interactive zsh configurations auto-insert a
                    matching `)` when `(` is typed (autopair widgets), producing invalid
                    syntax.
                - To avoid autopair widgets corrupting *the user's command text* (e.g.
                    commands containing `(`), we base64-encode the command and decode it
                    at runtime. This keeps the injected keystream free of `(` characters.
        """

        token = uuid.uuid4().hex[:12]
        begin = f"__PYTERM_MCP_BEGIN__{token}__"
        end_prefix = f"__PYTERM_MCP_END__{token}__"

        # NOTE: We base64-encode the user command before injecting it.
        # This prevents zle "autopair" widgets from rewriting characters like
        # `(` in the *injected keystream* (which can otherwise lead to stray
        # extra `)` and parse errors).
        cmd_b64 = base64.b64encode(command.encode("utf-8")).decode("ascii")
        cmd_b64_literal = iTermState._sh_single_quote(cmd_b64)

        # Implementation notes:
        # - We must print the END marker *after* the user's command output.
        # - We must also preserve interactive `$?` == user's command status.
        #
        # We accomplish this by:
        # 1) printing the BEGIN marker
        # 2) running `eval <cmd>` as the `if` condition
        # 3) in both branches, running a final `sh -c` that prints the END
        #    marker and exits with the status passed as $1. Because that `sh`
        #    command is the last command executed in the wrapper, the
        #    interactive shell's `$?` remains correct.
        end_trampoline = (
            f'command sh -c \'printf "%s%s:%d\\n" "__PYTERM_MCP_END__" '
            f'"{token}__" "$1"; exit "$1"\' sh'
        )

        wrapped = (
            f'printf "%s%s\\n" "__PYTERM_MCP_BEGIN__" "{token}__"; '
            f"if eval \"`printf '%s' {cmd_b64_literal} | base64 -d`\"; then "
            f"{end_trampoline} 0; "
            f'else {end_trampoline} "$?"; '
            "fi"
        )

        return wrapped, begin, end_prefix

    async def _snapshot_tail_lines(
        self, *, max_lines: int
    ) -> tuple[int, list[screen.LineContents]]:
        """Read the last up-to `max_lines` lines from scrollback+screen.

        Returns (start_line_number, lines).

        Uses a short transaction so `async_get_line_info()` and
        `async_get_contents()` are consistent.
        """
        if max_lines <= 0:
            return 0, []

        async with iterm2.Transaction(self.connection):
            li = await self.session.async_get_line_info()
            overflow = li.overflow
            total = li.scrollback_buffer_height + li.mutable_area_height
            if total <= 0:
                return overflow, []
            bottom_exclusive = overflow + total
            start = max(overflow, bottom_exclusive - max_lines)
            lines = await self.session.async_get_contents(
                first_line=start, number_of_lines=bottom_exclusive - start
            )
            return start, lines

    async def _snapshot_range(
        self, *, first_line: int, last_line_inclusive: int
    ) -> tuple[int, list[screen.LineContents]]:
        """Read a contiguous inclusive line range.

        Returns (start_line_number, lines). If the requested range is empty or
        out-of-bounds, returns an empty list.
        """
        if last_line_inclusive < first_line:
            return first_line, []

        async with iterm2.Transaction(self.connection):
            li = await self.session.async_get_line_info()
            overflow = li.overflow
            total = li.scrollback_buffer_height + li.mutable_area_height
            if total <= 0:
                return overflow, []
            bottom_exclusive = overflow + total

            start = max(overflow, first_line)
            end_exclusive = min(bottom_exclusive, last_line_inclusive + 1)
            if end_exclusive <= start:
                return start, []
            lines = await self.session.async_get_contents(
                first_line=start, number_of_lines=end_exclusive - start
            )
            return start, lines

    @staticmethod
    def _render_lines_until_end_marker(
        lines: list[screen.LineContents], *, end_prefix: str
    ) -> str:
        """Convert LineContents to text, stopping at the end marker.

        The end marker might appear on its own line *or* be appended to the end
        of a line when the command doesn't output a trailing newline.
        """
        marker_token = f"{end_prefix}:"
        out_parts: list[str] = []
        for line in lines:
            s = line.string
            pos = s.find(marker_token)
            if pos != -1:
                if pos > 0:
                    out_parts.append(s[:pos])
                # Do not include this line's hard_eol; the newline comes from
                # the marker printf and is not part of the command output.
                break
            out_parts.append(s)
            if line.hard_eol:
                out_parts.append("\n")
        return "".join(out_parts)

    async def _run_command_without_shell_integration(
        self,
        *,
        command: str,
        path: str | None = None,
        suppress_broadcast: bool,
        timeout: float,
        tail_probe_lines: int = 300,
    ) -> str:
        """Run a command and return output without shell integration.

        Strategy:
        - Wrap the command with begin/end sentinels.
        - Poll the *tail* of scrollback until the end sentinel appears.
        - Extract only the text between sentinels using bounded scrollback reads.

        This avoids repeatedly fetching the entire scrollback buffer and does
        not rely on ScreenStreamer notifications (which may not fire reliably
        in all environments).
        """
        wrapped, begin, end_prefix = self._wrap_with_markers(command)
        end_re = re.compile(rf"{re.escape(end_prefix)}:(?P<status>-?\d+)")
        deadline = time.monotonic() + max(0.0, timeout)

        await self.session.async_send_text(
            "\x01\x0b" + wrapped + "\r", suppress_broadcast=suppress_broadcast
        )

        end_line: int | None = None
        sleep_s = 0.05
        while end_line is None:
            start_line, lines = await self._snapshot_tail_lines(
                max_lines=tail_probe_lines
            )
            for i in range(len(lines) - 1, -1, -1):
                if end_re.search(lines[i].string):
                    end_line = start_line + i
                    break

            if end_line is not None:
                break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "Timeout waiting for command to complete (shell integration disabled)."
                )
            await asyncio.sleep(min(sleep_s, remaining))
            sleep_s = min(sleep_s * 1.5, 0.5)

        assert end_line is not None, (
            "ERROR: end_line should be set here <_run_command_without_shell_integration>"
        )

        # At this point we have observed the end marker -> command finished.
        # Now find the begin marker by scanning backward from end_line.
        async with iterm2.Transaction(self.connection):
            li = await self.session.async_get_line_info()
            overflow = li.overflow

        begin_line: int | None = None
        window = max(500, tail_probe_lines)
        while True:
            start = max(overflow, end_line - window)
            _, block = await self._snapshot_range(
                first_line=start, last_line_inclusive=end_line
            )
            for i in range(len(block) - 1, -1, -1):
                if begin in block[i].string:
                    begin_line = start + i
                    break
            if begin_line is not None:
                break
            if start == overflow:
                break
            window *= 2

        # Best-effort: if begin marker scrolled out, start from the earliest available line.
        content_start = (begin_line + 1) if begin_line is not None else overflow
        _, output_block = await self._snapshot_range(
            first_line=content_start, last_line_inclusive=end_line
        )
        return self._render_lines_until_end_marker(output_block, end_prefix=end_prefix)

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
        current_path = await self.get_session_var("path")
        if path and current_path != path:
            await self.session.async_send_text(
                f"cd '{path}'\r", suppress_broadcast=suppress
            )

        async with self._run_command_lock:
            shell_integration_enabled = await self._shell_integration_enabled()
            if not shell_integration_enabled:
                log(
                    "Shell integration not enabled; falling back to non-shell-integration method."
                )
                return await self._run_command_without_shell_integration(
                    command=command,
                    path=path,
                    suppress_broadcast=suppress,
                    timeout=timeout,
                )

            async with iterm2.Transaction(self.connection):
                await self.session.async_send_text(
                    command + "\r", suppress_broadcast=suppress
                )
                last_prompt: prompt.Prompt | None = await self._get_prompt()
                if last_prompt is None:
                    log(
                        ":warning: Shell integration appears broken; Unable to get last prompt. Exiting..."
                    )
                    return "Shell integration appears broken; Unable to get last prompt. Exiting..."

                task = asyncio.create_task(self._wait_for_prompt(timeout=timeout))

            # Wait for the command to end.
            result = await task
            if not result:
                log(":warning: Command timeout; Exiting shell-integration method...")
                return "Command timeout; Exiting shell-integration method..."

            # Re-fetch the prompt for the command we sent to get the output range
            async with iterm2.Transaction(self.connection):
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
        modes = [iterm2.PromptMonitor.Mode.COMMAND_END]
        try:
            async with iterm2.PromptMonitor(
                self.connection, self.session.session_id, modes
            ) as monitor:
                while True:
                    _type, _ = await asyncio.wait_for(
                        monitor.async_get(), timeout=timeout
                    )
                    if _type == iterm2.PromptMonitor.Mode.COMMAND_END:
                        return True
        except TimeoutError:
            return False

    async def _string_in_lines(self, prompt: prompt.Prompt) -> str:
        """Returns a string with the content in a range of lines."""
        updated_prompt = await self._get_prompt(getattr(prompt, "unique_id", ""))
        if updated_prompt is None:
            log(":warning: Unable to get updated prompt; returning empty string.")
            return "Unable to get updated prompt; returning empty string."
        output_range: util.CoordRange = updated_prompt.output_range
        cmd_range: util.CoordRange = updated_prompt.command_range
        start_y = output_range.start.y
        end_y = output_range.end.y
        if start_y == 0 and end_y == 0:
            # output_range not populated; fall back to command_range
            start_y = max(0, cmd_range.start.y - 3)
            end_y = cmd_range.end.y
        contents = await self.session.async_get_contents(start_y, max(1, end_y - start_y))
        result = ""
        for line in contents:
            if not line.string.strip():
                continue
            result += line.string
            if line.hard_eol:
                result += "\n"
        return result

    async def _shell_integration_enabled(self) -> bool:
        """Use shell-integration-only features to check if shell integration is enabled."""
        shell_integration_enabled = (
            os.getenv("ITERM_SHELL_INTEGRATION_INSTALLED", "").lower() == "yes"
        )
        prompt_check = await self._get_prompt()
        return shell_integration_enabled and prompt_check is not None

    async def _get_terminal_contents(self) -> list[str]:
        """Get the terminal screen contents."""
        line_info = await self.session.async_get_line_info()
        start = line_info.overflow
        total_lines = line_info.scrollback_buffer_height + line_info.mutable_area_height
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
            if key not in {"refresh_callback", "_run_command_lock", "_event_loop"}
        }
