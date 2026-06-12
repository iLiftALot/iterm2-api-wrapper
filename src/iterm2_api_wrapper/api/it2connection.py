from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import traceback
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar, Concatenate, overload

from iterm2 import _version, api_pb2, auth  # , connection
from websockets.asyncio.client import ClientConnection, unix_connect
from websockets.asyncio.client import connect as WebSocketConnect
from websockets.exceptions import InvalidMessage, InvalidStatus
from websockets.typing import Subprotocol

from .._logging import PrettyLog


log = PrettyLog.get_logger(__name__)


DisconnectCallback = Callable[[], None]
MessageMatcher = Callable[[api_pb2.ServerOriginatedMessage], bool]
NotificationHelper = Callable[["Connection", api_pb2.ServerOriginatedMessage], Coroutine[Any, Any, bool | None]]
gDisconnectCallbacks: list[DisconnectCallback] = []


def _getenv(key: str) -> str | None:
    return os.environ.get(key)


def _cookie_and_key() -> tuple[str | None, str | None]:
    cookie = _getenv("ITERM2_COOKIE")
    key = _getenv("ITERM2_KEY")
    return cookie, key


def _headers() -> dict[str, str]:
    cookie, key = _cookie_and_key()
    headers = {
        "origin": "ws://localhost/",
        "x-iterm2-library-version": f"python {_version.__version__}",
        "x-iterm2-disable-auth-ui": "true",
        "x-iterm2-advisory-name": auth.get_script_name(),
    }

    if cookie is not None:
        headers["x-iterm2-cookie"] = cookie

    if key is not None:
        headers["x-iterm2-key"] = key

    return headers


def _uri() -> str:
    return "ws://localhost:1912"


def _subprotocols() -> list[Subprotocol]:
    return [Subprotocol("api.iterm2.com")]


_RETRIES = 0


