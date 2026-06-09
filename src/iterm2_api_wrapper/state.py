from __future__ import annotations

import asyncio
import inspect
import json
import re
import shlex
from collections.abc import AsyncGenerator, Awaitable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable, ClassVar, Concatenate, Coroutine, Literal, cast, overload

from iterm2 import transaction
from websockets import ConcurrencyError, ConnectionClosed

from iterm2_api_wrapper._logging import PrettyLog
from iterm2_api_wrapper.alert import poly_modal_alert_handler


# fmt: off
from iterm2_api_wrapper.api.it2types import (  # isort: skip
    App, PartialProfile, Profile, Prompt, PromptMonitor, Session, Tab, Window,
    async_get_app, async_get_last_prompt, async_get_prompt_by_id,
)
from iterm2_api_wrapper.api.it2variable import (  # isort: skip
    UserVarEnum, UserVarKey, UserVariable, UserScope,
    SessionVarEnum, SessionVarKey, SessionVariable, SessionScope,
    AppVarEnum, AppVarKey, AppVariable, AppScope,
    TabVarEnum, TabVarKey, TabVariable, TabScope,
    WindowVarEnum, WindowVarKey, WindowVariable, WindowScope,
    Variable, VariableScope
)
# fmt: on


from iterm2_api_wrapper.connection import Connection
from iterm2_api_wrapper.typings import CommandStatus, HexCode, HexCodeEnum


