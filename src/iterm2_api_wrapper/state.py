from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import shlex
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any, ClassVar, Concatenate, Literal, cast, overload

from websockets import ConcurrencyError, ConnectionClosed

from ._logging import PrettyLog
from .alert import poly_modal_alert_handler
from .api.it2app import async_get_app
from .api.it2prompt import PromptMonitor, async_get_last_prompt, async_get_prompt_by_id, prompt
from .api.it2transaction import Transaction
from .api.it2variable import AppVarEnum, SessionVarEnum, TabVarEnum, UserVarEnum, WindowVarEnum
from .typings import CommandExecutionResult, CommandExecutionStatus, HexCodeEnum


if TYPE_CHECKING:
    from .api.it2app import App
    from .api.it2connection import Connection
    from .api.it2profile import PartialProfile, Profile
    from .api.it2prompt import Prompt
    from .api.it2session import Session
    from .api.it2tab import Tab
    from .api.it2window import Window
    from .typings import HexCode

    # fmt: off
    from .api.it2variable import (  # isort: skip
        AppScope, AppVariable, AppVarKey,
        SessionScope, SessionVariable, SessionVarKey,
        TabScope, TabVariable, TabVarKey,
        UserScope, UserVariable, UserVarKey,
        Variable, VariableScope,
        WindowScope, WindowVariable, WindowVarKey
    )
    # fmt: on


log = PrettyLog.get_logger(__name__)
DEFAULT_SHELL_INTEGRATION_PATH = str(Path.home().joinpath(".iterm2_shell_integration.{shell}"))


def _has_session_value(value: object) -> bool:
    return value is not None and bool(str(value).strip())


def _is_marker_line(line: str, marker: str) -> bool:
    return line.strip() == marker


def _strip_marker_suffix(lines: list[str], marker: str) -> list[str]:
    """Drop the standalone sentinel line and anything printed after it."""
    for index, line in enumerate(lines):
        if _is_marker_line(line, marker):
            return lines[:index]
    return lines


def changed_slice(before: list[str], after: list[str]) -> list[str]:
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


def _validate_state[**P, T](
    method: Callable[Concatenate[iTermState, P], Coroutine[Any, Any, T]],
) -> Callable[Concatenate[iTermState, P], Coroutine[Any, Any, T]]:
    """Decorator that validates state and auto-routes to the correct event loop."""

    @wraps(method)
    async def async_wrapper(self: iTermState, *args: P.args, **kwargs: P.kwargs) -> T:
        # Auto-route: if we're on the wrong loop, hop to the correct one
        if not self._on_correct_loop():
            target_loop = self.loop_manager.require_loop()
            routed = async_wrapper(self, *args, **kwargs)

            try:
                future = asyncio.run_coroutine_threadsafe(routed, target_loop)
            except RuntimeError:
                routed.close()
                self.loop_manager._discard_loop(target_loop)
                raise

            wrapped_future = asyncio.wrap_future(future)

            try:
                return await wrapped_future
            except asyncio.CancelledError:
                cancelled = future.cancel()
                log.debug(
                    f"Cancelled cross-loop call to {method.__qualname__}: "
                    f"future.cancel() -> {cancelled} (done={future.done()} cancelled={future.cancelled()})"
                )
                raise

        # We're on the correct loop — validate + execute
        try:
            await self.ensure_state()
            return await method(self, *args, **kwargs)
        except (ConnectionClosed, ConcurrencyError):
            log.warning("Connection closed, refreshing state and retrying...")
            await self.ensure_state()  # Uses the `_refresh_callback`
            return await method(self, *args, **kwargs)

    if not inspect.iscoroutinefunction(method):
        raise TypeError(
            "The _validate_state decorator can only be applied to async methods. "
            f"iTermState.{method!r} is not asynchronous."
        )

    return async_wrapper


class User:
    """Helper class for user-defined variable context"""

    __user_ref_pattern = re.compile(r"([\S]*?)\.?(user\.[\S]*)")

    def __init__(self, state: iTermState) -> None:
        self.__state = state

    def __contains_user_ref(self, name: str) -> bool:
        return bool(type(self).__user_ref_pattern.search(name))

    def __is_session_member(self, name: str) -> bool:
        user_ctx_part: str = ""
        maybe_match = type(self).__user_ref_pattern.match(name)
        log.debug(f"Checking: {name}... ", maybe_match)

        if maybe_match:
            maybe_prefix_part = maybe_match.group(1)
            maybe_suffix_part = maybe_match.group(2)
            if maybe_prefix_part:
                user_ctx_part = getattr(self.__state.SESSION_VAR, maybe_prefix_part, "")
                log.debug("Found user context part: ", user_ctx_part)
            elif maybe_suffix_part:
                user_ctx_part = maybe_suffix_part
                log.debug("Found user context part: ", user_ctx_part)

        return bool(user_ctx_part)

    def display_name(self, name: str) -> str:
        return f"user.{name}" if not self.__contains_user_ref(name) else name

    @overload
    async def async_get_variable(self, name: Literal["*", UserVarEnum.all]) -> dict[str, str]: ...
    @overload
    async def async_get_variable(self, name: UserVariable) -> str: ...
    async def async_get_variable(self, name: str) -> str | dict[str, str]:
        target = self.__state.session

        if not name.endswith("*"):
            display_name = self.display_name(name)
            if display_name != name:
                direct_value = await target.async_get_variable(name)
                if direct_value is not None:
                    return direct_value
            return await target.async_get_variable(display_name)

        all_session_vars: dict[str, str] = await target.async_get_variable("*")
        all_user_vars = {
            var_name: var_value
            for var_name, var_value in all_session_vars.items()
            if self.__contains_user_ref(var_name) and self.__is_session_member(var_name)
        }

        return all_user_vars