class Connection:
    """Modern iTerm2 API websocket connection. Remaster of iTerm2's :class:`~iterm2.Connection`.

    This owns the connection/dispatch behavior instead of inheriting from
    upstream ``iterm2.connection.Connection``.

    Implements updated websocket connection logic and improved typing.
    """

    helpers: ClassVar[list[NotificationHelper]] = []

    def __init__(self) -> None:
        """Initialize the Connection instance.

        Updated to enhance typing clarity and resolve mypy errors in
        other methods.
        """

        self.websocket: ClientConnection | None = None
        # A list of tuples of (match_func, future). When a message is received
        # each match_func is called with the message as an argument. The first
        # one that returns true gets its future's result set with that message.
        # If none returns True it is dispatched through the helpers. Typically
        # that would be a notification.
        self.__receivers: list[tuple[MessageMatcher, asyncio.Future[api_pb2.ServerOriginatedMessage]]] = []
        self.__dispatch_forever_future: asyncio.Future | None = None
        self.__tasks: list[asyncio.Task] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def register_helper(cls, helper: NotificationHelper) -> None:
        """Register a notification helper for unclaimed server messages."""
        if helper is None:
            raise AssertionError("helper must not be None")

        cls.helpers.append(helper)

    @staticmethod
    async def async_create() -> Connection:
        """Create and authenticate a new iTerm2 API connection.

        This is intended for use in an apython REPL. It constructs a new
        connection and returns it without creating an asyncio event loop.

        ---

        Updates the usage of ``Connection.async_create()`` to use
        updated websocket exception handling for connection errors.

        ---

        :returns: A new connection to iTerm2.
        :rtype: Connection

        .. seealso:: [Running in a REPL](https://iterm2.com/python-api/usage.html#running-in-a-repl)
        """
        conn = Connection()
        # Set ITERM2_COOKIE and ITERM2_KEY if needed by making an Applescript request.
        have_fresh_cookie: bool = conn.authenticate(False)

        while True:
            try:
                loop = asyncio.get_running_loop()
                conn.loop = loop
                conn.websocket = await conn._get_connect_coro()
                conn.__dispatch_forever_future = asyncio.ensure_future(conn._async_dispatch_forever(conn, loop))
                return conn
            # except (ConnectionRefusedError, FileNotFoundError, InvalidProxyMessage):
            except ConnectionRefusedError as e:
                # ! NOTE: App might not be open
                from ..mac.platform_macos import activate_iterm_app
                global _RETRIES
                _RETRIES += 1
                log.warning(f"Connection was refused. App might not be open. Retry # {_RETRIES}")
                iterm_is_closed = activate_iterm_app(None, comfirm_close=True)

                return await conn.async_create()
            except InvalidStatus as status_code_exception:
                if status_code_exception.response.status_code == 401:
                    if have_fresh_cookie:
                        log.error("Authentication failed with a cookie. Cannot connect to iTerm2.")
                        raise
                    # Force request a cookie and try one more time.
                    conn._remove_auth()
                    have_fresh_cookie = conn.authenticate(True)
                    if not have_fresh_cookie:
                        log.error("Failed to obtain authentication cookie. Cannot connect to iTerm2.")
                        # Didn't get a cookie, so no point trying again.
                        raise
                elif status_code_exception.response.status_code == 406:
                    log.error(
                        "This version of the iterm2 module is too old for "
                        "the current version of iTerm2. Please upgrade."
                    )
                    sys.exit(1)
                else:
                    log.error(
                        "Failed to connect to iTerm2 with unexpected status code: "
                        f"{status_code_exception.response.status_code}"
                    )
                    raise

    @property
    def iterm2_protocol_version(self) -> tuple[int, int]:
        """
        Returns a tuple (major version, minor version) or 0,0 if it's an old
        version of iTerm2 that doesn't report its version or it's unknown.

        ---

        Updates the logic to use ``self.websocket.response.headers`` instead of
        ``self.websocket.response_headers``.

        ---

        :returns: A tuple (major version, minor version) or (0, 0) if unknown.
        :rtype: tuple[int, int]
        """
        if self.websocket is None or self.websocket.response is None:
            return (0, 0)
        key = "X-iTerm2-Protocol-Version"
        if key not in self.websocket.response.headers:
            return (0, 0)
        header_value = self.websocket.response.headers[key]
        parts = header_value.split(".")
        if len(parts) != 2:
            return (0, 0)
        return (int(parts[0]), int(parts[1]))

    def _unix_domain_socket_path(self) -> str:
        suite = os.environ.get("IT2_SUITE", "iTerm2")
        application_support = os.path.expanduser("~/Library/Application Support/" + suite)
        return os.path.join(application_support, "private", "socket")

    def _get_connect_coro(self) -> WebSocketConnect:
        """Get the appropriate connect coroutine based on whether the Unix domain socket path exists.

        ---

        Re-implemented only for clarity of the return type.

        ---

        :returns: A coroutine that can be awaited to establish a websocket connection.
        :rtype: connect
        """

        path: str = self._unix_domain_socket_path()

        if os.path.exists(path):
            return self._get_unix_connect_coro()
        return self._get_tcp_connect_coro()

    def _get_unix_connect_coro(self) -> WebSocketConnect:
        """Experimental: connect with unix domain socket.

        ---

        Updated to use the correct parameters for ``unix_connect`` (``extra_headers`` -> ``additional_headers``)
        and to have a more accurate return type.

        ---

        :returns: A coroutine that can be awaited to establish a websocket connection using a Unix domain socket.
        :rtype: connect
        """

        path: str = self._unix_domain_socket_path()
        return unix_connect(
            path=path,
            uri="ws://localhost",
            ping_interval=None,
            close_timeout=0,
            additional_headers=_headers(),
            subprotocols=_subprotocols(),
            max_size=None,
        )

    def _get_tcp_connect_coro(self) -> WebSocketConnect:
        """Connect with TCP socket.

        ---

        Updated to use the correct parameters for ``connect`` (``extra_headers`` -> ``additional_headers``)
        and to have a more accurate return type.

        ---

        :returns: A coroutine that can be awaited to establish a websocket connection using a TCP socket.
        :rtype: connect
        """
        return WebSocketConnect(
            uri=_uri(),
            ping_interval=None,
            close_timeout=0,
            additional_headers=_headers(),
            subprotocols=_subprotocols(),
            max_size=None,
        )

    async def async_close(self) -> None:
        """Cancel the dispatcher task and close the websocket cleanly."""
        dispatch_future = self.__dispatch_forever_future
        if dispatch_future is not None and not dispatch_future.done():
            dispatch_future.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await dispatch_future

        self.__dispatch_forever_future = None

        pending_tasks = [task for task in self.__tasks if not task.done()]
        for task in pending_tasks:
            task.cancel()

        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

        self.__tasks = []

        websocket = self.websocket
        self.websocket = None
        if websocket is None:
            return

        await websocket.close()
        await websocket.wait_closed()

    async def async_connect[T](self, coro: Callable[[Connection], Coroutine[Any, Any, T]], retry: bool = False) -> T:
        """Establishes a websocket connection.

        ---

        Updates parameter types along with the updated websocket error handling (
            ``InvalidStatusCode`` -> ``InvalidStatus``
                and...
            ``exception.status_code`` -> ``exception.response.status_code``
        ).

        ---

        You probably want to use Connection.run(), which takes care of runloop
        setup for you. Connects to iTerm2 on localhost. Once connected, awaits
        execution of coro.

        This uses ITERM2_COOKIE and ITERM2_KEY environment variables to help
        with authentication. ITERM2_COOKIE has a shared secret that lets
        user-launched scripts skip the auth dialog. ITERM2_KEY is used to tie
        together the output
        of this program with its entry in the scripting console.

        ---

        :param coro: A coroutine to run once connected.
        :type coro: Callable[[Connection], Coroutine[Any, Any, T]]
        :param retry: Keep trying to connect until it succeeds?
        :type retry: bool
        :returns: The result of the coroutine.
        :rtype: T
        """
        done = False
        while not done:
            # Set ITERM2_COOKIE and ITERM2_KEY if needed by making an Applescript request.
            # This cookie might be stale, but we'll try it optimstically.
            have_fresh_cookie: bool = self.authenticate(False)

            try:
                async with self._get_connect_coro() as websocket:
                    done = True
                    self.websocket = websocket
                    try:
                        return await coro(self)
                    except Exception:
                        traceback.print_exc()
                        sys.exit(1)
            except InvalidStatus as exception:
                status_code = exception.response.status_code

                if status_code == 401:
                    # Auth failure.
                    if retry:
                        # Sleep and try to authenticate until successful.
                        while not have_fresh_cookie:
                            await asyncio.sleep(0.5)
                            have_fresh_cookie = self.authenticate(True)
                    else:
                        # Not retrying forever.
                        if have_fresh_cookie:
                            # Welp, that shoulda worked. Give up.
                            raise

                        # Prepare the second and final attempt.
                        self._remove_auth()
                        have_fresh_cookie = self.authenticate(True)
                        if not have_fresh_cookie:
                            # Failed to get a cookie. Give up.
                            raise
                elif status_code == 406:
                    log.error(
                        "This version of the iterm2 module is too old "
                        "for the current version of iTerm2. Please upgrade."
                    )
                    sys.exit(1)
                    raise
                else:
                    raise
            except InvalidMessage:
                # This is a temporary workaround for this issue:
                #
                # https://gitlab.com/gnachman/iterm2/issues/7681#note_163548399
                # https://github.com/aaugustin/websockets/issues/604
                #
                # I'm leaving the print statement in because I'm worried this
                # might have unexpected consequences, as InvalidMessage is
                # certainly not very specific.
                traceback.print_exc()
                log.warning("websockets.connect failed with InvalidMessage. Retrying.")
            except (ConnectionRefusedError, OSError) as exception:
                # https://github.com/aaugustin/websockets/issues/593
                if retry:
                    await asyncio.sleep(0.5)
                else:
                    log.error(
                        """There was a problem connecting to iTerm2.

                        Please check the following:
                        * Ensure the Python API is enabled in iTerm2's preferences
                        * Ensure iTerm2 is running
                        * Ensure script is running on the same machine as iTerm2

                        If you'd prefer to retry connecting automatically instead of
                        raising an exception, pass retry=true to run_until_complete()
                        or run_forever()."""
                    )
                    path = self._unix_domain_socket_path()
                    exists = os.path.exists(path)
                    if exists:
                        log.error(
                            "If you have downgraded from iTerm2 3.3.12+ to an older version, "
                            f"you must manually delete the file at {path}.\n"
                        )

                    done = True
                    raise ConnectionRefusedError("Problem connecting to iTerm2.") from exception
            finally:
                self._remove_auth()

        raise RuntimeError("Unreachable code reached in async_connect.")

    def run[T](
        self, forever: bool, coro: Callable[[Connection], Coroutine[Any, Any, T]], retry: bool, debug: bool = False
    ) -> T:
        if self.loop is not None and not self.loop.is_closed():
            self.loop.close()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def async_main(connection: Connection) -> T:
            self.__tasks = []
            dispatch_forever_task = asyncio.ensure_future(self._async_dispatch_forever(connection, loop))

            try:
                result = await coro(connection)

                if forever:
                    await dispatch_forever_task

                return result

            finally:
                dispatch_forever_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await dispatch_forever_task

                for task in self.__tasks:
                    task.cancel()

                if self.__tasks:
                    await asyncio.gather(*self.__tasks, return_exceptions=True)

        loop.set_debug(debug)
        self.loop = loop

        try:
            result = loop.run_until_complete(self.async_connect(async_main, retry))
        finally:
            global gDisconnectCallbacks
            callbacks = list(gDisconnectCallbacks)
            gDisconnectCallbacks.clear()
            for callback in callbacks:
                callback()

        return result

    async def async_send_message(self, message: api_pb2.ClientOriginatedMessage) -> None:
        if self.websocket is None:
            raise ConnectionError("Cannot send message before websocket is connected.")

        await self.websocket.send(message.SerializeToString())

    def _get_receiver_future(
        self, message: api_pb2.ServerOriginatedMessage
    ) -> asyncio.Future[api_pb2.ServerOriginatedMessage] | None:
        """Remove and return the receiver future matching ``message``."""
        index = self._receiver_index(message)
        if index is None:
            return None

        _match_func, future = self.__receivers[index]
        del self.__receivers[index]
        return future

    def _receiver_index(self, message: api_pb2.ServerOriginatedMessage) -> int | None:
        """Find the receiver that should handle ``message``."""
        for index, receiver in enumerate(self.__receivers):
            match_func = receiver[0]
            if match_func and match_func(message):
                return index

        return None

    async def async_dispatch_until_id(self, reqid: str) -> api_pb2.ServerOriginatedMessage:
        """Dispatch incoming messages until the response with ``reqid`` arrives."""
        future: asyncio.Future[api_pb2.ServerOriginatedMessage] = asyncio.Future()

        def match_func(incoming_message: api_pb2.ServerOriginatedMessage) -> bool:
            return incoming_message.id == reqid

        self.__receivers.append((match_func, future))
        return await future

    async def _async_dispatch_to_helper(self, message: api_pb2.ServerOriginatedMessage) -> None:
        """Dispatch an unclaimed message to registered notification helpers."""
        for helper in type(self).helpers:
            if helper is None:
                raise AssertionError("helper must not be None")

            if await helper(self, message):
                break

    def _remove_auth(self) -> None:
        for var in ("ITERM2_COOKIE", "ITERM2_KEY"):
            os.environ.pop(var, None)

    def authenticate(self, force: bool) -> bool:
        """Request an iTerm2 auth cookie through AppleScript."""
        if force:
            self._remove_auth()

        try:
            return auth.authenticate()
        except auth.AuthenticationException:
            return False

    def _collect_garbage(self) -> None:
        """Keep pending task references only while they are still active."""
        self.__tasks = [task for task in self.__tasks if not task.done()]

    async def _async_dispatch_forever(self, connection: Connection, loop: asyncio.AbstractEventLoop) -> None:
        """Read websocket messages and dispatch them to receivers or helpers."""
        self.__tasks = []

        if self.websocket is None:
            raise ConnectionError("Cannot dispatch messages before websocket is connected.")

        try:
            while True:
                data = await self.websocket.recv(decode=False)
                self._collect_garbage()

                message = api_pb2.ServerOriginatedMessage()
                message.ParseFromString(data)

                future = self._get_receiver_future(message)
                # Note that however we decide to handle this message,
                # it must be done *after* we await on the websocket.
                # Otherwise we might never get the chance.
                if future is None:
                    # May be a notification.
                    self.__tasks.append(asyncio.ensure_future(self._async_dispatch_to_helper(message)))
                else:
                    self.set_message_in_future(loop, message, future)

        except asyncio.CancelledError:
            # Presumably a run_until_complete script
            pass

        except Exception:
            # I'm not quite sure why this is necessary, but if we don't
            # catch and re-raise the exception it gets swallowed.
            traceback.print_exc()
            raise

    def set_message_in_future(
        self,
        loop: asyncio.AbstractEventLoop,
        message: api_pb2.ServerOriginatedMessage,
        future: asyncio.Future[api_pb2.ServerOriginatedMessage],
    ) -> None:
        """Schedule an RPC response message into its waiting future."""

        def set_result() -> None:
            if not future.done():
                future.set_result(message)

        loop.call_soon(set_result)


