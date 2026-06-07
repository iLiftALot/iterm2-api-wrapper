from __future__ import annotations

import asyncio
import inspect
import json
import re
import shlex
from collections.abc import Awaitable
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable, ClassVar, Concatenate, Coroutine, Literal, cast, overload

from iterm2 import transaction
from websockets import ConcurrencyError, ConnectionClosed

from iterm2_api_wrapper._logging import PrettyLog
from iterm2_api_wrapper.alert import poly_modal_alert_handler
from iterm2_api_wrapper.connection import Connection
from iterm2_api_wrapper.typings import (
    App,
    CommandStatus,
    GlobalVar,
    GlobalVariable,
    HexCode,
    HexCodeValue,
    PartialProfile,
    Profile,
    Prompt,
    PromptMonitor,
    Session,
    SessionVar,
    SessionVariable,
    Tab,
    TabVar,
    TabVariable,
    UserVar,
    UserVariable,
    Variable,
    VariableContext,
    Window,
    WindowVar,
    WindowVariable,
    async_get_app,
    async_get_last_prompt,
    async_get_prompt_by_id,
)


log = PrettyLog.get_logger(__name__)
DEFAULT_SHELL_INTEGRATION_PATH = "~/.iterm2_shell_integration.{shell}"


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
    async def async_get_variable(self, name: Literal["*", UserVar.all]) -> dict[str, str]: ...
    @overload
    async def async_get_variable(self, name: UserVariable) -> str: ...
    async def async_get_variable(self, name: UserVariable) -> str | dict[str, str]:
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
    SESSION_VAR: ClassVar[type[SessionVar]] = SessionVar
    """Enum class :class:`SessionVar` for type-hinted :class:`~iterm2.Session` variable options. Use for :meth:`~iTermState.get_variable` methods"""
    GLOBAL_VAR: ClassVar[type[GlobalVar]] = GlobalVar
    """Enum class :class:`GlobalVar` for type-hinted global variable options. Use for :meth:`~iTermState.get_variable` methods"""
    TAB_VAR: ClassVar[type[TabVar]] = TabVar
    """Enum class :class:`TabVar` for type-hinted :class:`~iterm2.Tab` variable options. Use for :meth:`~iTermState.get_variable` methods"""
    WINDOW_VAR: ClassVar[type[WindowVar]] = WindowVar
    """Enum class :class:`WindowVar` for type-hinted :class:`~iterm2.Window` variable options. Use for the :meth:`~iTermState.get_variable` method."""
    HEX: ClassVar[type[HexCode]] = HexCode
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
                await self.session.async_send_text(f"source {shlex.quote(str(si_path))}\r")
                si_load_output = await self._wait_for_prompt()
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
    async def get_session_var(self, name: Literal["*", SessionVar.all]) -> dict[SessionVariable, str]: ...
    @overload
    async def get_session_var(self, name: SessionVariable) -> str: ...
    async def get_session_var(self, name: SessionVariable) -> str | dict[SessionVariable, str]:
        """Get a session variable."""
        ctx = "session" if not (len(parts := name.split(".")) >= 2 and parts[-2] == "user") else "user"
        return await self.get_variable(ctx=ctx, variable=name)

    @overload
    async def get_window_var(self, name: Literal["*", WindowVar.all]) -> dict[WindowVariable, str]: ...
    @overload
    async def get_window_var(self, name: WindowVariable) -> str: ...
    async def get_window_var(self, name: WindowVariable) -> str | dict[WindowVariable, str]:
        """Get a window variable."""
        return await self.get_variable(ctx="window", variable=name)

    @overload
    async def get_tab_var(self, name: Literal["*", TabVar.all]) -> dict[TabVariable, str]: ...
    @overload
    async def get_tab_var(self, name: TabVariable) -> str: ...
    async def get_tab_var(self, name: TabVariable) -> str | dict[TabVariable, str]:
        """Get a tab variable."""
        return await self.get_variable(ctx="tab", variable=name)

    @overload
    async def get_global_var(self, name: Literal["*", GlobalVar.all]) -> dict[GlobalVariable, str]: ...
    @overload
    async def get_global_var(self, name: GlobalVariable) -> str: ...
    async def get_global_var(self, name: GlobalVariable) -> str | dict[GlobalVariable, str]:
        """Get a global variable."""
        return await self.get_variable(ctx="iterm2", variable=name)

    @overload
    async def get_user_var(self, name: Literal["*", UserVar.all]) -> dict[UserVariable, str]: ...
    @overload
    async def get_user_var(self, name: UserVariable) -> str: ...
    async def get_user_var(self, name: UserVariable) -> str | dict[UserVariable, str]:
        """Get a user variable."""
        return await self.get_variable(ctx="user", variable=name)

    @overload
    @_validate_state
    async def get_variable(
        self,
        ctx: VariableContext,
        variable: Literal["*", GlobalVar.all, WindowVar.all, TabVar.all, SessionVar.all, UserVar.all],
    ) -> dict[str, str]: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: Literal["session"], variable: SessionVariable) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: Literal["tab"], variable: TabVariable) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: Literal["window"], variable: WindowVariable) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: Literal["iterm2"], variable: GlobalVariable) -> str: ...
    @overload
    @_validate_state
    async def get_variable(self, ctx: Literal["user"], variable: UserVariable) -> str: ...
    @_validate_state
    async def get_variable(self, ctx: VariableContext, variable: Variable) -> str | dict[str, str]:
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
    async def send_escape_sequence(self, *sequences: HexCode | HexCodeValue | str, broadcast: bool = False) -> None:
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
            if isinstance(seq, HexCode):
                return str(seq)

            # Resolve a HexCode member name (including aliases) to its bytes.
            member = HexCode.__members__.get(seq)
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
                log.debug("Shell integration not enabled; falling back to non-shell-integration method.")
                return await self._run_command_without_shell_integration(
                    command=command, suppress_broadcast=suppress, timeout=timeout
                )

            log.debug("Shell integration enabled.")

            async with transaction.Transaction(self.connection):
                await self.session.async_send_text(command + "\r", suppress_broadcast=suppress)
                last_prompt: Prompt | None = await self._get_prompt()

                if last_prompt is None:
                    log.warning(
                        ":warning: Shell integration appears broken; Unable to get last prompt. "
                        "Running command without shell integration."
                    )
                    return await self._run_command_without_shell_integration(
                        command=command, suppress_broadcast=suppress, timeout=timeout
                    )

                task = asyncio.create_task(self._wait_for_prompt(timeout=timeout))

            # Wait for the command to end.
            result = await task

            if result.prompt_id is None:
                log.warning(":warning: Command timeout; Running command without shell integration.")
                return await self._run_command_without_shell_integration(
                    command=command, suppress_broadcast=suppress, timeout=timeout
                )

            # Re-fetch the prompt for the command we sent to get the output range
            async with transaction.Transaction(self.connection):
                content = await self._get_prompt_output(result.prompt_id)

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

    async def _wait_for_prompt(self, *, timeout: float = 30.0) -> CommandStatus:
        """Block until the running command terminates. Returns string if command ended, None on timeout."""
        ModeFactory = PromptMonitor.Mode
        modes = [ModeFactory.COMMAND_START, ModeFactory.COMMAND_END, ModeFactory.PROMPT]
        try:
            async with PromptMonitor(self.connection, self.session.session_id, modes) as monitor:
                active_prompt_id: str | None = None
                active_command: str | None = None

                while True:
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
            return CommandStatus(
                prompt_id=None, command=None, exit_code=CommandStatus.ExitCode.GENERAL_FAILURE, timed_out=True
            )

    async def _get_prompt_output(self, prompt_id: str) -> str:
        """Returns a string with the content in a range of lines."""
        updated_prompt = await self._get_prompt(prompt_id)

        if updated_prompt is None:
            log.error(":error: Unable to get updated prompt; raising RuntimeError.")
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

        has_integration_settings = bool(shell_integration_property)

        last_command_found = await self.get_session_var("lastCommand") is not None
        prompt_found = await self._get_prompt() is not None

        has_integration_prompt_capabilities = last_command_found and prompt_found

        # if has_integration_settings and not has_integration_prompt_capabilities:
        if has_integration_settings and not has_integration_prompt_capabilities:
            await self.maybe_load_shell_integration()

        return has_integration_prompt_capabilities

    # --------------------------------------------------
    # NON-Shell-Integration-Related Helpers
    # --------------------------------------------------

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
    def _extract_output_from_changed_block(changed: list[str], *, prompt_line: str, command: str) -> str:
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
        if command_norm and first.endswith(command_norm) and prompt_norm and prompt_norm in first:
            block = block[1:]

        # Drop trailing prompt line
        while block and not block[-1].strip():
            block.pop()
        if block and block[-1].strip() == prompt_norm:
            block.pop()

        return "\n".join(line.rstrip("\n") for line in block).strip()

    async def _get_prompt_candidate(
        self, *, suppress_broadcast: bool, retries: int = 5, retry_delay: float = 0.1
    ) -> tuple[list[str], str]:
        """
        Get terminal snapshot + prompt candidate.

        Works even when scrollback height is 0 by scanning for the last non-empty line.
        If no candidate exists, nudge with Enter a small bounded number of times.
        """
        lines = await self._get_terminal_snapshot()
        prompt_line = self._last_nonempty_line(lines)

        attempts = 0
        while prompt_line is None and attempts < retries:
            await self.session.async_send_text("\r", suppress_broadcast=suppress_broadcast)
            await asyncio.sleep(retry_delay)
            lines = await self._get_terminal_snapshot()
            prompt_line = self._last_nonempty_line(lines)
            attempts += 1

        if prompt_line is None:
            raise RuntimeError("Unable to identify prompt line in terminal contents for fallback execution.")

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
        start_lines, prompt_line = await self._get_prompt_candidate(suppress_broadcast=suppress_broadcast)

        log.debug(f"Fallback run start: line_count={len(start_lines)}, prompt={prompt_line!r}")

        await self.session.async_send_text(command + "\r", suppress_broadcast=suppress_broadcast)

        loop = self.loop or asyncio.get_running_loop()
        deadline = loop.time() + max(0.1, timeout)
        poll_interval = 0.1

        saw_change = False
        stable_prompt_polls = 0
        end_lines = start_lines

        while True:
            end_lines = await self._get_terminal_snapshot()

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
                raise TimeoutError("Timeout waiting for command completion (shell integration disabled).")

            await asyncio.sleep(poll_interval)

        changed = self._changed_slice(start_lines, end_lines)
        output = self._extract_output_from_changed_block(changed, prompt_line=prompt_line, command=command)

        log.debug(f"Fallback run end: line_count={len(end_lines)}, output_len={len(output)}")
        return output

    async def _get_terminal_snapshot(self) -> list[str]:
        """Get a transactionally consistent snapshot of the terminal screen contents."""
        async with transaction.Transaction(self.connection):
            line_info = await self.session.async_get_line_info()
            start = line_info.overflow
            total_lines = line_info.scrollback_buffer_height + line_info.mutable_area_height
            contents = await self.session.async_get_contents(first_line=start, number_of_lines=total_lines)

        return [line.string for line in contents]

    def asdict(self) -> dict[str, Any]:
        """Convert iTermState to dictionary."""
        return {
            key: {k: v for k, v in value.__dict__.items()} if hasattr(value, "__dict__") else value
            for key, value in self.__dict__.items()
            if not key.startswith("_")
        }