class LoopManager:
    """Resolve and reconcile the event loop that owns an ``iTermState``."""

    def __init__(self, state: iTermState):
        self._state = state

    @staticmethod
    def _usable_loop(loop: asyncio.AbstractEventLoop | None) -> asyncio.AbstractEventLoop | None:
        if loop is None or loop.is_closed():
            return None
        return loop

    def _discard_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._state._event_loop is loop:
            self._state._event_loop = None
        if self._state.connection.loop is loop:
            self._state.connection.loop = None

    def _reconcile_loop(self) -> asyncio.AbstractEventLoop | None:
        state_loop = self._usable_loop(self._state._event_loop)
        connection_loop = self._usable_loop(self._state.connection.loop)

        if state_loop is None and self._state._event_loop is not None:
            self._state._event_loop = None
        if connection_loop is None and self._state.connection.loop is not None:
            self._state.connection.loop = None

        loop = state_loop or connection_loop
        if loop is None:
            return None

        self._state._event_loop = loop
        self._state.connection.loop = loop
        return loop

    def require_loop(self) -> asyncio.AbstractEventLoop:
        loop = self._reconcile_loop()
        if loop is None:
            raise RuntimeError("No usable iTerm event loop is available on this state.")

        if not loop.is_running():
            raise RuntimeError("The iTerm event loop is not running; recreate or refresh the client.")

        return loop

    def _on_correct_loop(self) -> bool:
        loop = self.loop
        if loop is None or not loop.is_running():
            return False

        try:
            return asyncio.get_running_loop() is loop
        except RuntimeError:
            return False

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """Get and reconcile the event loop associated with this state."""
        return self._reconcile_loop()


class MarkedCommand:
    """Creates synthetic iTerm2 shell-integration marks for non-shell-integrated shells."""

    BEFORE_PROMPT = r"\033]133;A\a"
    AFTER_PROMPT = r"\033]133;B\a"
    BEFORE_OUTPUT = r"\033]133;C\a"
    AFTER_OUTPUT = r"\033]133;D;%d\a"

    def __init__(
        self,
        command: str,
        *,
        command_label: str | None = None,
        prompt: str = "iterm2-api-wrapper> ",
    ) -> None:
        self.command = command
        self.label = command if command_label is None else command_label
        self.prompt = prompt

    @property
    def execution_label(self) -> str:
        return shlex.quote(self.label)

    @property
    def execution_prompt(self) -> str:
        return f"{self.BEFORE_PROMPT}{self.prompt}{self.AFTER_PROMPT}"

    def script_body(self) -> str:
        before_prompt = shlex.quote(self.execution_prompt)
        before_output = shlex.quote(self.BEFORE_OUTPUT)
        after_output = shlex.quote(self.AFTER_OUTPUT)

        return "\n".join(
            (
                "# Generated by iterm2-api-wrapper. Safe to delete.",
                "emulate -L zsh",
                "setopt local_traps",
                "local __iterm_status=0",
                f"printf {before_prompt}",
                f"printf '%s\\n' {self.execution_label}",
                f"printf {before_output}",
                "{",
                self.command,
                "} always {",
                "__iterm_status=$?",
                f'printf {after_output} "$__iterm_status"',
                "}",
                'return "$__iterm_status"',
                "",
            )
        )

    def __str__(self) -> str:
        return self.script_body()


def write_marked_command_script(marked: MarkedCommand) -> Path:
    """Write a marked command script to a local temp file."""
    script_dir = Path(tempfile.gettempdir())
    script_path = script_dir / f"iterm2_marked_{os.getpid()}_{id(marked)}.zsh"
    script_path.write_text(marked.script_body(), encoding="utf-8")
    script_path.chmod(0o600)
    return script_path


def remove_marked_command_script(script_path: Path | None) -> None:
    """Best-effort cleanup for a generated marked command script."""
    if script_path is None:
        return

    try:
        script_path.unlink(missing_ok=True)
    except OSError:
        log.debug("Failed to remove marked command script", {"script_path": str(script_path)})