@overload
def run[T](
    forever: bool, coro: Callable[[Connection], Coroutine[Any, Any, T]], retry: bool = True, debug: bool = False
) -> T: ...


@overload
def run[T, **P](
    forever: bool,
    coro: Callable[Concatenate[Connection, P], Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T: ...


def run[T, **P](
    forever: bool,
    coro: Callable[Concatenate[Connection, P], Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run the given coroutine with iTerm2 connection.

    ---

    :param forever: Don't terminate after main returns?
    :type forever: bool
    :param coro: A coroutine (async function) to run after connecting.
    :type coro: Callable[[Connection, ...], Coroutine[Any, Any, T]]
    :param retry: Keep trying to connect until it succeeds? Defaults to ``True``.
    :type retry: bool
    :param debug: Enable debug mode for the event loop? Defaults to ``False``.
    :type debug: bool
    :param args: Additional positional arguments to pass to the coroutine.
    :type args: Any
    :param kwargs: Additional keyword arguments to pass to the coroutine.
    :type kwargs: Any
    :returns: The result of the coroutine.
    :rtype: T
    :raises ConnectionRefusedError: If the connection to iTerm2 is refused.
    """

    def coro_wrapper(connection: Connection) -> Coroutine[Any, Any, T]:
        return coro(connection, *args, **kwargs)

    result: T = Connection().run(forever=forever, coro=coro_wrapper, retry=retry, debug=debug)

    return result


def run_until_complete[T, **P](
    coro: Callable[Concatenate[Connection, P], Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run the given coroutine until complete, with optional retry and debug.

    Fixes the incorrect typing of iterm2.run_until_complete.
    It demands a that only accepts a single argument of type
    Connection which then returns a coroutine
    containing None. That will be incorrect if the coroutine
    returns any other type. This wrapper fixes that by
    allowing the caller to specify the return type.

    Additionally, this wrapper allows passing extra arguments
    to the coroutine by creating a closure.

    ---

    :param coro: The coroutine to run which must accept ``Connection``
        as its first argument, and may accept keyword arguments after that.
    :type coro: Callable[[Connection, ...], Coroutine[Any, Any, T]]
    :param retry: Whether to retry on failure. Defaults to ``True``.
    :type retry: bool
    :param debug: Whether to enable debug output. Defaults to ``False``.
    :type debug: bool
    :param kwargs: Additional keyword arguments to pass to the coroutine.
    :type kwargs: Any
    :returns: The result of the coroutine.
    :rtype: T
    :raises ConnectionRefusedError: If the connection to iTerm2 is refused.
    """
    try:
        return run(False, coro, retry, debug, *args, **kwargs)
    except ConnectionRefusedError as exc:
        log.error("Failed to connect to iTerm2:", exc, sep="\n")
        raise


def run_forever(
    coro: Callable[[Connection], Coroutine[Any, Any, None]], retry: bool = True, debug: bool = False
) -> None:
    """Run the given coroutine forever, with optional retry and debug.

    ---

    :param coro: The coroutine to run which must accept ``Connection``.
    :type coro: Callable[[Connection], Coroutine[Any, Any, None]]
    :param retry: Whether to retry on failure. Defaults to ``True``.
    :type retry: bool
    :param debug: Whether to enable debug output. Defaults to ``False``.
    :type debug: bool
    :raises ConnectionRefusedError: If the connection to iTerm2 is refused.
    """
    try:
        run(forever=True, coro=coro, retry=retry, debug=debug)
    except ConnectionRefusedError as exc:
        log.error("Failed to connect to iTerm2:", exc, sep="\n")
        raise ConnectionRefusedError from exc


def add_disconnect_callback(callback: DisconnectCallback) -> None:
    """Run ``callback`` on the next disconnection."""
    gDisconnectCallbacks.append(callback)
