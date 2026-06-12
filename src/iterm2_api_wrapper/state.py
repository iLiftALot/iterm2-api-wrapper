from __future__ import annotations

import asyncio
import inspect
import json
import re
import shlex
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Concatenate, Literal, cast, overload

from websockets import ConcurrencyError, ConnectionClosed

from ._logging import PrettyLog
from .alert import poly_modal_alert_handler
from .api.it2app import async_get_app
from .api.it2prompt import PromptMonitor, async_get_last_prompt, async_get_prompt_by_id, prompt
from .api.it2transaction import Transaction
from .api.it2variable import AppVarEnum, SessionVarEnum, TabVarEnum, UserVarEnum, WindowVarEnum
from .typings import CommandStatus, HexCodeEnum


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
DEFAULT_SHELL_INTEGRATION_PATH = f"{Path.home()}/.iterm2_shell_integration.{{shell}}"


def last_nonempty_line(lines: list[str]) -> str | None:
    """Return the last non-empty terminal line, trimmed."""
    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            return stripped
    return None


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


def prompt_preamble_line_count(lines: list[str], prompt_line: str) -> int:
    """Count non-empty prompt preamble lines immediately before the prompt line."""
    if not prompt_line:
        return 0

    prompt_index: int | None = None
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip() == prompt_line:
            prompt_index = index
            break

    if prompt_index is None:
        return 0

    count = 0
    index = prompt_index - 1
    while index >= 0 and lines[index].strip():
        count += 1
        index -= 1

    return count