@dataclass
class iTermState:
    """Global iTerm2 state."""

    connection: Connection
    app: App
    window: Window
    tab: Tab
    session: Session
    profile: Profile | PartialProfile

    is_hotkey_window: bool = False

    # Accessors to avoid further imports
    SESSION_VAR: ClassVar[type[SessionVarEnum]] = SessionVarEnum
    """Enum class :class:`SessionVar` for type-hinted :class:`~iterm2.Session` variable options. Use for :meth:`~iTermState.get_variable` methods"""
    GLOBAL_VAR: ClassVar[type[AppVarEnum]] = AppVarEnum
    """Enum class :class:`GlobalVar` for type-hinted global variable options. Use for :meth:`~iTermState.get_variable` methods"""
    TAB_VAR: ClassVar[type[TabVarEnum]] = TabVarEnum
    """Enum class :class:`TabVar` for type-hinted :class:`~iterm2.Tab` variable options. Use for :meth:`~iTermState.get_variable` methods"""
    WINDOW_VAR: ClassVar[type[WindowVarEnum]] = WindowVarEnum
    """Enum class :class:`WindowVar` for type-hinted :class:`~iterm2.Window` variable options. Use for the :meth:`~iTermState.get_variable` method."""
    HEX: ClassVar[type[HexCodeEnum]] = HexCodeEnum
    """Enum class :class:`HexCode` for type-hinted hex codes to use with :meth:`~iTermState.send_escape_sequence`."""

    # TODO: Implement Command Event Signaling?
    class CommandEvent:
        idle: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
        running: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
        cancelled: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    # refresh_callback and _event_loop are set in client.py after initialization
    _refresh_callback: Callable[[], Awaitable[iTermState]] | Awaitable[iTermState] | None = field(
        default=None, init=False, repr=False
    )
    _event_loop: asyncio.AbstractEventLoop | None = field(default=None, init=False, repr=False)
    _loop_manager: LoopManager | None = field(default=None, init=False, repr=False)

    # One lock per instance
    _run_command_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    # Shell integration constants
    SI_DEAD_RECHECK_SECONDS: ClassVar[float] = 60.0
    SI_PROBE_TIMEOUT: ClassVar[float] = 1.5
    _si_live_cache: dict[str, tuple[bool, float]] = field(default_factory=dict, init=False, repr=False)

    # --------------------------------------------------
    # Validation Helpers
    # --------------------------------------------------

    def refresh_from(self, new_state: iTermState) -> None:
        """
        Refresh this state in-place from another state instance.

        `iTermClient` uses this to preserve the identity of `client.state` while
        still updating all underlying iTerm2 objects after a reconnect.
        """
        if not isinstance(new_state, iTermState):
            raise TypeError(f"refresh_from expects an iTermState; got {type(new_state).__name__!r}")

        existing_loop = self.loop_manager.loop
        new_loop = (
            LoopManager._usable_loop(new_state._event_loop)
            or LoopManager._usable_loop(new_state.connection.loop)
            or existing_loop
        )

        self.connection = new_state.connection
        self.app = new_state.app
        self.window = new_state.window
        self.tab = new_state.tab
        self.session = new_state.session
        self.profile = new_state.profile
        self.is_hotkey_window = new_state.is_hotkey_window
        self._refresh_callback = new_state._refresh_callback
        self._event_loop = new_loop
        self._loop_manager = None

        if new_loop is not None:
            self.connection.loop = new_loop

    async def ensure_state(
        self, refresh_callback: Callable[[], Awaitable[iTermState]] | Awaitable[iTermState] | None = None
    ) -> None:
        """Ensure the state is valid, refreshing if needed."""
        if await self.validated_state():
            return

        callback = refresh_callback or self._refresh_callback
        if callback is None:
            raise RuntimeError("No refresh callback provided to ensure_state")

        new_state: iTermState
        if inspect.iscoroutine(callback) or isinstance(callback, Awaitable):
            new_state = await cast(Awaitable[iTermState], callback)
        else:
            new_state = await callback()
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
            if not await self.online():
                return False

            # Check app still responds
            if (current_app := await async_get_app(self.connection, create_if_needed=False)) is None:
                return False
            self.app = current_app

            # Check session still exists
            if (new_session := current_app.get_session_by_id(self.session.session_id, include_buried=False)) is None:
                return False
            self.session = new_session

            # Refresh owning window/tab from the session
            new_window, new_tab = current_app.get_window_and_tab_for_session(new_session)
            if new_window is None or new_tab is None:
                return False
            self.window = new_window
            self.tab = new_tab

            return True
        except (ConnectionClosed, ConcurrencyError, RuntimeError) as e:
            errMsg = (
                f"The connection (iTermState.connection) is receiving or sending messages concurrently:\n{e!r}"
                if isinstance(e, ConcurrencyError)
                else f"The connection (iTermState.connection) is closed or has a runtime error: {e!r}"
            )
            log.error(
                f"The connection (iTermState.connection) is closed:\n{
                    json.dumps(
                        {
                            'code': e.code,
                            'rcvd': e.rcvd,
                            'sent': e.sent,
                            'rcvd_then_sent': e.rcvd_then_sent,
                            'reason': e.reason,
                        },
                        indent=4,
                    )
                }"
                if isinstance(e, ConnectionClosed)
                else errMsg
            )
            return False

    async def online(self, decode: bool = False) -> bool:
        """
        Check if the iTerm2 connection is online.

        This method performs a passive websocket health check.

        It intentionally avoids reading from the websocket because iTerm2 keeps a
        background dispatcher task running on the same connection. Calling
        ``recv()`` here races with that dispatcher and can spuriously raise
        ``ConcurrencyError`` even while the connection is healthy.

        ---

        :param decode: Whether to decode the received message, defaults to False
        :type decode: ``bool``, optional
        :raises ConnectionClosed: If the websocket connection is closed
        :raises ConcurrencyError: If there is a concurrency error
        :raises RuntimeError: If there is a runtime error
        :return: True if the connection is online, False otherwise
        :rtype: ``bool``
        """
        websocket = self.connection.websocket
        del decode

        # Also check if event loop is still usable
        loop = self.loop
        if loop is None or loop.is_closed() or not loop.is_running():
            log.warning("Event loop is not available or closed during connection check.")
            return False

        if websocket is None:
            log.warning("No websocket connection available on iTermState.")
            return False

        websocket_state = websocket.state
        websocket_state_name = websocket_state.name
        if websocket_state_name != "OPEN":
            log.warning(f"Websocket is not open during connection check: state={websocket_state_name}")
            return False

        close_code = websocket.close_code
        if close_code is not None:
            log.warning(f"Websocket has a close code during connection check: close_code={close_code}")
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
    def loop_manager(self) -> LoopManager:
        """Get the loop manager associated with this state.

        This property ensures that a :class:`LoopManager` instance is created if it doesn't already exist.

        ---

        :return: The loop manager associated with this state.
        :rtype: `LoopManager`
        """

        if self._loop_manager is None:
            self._loop_manager = LoopManager(self)
        return self._loop_manager

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """Get the event loop associated with this state.

        This is the loop that all iTerm2 API calls must run on.
        Prefers the explicitly set _event_loop, falling back to connection.loop.
        """
        return self.loop_manager.loop

    def _on_correct_loop(self) -> bool:
        """Check if the current context is running on the connection's event loop.

        Returns:
            True if currently on the connection's loop, False otherwise.
            Also returns False if there's no running loop or no connection loop.
        """
        return self.loop_manager._on_correct_loop()

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    @_validate_state
    async def on_state_loop[T](self, coro_factory: Coroutine[None, None, T]) -> T:
        return await coro_factory

    @overload
    async def get_session_var(self, name: Literal["*", SessionVarEnum.all]) -> dict[SessionVarKey, str]: ...
    @overload
    async def get_session_var(self, name: SessionVariable) -> str: ...
    async def get_session_var(self, name: SessionVariable) -> str | dict[SessionVarKey, str]:
        """Get a session variable."""
        ctx = "session" if not (len(parts := name.split(".")) >= 2 and parts[-2] == "user") else "user"
        return await self.get_variable(ctx=ctx, variable=name)

    @overload
    async def get_window_var(self, name: Literal["*", WindowVarEnum.all]) -> dict[WindowVarKey, str]: ...
    @overload
    async def get_window_var(self, name: WindowVariable) -> str: ...
    async def get_window_var(self, name: WindowVariable) -> str | dict[WindowVarKey, str]:
        """Get a window variable."""
        return await self.get_variable(ctx="window", variable=name)

    @overload
    async def get_tab_var(self, name: Literal["*", TabVarEnum.all]) -> dict[TabVarKey, str]: ...
    @overload
    async def get_tab_var(self, name: TabVariable) -> str: ...
    async def get_tab_var(self, name: TabVariable) -> str | dict[TabVarKey, str]:
        """Get a tab variable."""
        return await self.get_variable(ctx="tab", variable=name)

    @overload
    async def get_global_var(self, name: Literal["*", AppVarEnum.all]) -> dict[AppVarKey, str]: ...
    @overload
    async def get_global_var(self, name: AppVariable) -> str: ...
    async def get_global_var(self, name: AppVariable) -> str | dict[AppVarKey, str]:
        """Get a global variable."""
        return await self.get_variable(ctx="iterm2", variable=name)

    @overload
    async def get_user_var(self, name: Literal["*", UserVarEnum.all]) -> dict[UserVarKey, str]: ...
    @overload
    async def get_user_var(self, name: UserVariable) -> str: ...
    async def get_user_var(self, name: str) -> str | dict[UserVarKey, str]:
        """Get a user variable."""
        return await self.get_variable(ctx="user", variable=name)

    @overload
    @_validate_state
    async def get_variable(
        self,
        ctx: VariableScope,
        variable: Literal["*", AppVarEnum.all, WindowVarEnum.all, TabVarEnum.all, SessionVarEnum.all, UserVarEnum.all],
    ) -> dict[str, str]: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: SessionScope, variable: SessionVariable) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: TabScope, variable: TabVariable) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: WindowScope, variable: WindowVariable) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: AppScope, variable: AppVariable) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: UserScope, variable: UserVariable) -> str: ...
    @_validate_state
    async def get_variable(self, ctx: VariableScope, variable: Variable) -> str | dict[str, str]:
        """Get a variable from the specified context."""

        target: Tab | Window | Session | App | User
        match ctx:
            case "session":
                target = self.session
            case "tab":
                target = self.tab
            case "window":
                target = self.window
            case "iterm2":
                target = self.app
            case "user":
                target = User(self)
            case _:
                raise ValueError(f"Invalid context: {ctx!r}")

        log.debug(
            f"Getting variable: {f'{ctx}.{variable}' if not isinstance(target, User) else f'{target.display_name(variable)}'}"
        )
        result: str | dict[str, str] = await target.async_get_variable(variable)
        return result

    @_validate_state
    async def send_escape_sequence(
        self,
        *sequences: HexCode | str,
        broadcast: bool = False,
        timeout: float = 2.0,
        wait: bool = False,
    ) -> bool:
        """Send one or more escape/control sequences to the session.

        Each argument may be a :class:`HexCode` member, a `HexCode` member name,
        or a raw string. Member names are resolved to their underlying control bytes.

        Multiple arguments are concatenated in order, so
        ``send_escape_sequence(HexCode.ESC, "B")`` sends ``"\\x1bb"``.

        :param sequences: :class:`HexCode` members, member names, and/or raw strings.
        :type sequences: `tuple[HexCode | str, ...]`
        :param broadcast: If `False`, suppress broadcast to other sessions.
        :type broadcast: `bool`, optional, default=`False`
        :param timeout: Seconds to wait when ``wait=True``.
        :type timeout: `float`, optional
        :param wait: If `False`, return immediately after writing. If `True`,
            wait for a prompt/command event or terminal content change.
        :type wait: `bool`, optional, default=`False`

        :returns: `True` if written, or if a response/change was detected when waiting.
        :rtype: `bool`
        """
        if not sequences:
            raise ValueError("send_escape_sequence requires at least one sequence")

        payload = "".join(self.HEX.resolve(seq) for seq in sequences)
        suppress = not broadcast

        if wait is False:
            await self.session.async_send_text(payload, suppress_broadcast=suppress)
            return True

        async with PromptMonitor(
            self.connection,
            self.session.session_id,
            [PromptMonitor.Mode.PROMPT, PromptMonitor.Mode.COMMAND_START, PromptMonitor.Mode.COMMAND_END],
            snapshot_provider=self._get_terminal_snapshot,
        ) as monitor:
            before = monitor.initial_snapshot
            await self.session.async_send_text(payload, suppress_broadcast=suppress)

            try:
                event = await asyncio.wait_for(monitor.async_get(include_id=True), timeout=timeout)
                log.debug(f"Prompt/command event detected after sending escape sequence(s): {sequences}: {event}")
                return True
            except TimeoutError:
                after = await monitor.refresh_snapshot()
                if after != before:
                    log.debug(f"No prompt event after escape sequence(s), but terminal contents changed: {sequences}")
                    return True

                log.warning(f"Timed out waiting for terminal response after sending escape sequence(s): {sequences}")
                return False

    @_validate_state
    async def run_command(
        self,
        command: str,
        path: str | None = None,
        broadcast: bool = False,
        timeout: float = 10.0,
    ) -> CommandExecutionResult:
        """Run a command and return its output."""
        safe_command = command.replace("\n", "\\n").replace("\r", "\\r")
        suppress = not broadcast
        script_path: Path | None = None

        async with self._run_command_lock:
            current_path = await self.get_session_var("path")
            if path and current_path != path:
                await self._send_text(f"cd -- {shlex.quote(path)}", suppress=suppress)

            shell_integration_enabled = await self._shell_integration_enabled()
            log.debug(
                "✅ Shell integration enabled."
                if shell_integration_enabled is True
                else "⚠️ Shell integration disabled; using synthetic marked command script."
            )

            expected_command = safe_command
            initial_snapshot = await self._get_terminal_snapshot()
            initial_prompt = await self._get_prompt()
            initial_prompt_id = initial_prompt.unique_id if initial_prompt is not None else None

            try:
                if shell_integration_enabled is True:
                    send_cmd_task = self._send_text(safe_command, suppress=suppress)
                else:
                    marked = MarkedCommand(safe_command, command_label=safe_command)
                    script_path = write_marked_command_script(marked)
                    source_command = f"source {shlex.quote(str(script_path))}"
                    send_cmd_task = self._send_text(source_command, suppress=suppress)

                result = await self._wait_for_prompt(
                    send_cmd_task,
                    timeout=timeout,
                    expected_command=expected_command,
                    initial_prompt_id=initial_prompt_id,
                )
                if result.timed_out:
                    log.warning(
                        "Command monitor timed out; preserving shell-integration cache because "
                        "a command timeout is not proof that shell integration is dead."
                    )

                content: str | None = None

                if result.prompt_id is not None:
                    log.debug(f"Prompt ID was retrieved normally: {result.prompt_id}")
                    content = await self._get_prompt_output(result.prompt_id, expected_command=expected_command)

                if content is None:
                    log.warning("Content == None. Trying another method...")
                    content = "\n".join(changed_slice(initial_snapshot, await self._get_terminal_snapshot()))

                return CommandExecutionResult(output=content, status=result)
            finally:
                remove_marked_command_script(script_path)

    # --------------------------------------------------
    # Shell-Integration-Related Helpers
    # --------------------------------------------------

    async def _get_prompt(self, unique_id: str | None = None) -> Prompt | None:
        """Get prompt history from the session."""
        prompt_obj: Callable[..., Coroutine[Any, Any, Prompt | None]]
        call_args: dict[str, Any] = {"connection": self.connection, "session_id": self.session.session_id}
        if unique_id:
            prompt_obj = async_get_prompt_by_id
            call_args["prompt_unique_id"] = unique_id
        else:
            prompt_obj = async_get_last_prompt

        last_prompt: Prompt | None = await prompt_obj(**call_args)
        return last_prompt

    async def _wait_for_prompt(
        self,
        coro: Awaitable[None],
        *,
        timeout: float = 30.0,
        expected_command: str | None = None,
        initial_prompt_id: str | None = None,
    ) -> CommandExecutionStatus:
        """Wait for shell-integration prompt events for a command."""
        Mode = PromptMonitor.Mode
        modes = [Mode.COMMAND_START, Mode.COMMAND_END, Mode.PROMPT]

        log.debug(
            "Command monitor initialized",
            {
                "session_id": self.session.session_id,
                "timeout": timeout,
                "expected_command": expected_command,
                "initial_prompt_id": initial_prompt_id,
            },
        )

        async with PromptMonitor(
            self.connection, self.session.session_id, modes, snapshot_provider=self._get_terminal_snapshot
        ) as monitor:
            last_snapshot = monitor.initial_snapshot
            saw_expected_start = expected_command is None
            active_prompt_id: str | None = None
            active_command: str | None = None

            await coro

            while True:
                try:
                    event = await asyncio.wait_for(monitor.async_get(include_id=True), timeout=timeout)
                except TimeoutError:
                    current_snapshot = await monitor.refresh_snapshot()
                    if last_snapshot != current_snapshot:
                        log.debug("Prompt event timed out, but terminal contents changed; continuing wait")
                        last_snapshot = current_snapshot
                        continue

                    log.warning(
                        "Timed out waiting for shell-integration prompt event",
                        {
                            "expected_command": expected_command,
                            "saw_expected_start": saw_expected_start,
                            "active_command": active_command,
                            "active_prompt_id": active_prompt_id,
                            "initial_prompt_id": initial_prompt_id,
                        },
                    )
                    return CommandExecutionStatus(
                        prompt_id=active_prompt_id,
                        command=active_command,
                        exit_code=CommandExecutionStatus.ExitCode.GENERAL_FAILURE,
                        timed_out=True,
                    )

                if event[0] == Mode.PROMPT:
                    prompt_obj = event[1]
                    prompt_id = event[2]
                    active_prompt_id = prompt_id or (prompt_obj.unique_id if prompt_obj is not None else None)
                    log.debug("PROMPT DETECTED: ", {"mode": event[0], "prompt_id": active_prompt_id})
                    continue

                if event[0] == Mode.COMMAND_START:
                    command = event[1]
                    prompt_id = event[2]

                    if expected_command is not None and command.strip() != expected_command.strip():
                        log.debug("Ignoring foreign COMMAND_START (initial text / leftover)", {"command": command})
                        continue

                    saw_expected_start = True
                    active_command = command
                    active_prompt_id = prompt_id or active_prompt_id or initial_prompt_id
                    log.debug("COMMAND STARTED: ", {"mode": event[0], "command": active_command})
                    continue

                if event[0] == Mode.COMMAND_END:
                    raw_exit_code = event[1]
                    event_prompt_id = event[2]
                    prompt_id_is_reliable = saw_expected_start

                    if not saw_expected_start:
                        if expected_command is None:
                            log.debug(
                                "Ignoring COMMAND_END preceding matching COMMAND_START",
                                {
                                    "event_prompt_id": event_prompt_id,
                                    "initial_prompt_id": initial_prompt_id,
                                    "expected_command": expected_command,
                                    "active_command": active_command,
                                    "active_prompt_id": active_prompt_id,
                                },
                            )
                            continue

                        current_snapshot = await monitor.refresh_snapshot()
                        if current_snapshot == last_snapshot:
                            log.debug(
                                "Ignoring COMMAND_END without COMMAND_START and without terminal changes",
                                {
                                    "event_prompt_id": event_prompt_id,
                                    "initial_prompt_id": initial_prompt_id,
                                    "expected_command": expected_command,
                                },
                            )
                            continue

                        last_snapshot = current_snapshot
                        saw_expected_start = True
                        active_command = expected_command
                        active_prompt_id = None
                        prompt_id_is_reliable = False
                        log.debug(
                            "Accepting COMMAND_END without COMMAND_START; prompt id is not reliable, using snapshot fallback",
                            {
                                "event_prompt_id": event_prompt_id,
                                "initial_prompt_id": initial_prompt_id,
                                "expected_command": expected_command,
                            },
                        )

                    exit_code = CommandExecutionStatus.ExitCode.coerce(raw_exit_code)
                    prompt_id = active_prompt_id or event_prompt_id or initial_prompt_id
                    if not prompt_id_is_reliable:
                        prompt_id = None

                    log.debug(
                        "COMMAND FINISHED:",
                        {"mode": event[0].value, "raw_exit_code": raw_exit_code, "known_exit_code": exit_code},
                    )

                    return CommandExecutionStatus(prompt_id=prompt_id, command=active_command, exit_code=exit_code)

    async def _get_prompt_output(
        self, prompt_id: str, *, expected_command: str | None = None, extract_prompt_text: bool = False
    ) -> str | None:
        """Return command output for a prompt id, or None when the prompt is not usable."""
        updated_prompt = await self._get_prompt(prompt_id)
        if updated_prompt is None:
            log.error(":error: Unable to get updated prompt; raising RuntimeError.", emoji=True)
            raise RuntimeError("Failed to retrieve prompt after command execution.")

        # fmt: off
        log.debug(
            "OUPUT RANGE:", updated_prompt.output_range.proto,
            "\nCOMMAND RANGE:", updated_prompt.command_range.proto,
            "\nEXCLUDED SUBRANGES:", updated_prompt.excluded_subranges,
            "\nPROMPT RANGE:", updated_prompt.prompt_range.proto,
            "\nCOMMAND:", updated_prompt.command,
            sep="\n",
        )
        # fmt: on

        if expected_command is not None:
            prompt_command = str(updated_prompt.command or "").strip()
            if prompt_command != expected_command.strip():
                log.debug(
                    "Prompt output rejected because prompt command does not match expected command",
                    {"prompt_command": prompt_command, "expected_command": expected_command},
                )
                return None

        output_range = updated_prompt.output_range
        start, end = output_range.start, output_range.end
        start_x, start_y = start.x, start.y
        end_x, end_y = end.x if extract_prompt_text is True else None, end.y

        if (start_x, start_y) == (end_x, end_y):
            log.debug("Prompt output range is empty; falling back to snapshot diff")
            return None

        if end_y < start_y or (end_y == start_y and (isinstance(end_x, int) and end_x < start_x)):
            log.debug(f"Invalid output range: {start_x=}, {start_y=}, {end_x=}, {end_y=}")
            return None

        # number_of_lines = max(1, (end_y - start_y) - 1)
        number_of_lines = max(1, end_y - start_y)
        # TODO: Handle prompt-cmd-line exclusion
        #   - assign prompt_line by calling this method recursively with extract_prompt_text=True if prompt_line is False
        #   - pop lines from the result until it does not include the prompt line
        #   - prompt extraction example:
        #       _start_y = updated_prompt.prompt_range.start.y
        #       _end_y = updated_prompt.prompt_range.end.y
        #       _start_x = updated_prompt.prompt_range.start.x
        #       _end_x = updated_prompt.prompt_range.end.x
        #       _number_of_lines = max(1, _end_y - _start_y)
        #       _contents = await self.session.async_get_contents(_start_y, _number_of_lines)
        #       _result = "\n".join(line.string for line in _contents)[_start_x:_end_x].strip()

        async with Transaction(self.connection):
            contents = await self.session.async_get_contents(start_y, number_of_lines)

        result = "\n".join(line.string for line in contents)[start_x:end_x].strip()
        if not result:
            return None

        return result

    async def _shell_integration_enabled(self, allow_autoload: bool = True) -> bool:
        """Return True when prompt-monitor output extraction is usable now."""
        sid = self.session.session_id
        loop = self.loop or asyncio.get_running_loop()

        if (cached := self._si_live_cache.get(sid)) is not None:
            live, checked_at = cached
            if live or (loop.time() - checked_at) < self.SI_DEAD_RECHECK_SECONDS:
                return live

        def cache(live: bool) -> bool:
            self._si_live_cache[sid] = (live, loop.time())
            return live

        last_prompt = await self._get_prompt()

        if last_prompt is None:
            auto_load = self.profile.all_properties.get("Load Shell Integration Automatically", 0)
            if allow_autoload and bool(auto_load):
                return cache(await self._ask_load_shell_integration())
            return cache(False)

        last_command = await self.session.async_get_variable("lastCommand")
        username = await self.session.async_get_variable("username")
        hostname = await self.session.async_get_variable("hostname")

        prompt_state = getattr(last_prompt, "state", None)
        prompt_ready = prompt_state in {prompt.PromptState.EDITING, prompt.PromptState.UNKNOWN}
        has_identity = _has_session_value(username) and _has_session_value(hostname)

        if prompt_ready and has_identity:
            log.debug(
                "Shell integration prompt evidence accepted",
                {
                    "prompt_state": prompt_state,
                    "lastCommand": last_command,
                    "username": username,
                    "hostname": hostname,
                },
            )
            return cache(True)

        strict_snapshot = await self._get_terminal_snapshot(filter_all_empty=True)
        if strict_snapshot and not has_identity:
            log.debug(
                "Shell integration prompt evidence rejected: identity variables are missing",
                {
                    "prompt_state": prompt_state,
                    "lastCommand": last_command,
                    "username": username,
                    "hostname": hostname,
                    "line_count": len(strict_snapshot),
                },
            )
            return cache(False)

        job = await self.session.async_get_variable("jobName")
        shell = await self.session.async_get_variable("shell")

        if job and shell and job != Path(str(shell)).name:
            log.debug(
                "Shell integration prompt exists, but foreground job is not the shell", {"job": job, "shell": shell}
            )
            return cache(False)

        return cache(await self._probe_shell_integration_live())

    async def _probe_shell_integration_live(self, timeout: float | None = None) -> bool:
        async with PromptMonitor(self.connection, self.session.session_id) as monitor:
            await self.session.async_send_text("\r", suppress_broadcast=True)
            try:
                await asyncio.wait_for(
                    monitor.async_get(mode=PromptMonitor.Mode.PROMPT), timeout or self.SI_PROBE_TIMEOUT
                )
            except TimeoutError:
                return False
            return True

    async def _ask_load_shell_integration(self, path: str | None = None, skip_confirm: bool = False) -> bool:
        user_shell = await self.get_session_var("shell")
        si_path = Path(path or DEFAULT_SHELL_INTEGRATION_PATH.format(shell=user_shell))
        load_si_prompt_response = poly_modal_alert_handler(
            connection=self.connection,
            title="Load Shell Integration Confirmation",
            subtitle="Automatic shell integration loading is enabled, but it doesn't seem to be initialized yet "
            "(prompt retrieval capabilities are unavailable).\nWould you like to load shell integration now?\n",
            window_id=self.window.window_id,
            button_names=["Yes", "No"],
            text_fields=(["/path/to/.iterm2_shell_integration.{zsh,bash,fish}"], [str(si_path)]),
        )
        should_load_shell_integration: bool = skip_confirm is True

        if skip_confirm is False:
            load_si_prompt_response = await load_si_prompt_response
            should_load_shell_integration = str(load_si_prompt_response.button).lower() == "yes"
            si_path = Path(load_si_prompt_response.tf_text or si_path).expanduser().resolve()

        log.debug(f"{should_load_shell_integration=}")

        if should_load_shell_integration:
            if si_path.exists():
                log.debug(f"Loading shell integration at: {si_path!s}")
                send_cmd_coro = self.session.async_send_text(
                    f"source {shlex.quote(str(si_path))}\r", suppress_broadcast=True
                )
                si_load_output = await self._wait_for_prompt(send_cmd_coro)
                log.debug(
                    "Shell integration loaded with output:",
                    await self._get_prompt_output(f"{si_load_output.prompt_id}"),
                )
                return await self._shell_integration_enabled(allow_autoload=False)

            log.warning(f"Unknown shell integration file - '{si_path!s}' does not exist.")

        return False

    # --------------------------------------------------
    # ! NON-Shell-Integration-Related Helpers
    # --------------------------------------------------

    async def _send_text(
        self,
        command: str | MarkedCommand,
        suppress: bool,
        *,
        clear_line: bool = True,
    ) -> None:
        """Send a command line to the session."""
        text = str(command).removesuffix("\r")

        if clear_line is True:
            await self.session.async_send_text(str(self.HEX.CNTRL_U), suppress_broadcast=suppress)
            await asyncio.sleep(0.02)

        await self.session.async_send_text(text + "\r", suppress_broadcast=suppress)

    async def _get_terminal_snapshot(self, *, trim_end: bool = True, filter_all_empty: bool = False) -> list[str]:
        """Get a transactionally consistent snapshot of the terminal screen contents."""
        async with Transaction(self.connection):
            line_info = await self.session.async_get_line_info()
            start = line_info.overflow
            total_lines = line_info.scrollback_buffer_height + line_info.mutable_area_height
            contents = await self.session.async_get_contents(first_line=start, number_of_lines=total_lines)

        if trim_end:
            while contents and not contents[-1].string.strip():
                contents.pop()

        return [
            line.string
            for line in contents
            if (filter_all_empty is True and line.string.strip()) or (filter_all_empty is False)
        ]

    def asdict(self) -> dict[str, Any]:
        """Convert iTermState to dictionary."""
        return {
            key: {k: v for k, v in value.__dict__.items()} if hasattr(value, "__dict__") else value
            for key, value in self.__dict__.items()
            if not key.startswith("_")
        }