log = PrettyLog.get_logger(__name__)
DEFAULT_SHELL_INTEGRATION_PATH = f"{Path.home()}/.iterm2_shell_integration.{{shell}}"


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
                    "Cancelled cross-loop call to %s: future.cancel() -> %s (done=%s cancelled=%s)",
                    method.__qualname__,
                    cancelled,
                    future.done(),
                    future.cancelled(),
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
            name = self.display_name(name)
            return await target.async_get_variable(name)

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
                send_cmd_coro = self.session.async_send_text(f"source {shlex.quote(str(si_path))}\r")
                si_load_output, _ = await self._wait_for_prompt(send_cmd_coro)
                log.debug(
                    "Shell integration loaded with output:",
                    await self._get_prompt_output(f"{si_load_output.prompt_id}"),
                )
                return await self._shell_integration_enabled()

            log.warning(f"Unknown shell integration file - '{si_path!s}' does not exist.")

        return False

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
                initial_snapshot = await self._get_terminal_snapshot()
                return await self._run_command_without_shell_integration(
                    initial_snapshot, command=command, suppress_broadcast=suppress
                )

            log.debug("Shell integration enabled.")

            send_cmd_task = asyncio.create_task(
                self.session.async_send_text(command + "\r", suppress_broadcast=suppress)
            )
            result, initial_snapshot = await self._wait_for_prompt(send_cmd_task, timeout=timeout)
            content = await self._get_prompt_output(result.prompt_id or initial_snapshot)
            return content

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
        self, coro: Awaitable[None], *, timeout: float = 30.0
    ) -> tuple[CommandStatus, list[str]]:
        """Block until the running command terminates. Returns string if command ended, None on timeout."""
        ModeFactory = PromptMonitor.Mode
        modes = [ModeFactory.COMMAND_START, ModeFactory.COMMAND_END, ModeFactory.PROMPT]
        initial_snapshot = await self._get_terminal_snapshot()
        log.debug(initial_snapshot, initial_snapshot[-1])

        async def _term_contents_updated() -> bool:
            new_snapshot = await self._get_terminal_snapshot()
            return initial_snapshot != new_snapshot

        async with PromptMonitor(self.connection, self.session.session_id, modes) as monitor:

            async def _internal(_timeout: float = timeout):
                active_prompt_id: str | None = None
                active_command: str | None = None

                while True:
                    try:
                        event = await asyncio.wait_for(monitor.async_get(include_id=True), timeout=timeout)
                        if event[0] == ModeFactory.PROMPT:
                            prompt = event[1]
                            prompt_id = event[2]
                            active_prompt_id = prompt_id or (prompt.unique_id if prompt is not None else None)
                            log.debug("PROMPT DETECTED: ", {"mode": event[0], "prompt_id": active_prompt_id})
                            continue
                        if event[0] == ModeFactory.COMMAND_START:
                            command = event[1]
                            prompt_id = event[2]
                            active_command = command
                            active_prompt_id = prompt_id or active_prompt_id
                            log.debug("COMMAND STARTED: ", {"mode": event[0], "command": active_command})
                            continue
                        if event[0] == ModeFactory.COMMAND_END:
                            raw_exit_code = event[1]
                            exit_code = CommandStatus.ExitCode.coerce(raw_exit_code)
                            prompt_id = event[2] or active_prompt_id
                            log.debug(
                                "COMMAND FINISHED:",
                                {"mode": event[0], "exit_code": raw_exit_code, "known_exit_code": exit_code},
                            )
                            return CommandStatus(prompt_id=prompt_id, command=active_command, exit_code=exit_code)
                    except TimeoutError:
                        if await _term_contents_updated():
                            log.debug("Timeout reached, however, the session contents are still updating. Retrying...")
                            continue
                        return CommandStatus(
                            prompt_id=None,
                            command=None,
                            exit_code=CommandStatus.ExitCode.GENERAL_FAILURE,
                            timed_out=True,
                        )

            _, status = await asyncio.gather(coro, _internal())
        return status, initial_snapshot

    async def _get_prompt_output(self, promptId_or_snapshot: str | list[str]) -> str:
        """Returns a string with the content in a range of lines."""
        if isinstance(promptId_or_snapshot, list):
            new_snapshot = await self._get_terminal_snapshot()
            start_line = len(promptId_or_snapshot)
            return "\n".join(new_snapshot[start_line:])

        updated_prompt = await self._get_prompt(promptId_or_snapshot)
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

        async with transaction.Transaction(self.connection):
            contents = await self.session.async_get_contents(start_y, max(1, end_y - start_y))

        result = "\n".join(line.string for line in contents).strip()

        if not result:
            return no_output_message

        return result

    async def _shell_integration_enabled(self) -> bool:
        """
        Check if shell integration is enabled via profile settings and prompt
        retrieval capabilities.
        """

        shell_integration_property: Literal[0, 1] = self.profile.all_properties.get(
            "Load Shell Integration Automatically", 0
        )
        prompt_found = await self._get_prompt() is not None
        has_integration_settings = bool(shell_integration_property)
        has_prompt_capabilities = prompt_found
        log.debug(
            ("{} => {}\n{} => {}").format(
                "has_integration_settings", has_integration_settings, "prompt_found", prompt_found
            )
        )

        if has_integration_settings and not has_prompt_capabilities:
            await self.maybe_load_shell_integration()

        return has_prompt_capabilities

    @asynccontextmanager
    async def _run_with_transaction[T, **P](
        self, coro: Callable[P, Coroutine[Any, Any, T]], *args: P.args, **kwargs: P.kwargs
    ) -> AsyncGenerator[Coroutine[Any, Any, T]]:
        try:
            async with transaction.Transaction(self.connection):
                # c = await coro(*args, **kwargs)
                # yield c
                yield coro(*args, **kwargs)
        finally:
            pass

    # --------------------------------------------------
    # ! NON-Shell-Integration-Related Helpers
    # --------------------------------------------------

    async def _run_command_without_shell_integration(
        self, starting_snapshot: list[str], *, command: str, suppress_broadcast: bool, per_change_timeout: float = 5.0
    ) -> str:
        """
        Run command without shell integration by snapshot-diff + prompt reappearance.
        """
        await self.session.async_send_text(command + "\r", suppress_broadcast=suppress_broadcast)

        saw_change = False
        timeout = per_change_timeout
        starting_line_number = len(starting_snapshot)
        start_lines = starting_snapshot
        end_lines = start_lines
        log.debug(f"Fallback run start: line_count={starting_line_number}")

        while timeout > 0:
            end_lines = await self._get_terminal_snapshot()

            if not saw_change and end_lines != start_lines:
                saw_change = True
                timeout = per_change_timeout
                start_lines = end_lines
                continue

            if saw_change and end_lines == start_lines:
                saw_change = False

            await asyncio.sleep(timeout)
            timeout -= 1

        changed = end_lines[starting_line_number:]
        output = "\n".join(changed)
        log.debug(f"Fallback run end:\n- line_count={len(end_lines)}\n- output_len={len(output)}")
        return output

    async def _get_terminal_snapshot(self, *, trim_end: bool = True, filter_all_empty: bool = False) -> list[str]:
        """Get a transactionally consistent snapshot of the terminal screen contents."""
        async with transaction.Transaction(self.connection):
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