def looks_like_prompt_preamble(line: str) -> bool:
    """Best-effort detection for path/time prompt preamble lines."""
    stripped = line.strip()
    if not stripped.startswith(("~/", "/")):
        return False

    return bool(re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", stripped))


def extract_output_from_changed_block(
    changed: list[str], *, prompt_line: str, command: str, prompt_preamble_lines: int = 0
) -> str:
    """Trim command echo and prompt lines from a terminal snapshot diff."""
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

    while block:
        while block and not block[0].strip():
            block = block[1:]

        if not block:
            break

        first = block[0].strip()
        if command_norm and (first == command_norm or (first.endswith(command_norm) and prompt_norm in first)):
            block = block[1:]
            continue

        if (
            command_norm
            and len(block) >= 2
            and looks_like_prompt_preamble(block[0])
            and block[1].strip().endswith(command_norm)
            and prompt_norm in block[1]
        ):
            block = block[2:]
            continue

        break

    while block and not block[-1].strip():
        block.pop()
    if block and prompt_norm and block[-1].strip() == prompt_norm:
        block.pop()
        for _ in range(prompt_preamble_lines):
            if block:
                block.pop()

        if prompt_preamble_lines == 0 and block and len(prompt_norm) <= 4 and "\n" in block[-1]:
            block.pop()

        while block and not block[-1].strip():
            block.pop()

    if prompt_norm and len(prompt_norm) <= 4 and block and "\n" in block[-1]:
        block.pop()

    if prompt_norm and len(prompt_norm) <= 4 and block and looks_like_prompt_preamble(block[-1]):
        block.pop()

    while block and not block[-1].strip():
        block.pop()

    return "\n".join(line.rstrip("\n") for line in block).strip()


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

    # Variable accessors to avoid further imports
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
    async def send_escape_sequence(self, *sequences: HexCode | str, broadcast: bool = False) -> None:
        """
        Send one or more escape/control sequences to the session.

        Each argument may be a ``HexCode`` member (e.g. ``HexCode.CNTRL_C``),
        a ``HexCode`` member *name* (e.g. ``"CNTRL_C"`` or ``"ESC"``), or a raw
        string. Member names are resolved to their underlying control bytes.
        Multiple arguments are concatenated in order, so
        ``send_escape_sequence(HexCode.ESC, "B")`` sends ``"\\x1bb"``.

        :param sequences: HexCode members, member names, and/or raw strings.
        :param broadcast: If False (default), suppress broadcast to other
            sessions; if True, allow it.
        """
        if not sequences:
            raise ValueError("send_escape_sequence requires at least one sequence")

        def _resolve(seq: HexCode | str) -> HexCode | str:
            if isinstance(seq, HexCodeEnum):
                return str(seq)

            # Resolve a HexCode member name (including aliases) to its bytes.
            member = HexCodeEnum.__members__.get(seq)
            return str(member) if member is not None else seq

        payload = "".join(_resolve(seq) for seq in sequences)
        await self.session.async_send_text(payload, suppress_broadcast=not broadcast)

    @_validate_state
    async def run_command(
        self, command: str, path: str | None = None, broadcast: bool = False, timeout: float = 10.0
    ) -> str:
        """Run a command and return its output"""
        suppress = not broadcast

        async with self._run_command_lock:
            current_path = await self.get_session_var("path")
            if path and current_path != path:
                await self.session.async_send_text(f"cd -- {shlex.quote(path)}\r", suppress_broadcast=suppress)

            shell_integration_enabled = await self._shell_integration_enabled()
            if not shell_integration_enabled:
                return await self._run_command_without_shell_integration(
                    command=command, suppress_broadcast=suppress, timeout=timeout
                )

            log.debug("Shell integration enabled.")

            initial_snapshot, _ = await self._get_prompt_candidate(suppress_broadcast=suppress)
            send_cmd_task = self.session.async_send_text(command + "\r", suppress_broadcast=suppress)
            result = await self._wait_for_prompt(send_cmd_task, timeout=timeout, expected_command=command)
            if result.timed_out:
                log.warning("Command timed out...")
                self._si_live_cache[self.session.session_id] = (False, (self.loop or asyncio.get_running_loop()).time())
            if result.prompt_id is not None:
                log.debug(f"Prompt ID was retrieved normally: {result.prompt_id}")
                content = await self._get_prompt_output(result.prompt_id)
            else:
                log.warning("Prompt ID came back as None. Trying another method...")
                content = await self._wait_for_prompt_reappearance_from_snapshot(
                    initial_snapshot, command=command, timeout=timeout
                )

            return content

    @_validate_state
    async def shell_integration_status(self) -> Literal["absent", "active", "busy", "stale", "legacy"]:
        """
        Classify shell-integration state from iTerm2's own per-session evidence.

        Prompt records are created exclusively by the integration's OSC 133/1337
        marks, so they are the only API-visible ground truth:
        - absent: no marks ever seen in this session -> not loaded
        - active: at a live, integration-tracked prompt right now
        - busy:   marks exist; a command is genuinely in flight
        - stale:  marks exist but foreground job is the shell itself
                    (`exec zsh`, or ssh'd somewhere without integration)
        - legacy: iTerm2 too old to report prompt state; marks exist
        """
        last_prompt = await self._get_prompt()
        if last_prompt is None:
            return "absent"

        state = last_prompt.state
        if state == prompt.PromptState.EDITING:
            return "active"

        if state == prompt.PromptState.UNKNOWN:
            return "legacy"

        # RUNNING / FINISHED: real foreground command vs stale marks.
        job = await self.get_session_var("jobName")
        shell = await self.get_session_var("shell")
        if job and shell and job == Path(str(shell)).name:
            return "stale"

        return "busy"

    # --------------------------------------------------
    # Shell-Integration-Related Helpers
    # --------------------------------------------------

    async def _get_prompt(self, unique_id: str | None = None) -> None | Prompt:
        """Get prompt history from the session."""
        prompt_obj: Callable[..., Coroutine[Any, Any, None | Prompt]]
        call_args: dict[str, Any] = {"connection": self.connection, "session_id": self.session.session_id}
        if unique_id:
            prompt_obj = async_get_prompt_by_id
            call_args["prompt_unique_id"] = unique_id
        else:
            prompt_obj = async_get_last_prompt

        last_prompt: None | Prompt = await prompt_obj(**call_args)
        return last_prompt

    async def _wait_for_prompt(
        self, coro: Awaitable[None], *, timeout: float = 30.0, expected_command: str | None = None
    ) -> CommandStatus:
        """Wait for shell-integration prompt events for a command."""
        ModeFactory = PromptMonitor.Mode
        modes = [ModeFactory.COMMAND_START, ModeFactory.COMMAND_END, ModeFactory.PROMPT]

        log.debug("Command monitor initialized", {"session_id": self.session.session_id, "timeout": timeout})

        async with PromptMonitor(self.connection, self.session.session_id, modes) as monitor:
            saw_expected_start = expected_command is None
            active_prompt_id: str | None = None
            active_command: str | None = None
            await coro
            loop = self.loop or asyncio.get_running_loop()
            poll_timeout = min(0.25, max(0.1, timeout))
            last_activity = loop.time()
            monitor_task = asyncio.create_task(monitor.async_get(include_id=True))

            try:
                while True:
                    done, _ = await asyncio.wait({monitor_task}, timeout=poll_timeout)
                    if monitor_task not in done:
                        if loop.time() - last_activity >= timeout:
                            status = CommandStatus(
                                prompt_id=None,
                                command=active_command,
                                exit_code=CommandStatus.ExitCode.GENERAL_FAILURE,
                                timed_out=True,
                            )
                            break

                        continue

                    event = monitor_task.result()
                    monitor_task = asyncio.create_task(monitor.async_get(include_id=True))
                    last_activity = loop.time()

                    if event[0] == ModeFactory.PROMPT:
                        prompt = event[1]
                        prompt_id = event[2]
                        active_prompt_id = prompt_id or (prompt.unique_id if prompt is not None else None)
                        log.debug("PROMPT DETECTED: ", {"mode": event[0], "prompt_id": active_prompt_id})
                        continue
                    if event[0] == ModeFactory.COMMAND_START:
                        command = event[1]
                        prompt_id = event[2]
                        if expected_command is not None and command.strip() != expected_command.strip():
                            log.debug("Ignoring foreign COMMAND_START (initial text / leftover)", {"command": command})
                            continue
                        saw_expected_start = True
                        active_command = command
                        active_prompt_id = prompt_id or active_prompt_id
                        log.debug("COMMAND STARTED: ", {"mode": event[0], "command": active_command})
                        continue
                    if event[0] == ModeFactory.COMMAND_END:
                        if not saw_expected_start:
                            log.debug("Ignoring COMMAND_END preceding our COMMAND_START (initial text / leftover)")
                            continue
                        raw_exit_code = event[1]
                        exit_code = CommandStatus.ExitCode.coerce(raw_exit_code)
                        prompt_id = event[2] or active_prompt_id
                        log.debug(
                            "COMMAND FINISHED:",
                            {"mode": event[0], "exit_code": raw_exit_code, "known_exit_code": exit_code},
                        )
                        status = CommandStatus(prompt_id=prompt_id, command=active_command, exit_code=exit_code)
                        break
            finally:
                if not monitor_task.done():
                    monitor_task.cancel()
                    try:
                        await monitor_task
                    except asyncio.CancelledError:
                        pass

        return status

    async def _get_prompt_output(self, prompt_id: str) -> str:
        """Returns a string with the content in a range of lines."""
        updated_prompt = await self._get_prompt(prompt_id)
        if updated_prompt is None:
            log.error(":error: Unable to get updated prompt; raising RuntimeError.", emoji=True)
            raise RuntimeError("Failed to retrieve prompt after command execution.")

        no_output_message = "<no output>"

        output_range = updated_prompt.output_range
        start_y = output_range.start.y
        end_y = output_range.end.y

        if start_y == 0 and end_y == 0:
            cmd_range = updated_prompt.command_range
            start_y = cmd_range.start.y + 1
            end_y = cmd_range.end.y + 1

        if end_y < start_y:
            return no_output_message

        async with Transaction(self.connection):
            contents = await self.session.async_get_contents(start_y, max(1, end_y - start_y))

        result = "\n".join(line.string for line in contents).strip()

        if not result:
            return no_output_message

        return result

    async def _shell_integration_enabled(self, allow_autoload: bool = True) -> bool:
        """True only for *verified-live* shell integration.

        Mark presence is necessary but NOT sufficient: iTerm2 persists marks
        (and their prompt state) through arrangement/session restore, so a
        dead session can carry another shell's marks. The only currency proof
        is minting a fresh mark, so unverified sessions get one bounded CR
        probe; the verdict is cached per session id. Live verdicts persist
        (flipped by run_command on prompt-path timeout); dead verdicts expire
        after SI_DEAD_RECHECK_SECONDS so late-loaded integration is found.
        """
        sid = self.session.session_id
        loop = self.loop or asyncio.get_running_loop()

        if (cached := self._si_live_cache.get(sid)) is not None:
            live, checked_at = cached
            if live or (loop.time() - checked_at) < self.SI_DEAD_RECHECK_SECONDS:
                return live

        if await self._get_prompt() is None:
            # No marks at all (restore would have carried them over):
            # integration has never spoken here. Offer auto-load if configured.
            auto_load: Literal[0, 1] = self.profile.all_properties.get("Load Shell Integration Automatically", 0)
            live = allow_autoload and bool(auto_load) and await self.maybe_load_shell_integration()
        else:
            live = await self._probe_shell_integration_live()

        self._si_live_cache[sid] = (live, loop.time())
        return live

    async def _probe_shell_integration_live(self, timeout: float | None = None) -> bool:
        """Ground truth: a bare CR at an idle prompt must mint a fresh PROMPT
        mark. Restored/stale marks cannot pass this; only a live precmd hook
        can. Refuses to probe when the foreground job is not the shell (the CR
        would feed a running program's stdin) and reports not-live — which is
        the correct routing decision for that moment anyway.
        """
        job, shell = await self.get_session_var("jobName"), await self.get_session_var("shell")
        if not job or not shell or job != Path(str(shell)).name:
            log.debug("Skipping CR probe: foreground job is not the shell", {"job": job, "shell": shell})
            return False

        async with PromptMonitor(self.connection, self.session.session_id) as monitor:
            await self.session.async_send_text("\r", suppress_broadcast=True)
            try:
                await asyncio.wait_for(
                    monitor.async_get(mode=PromptMonitor.Mode.PROMPT), timeout or self.SI_PROBE_TIMEOUT
                )
            except TimeoutError:
                return False
            return True

    async def maybe_load_shell_integration(self, path: str | None = None, skip_confirm: bool = False) -> bool:
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

    async def _get_prompt_candidate(
        self, *, suppress_broadcast: bool, retries: int = 5, retry_delay: float = 0.1
    ) -> tuple[list[str], str]:
        """Get terminal snapshot plus the last non-empty prompt candidate line."""
        lines = await self._get_terminal_snapshot()
        prompt_line = last_nonempty_line(lines)

        attempts = 0
        while prompt_line is None and attempts < retries:
            await self.session.async_send_text("\r", suppress_broadcast=suppress_broadcast)
            await asyncio.sleep(retry_delay)
            lines = await self._get_terminal_snapshot()
            prompt_line = last_nonempty_line(lines)
            attempts += 1

        if prompt_line is None:
            raise RuntimeError("Unable to identify prompt line in terminal contents for fallback execution.")

        return lines, prompt_line

    async def _run_command_without_shell_integration(
        self,
        starting_snapshot: list[str] | None = None,
        *,
        command: str,
        suppress_broadcast: bool,
        timeout: float = 10.0,
    ) -> str:
        """
        Run command without shell integration by snapshot-diff + prompt reappearance.
        """
        if starting_snapshot is None:
            starting_snapshot, prompt_line = await self._get_prompt_candidate(suppress_broadcast=suppress_broadcast)
        else:
            prompt_line = last_nonempty_line(starting_snapshot)
            if prompt_line is None:
                raise RuntimeError("Unable to identify prompt line in terminal contents for fallback execution.")

        log.debug(f"Fallback run start: line_count={len(starting_snapshot)}, prompt={prompt_line!r}")
        await self.session.async_send_text(command + "\r", suppress_broadcast=suppress_broadcast)

        return await self._wait_for_prompt_reappearance_from_snapshot(
            starting_snapshot, command=command, timeout=timeout
        )

    async def _wait_for_prompt_reappearance_from_snapshot(
        self, starting_snapshot: list[str], *, command: str, timeout: float = 10.0
    ) -> str:
        """Recover command output when shell-integration monitoring fails to return a prompt id."""
        prompt_line = last_nonempty_line(starting_snapshot)
        if prompt_line is None:
            raise RuntimeError(...)

        end_lines = await self._wait_for_terminal_snapshot_completion(
            starting_snapshot, prompt_line=prompt_line, timeout=timeout
        )

        changed = changed_slice(starting_snapshot, end_lines)
        output = extract_output_from_changed_block(changed, prompt_line=prompt_line, command=command)
        log.debug(f"Recovered command output from snapshot:\n- line_count={len(end_lines)}\n- output_len={len(output)}")
        return output or "<no output>"

    async def _wait_for_terminal_snapshot_completion(
        self, starting_snapshot: list[str], *, prompt_line: str, timeout: float
    ) -> list[str]:
        loop = self.loop or asyncio.get_running_loop()
        last_activity = loop.time()
        poll_interval = 0.1
        saw_change = False
        stable_prompt_polls = 0
        end_lines = starting_snapshot

        while True:
            end_lines = await self._get_terminal_snapshot()

            if not saw_change and end_lines != starting_snapshot:
                saw_change = True
                last_activity = loop.time()

            last_nonempty = last_nonempty_line(end_lines)
            if saw_change and last_nonempty == prompt_line:
                stable_prompt_polls += 1
                if stable_prompt_polls >= 2:
                    break
            elif saw_change and last_nonempty != prompt_line:
                last_activity = loop.time()
                stable_prompt_polls = 0
            else:
                stable_prompt_polls = 0

            if loop.time() - last_activity >= timeout:
                raise TimeoutError("Timeout waiting for command completion (shell integration disabled).")

            await asyncio.sleep(poll_interval)

        return end_lines

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
