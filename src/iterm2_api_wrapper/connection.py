from __future__ import annotations

import asyncio
import os
import sys
import traceback
from collections.abc import Callable, Coroutine
from typing import Any, Concatenate, overload

from iterm2 import api_pb2, connection
from websockets import ClientConnection, connect, exceptions, unix_connect

from iterm2_api_wrapper._logging import PrettyLog


log = PrettyLog.get_logger(__name__)


class Connection(connection.Connection):
    """Subclass of iTerm2's `Connection` which implements updated websocket connection logic."""

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
        self.__receivers: list[tuple[Callable[[api_pb2.ServerOriginatedMessage], bool], asyncio.Future]] = []
        self.__dispatch_forever_future: asyncio.Future | None = None
        self.__tasks: list[asyncio.Task] = []
        self.loop: asyncio.AbstractEventLoop | None = None

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

        .. seealso:: Running in a REPL at https://iterm2.com/python-api/usage.html#running-in-a-repl
        """
        conn = Connection()
        # Set ITERM2_COOKIE and ITERM2_KEY if needed by making an Applescript
        # request.
        have_fresh_cookie: bool = conn.authenticate(False)

        while True:
            try:
                conn.websocket = await conn._get_connect_coro()
                # pylint: disable=protected-access
                conn.__dispatch_forever_future = asyncio.ensure_future(
                    conn._async_dispatch_forever(conn, asyncio.get_running_loop())
                )
                return conn
            except exceptions.InvalidStatus as status_code_exception:
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
                        f"Failed to connect to iTerm2 with unexpected status code: {status_code_exception.response.status_code}"
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
        if self.websocket is None:
            return (0, 0)
        key = "X-iTerm2-Protocol-Version"
        if key not in self.websocket.response.headers:
            return (0, 0)
        header_value = self.websocket.response.headers[key]
        parts = header_value.split(".")
        if len(parts) != 2:
            return (0, 0)
        return (int(parts[0]), int(parts[1]))

    def _get_connect_coro(self) -> connect:
        """Get the appropriate connect coroutine based on whether the Unix domain socket path exists.

        ---

        Re-implemented only for clarity of the return type.

        ---

        :returns: A coroutine that can be awaited to establish a websocket connection.
        :rtype: connect
        """

        path: str = self._unix_domain_socket_path()
        exists: bool = os.path.exists(path)

        if exists:
            return self._get_unix_connect_coro()
        return self._get_tcp_connect_coro()

    def _get_unix_connect_coro(self) -> connect:
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
            additional_headers=connection._headers(),
            subprotocols=connection._subprotocols(),
            max_size=None,
        )

    def _get_tcp_connect_coro(self) -> connect:
        """Connect with TCP socket.

        ---

        Updated to use the correct parameters for ``connect`` (``extra_headers`` -> ``additional_headers``)
        and to have a more accurate return type.

        ---

        :returns: A coroutine that can be awaited to establish a websocket connection using a TCP socket.
        :rtype: connect
        """

        return connect(
            uri=connection._uri(),
            ping_interval=None,
            close_timeout=0,
            additional_headers=connection._headers(),
            subprotocols=connection._subprotocols(),
            max_size=None,
        )

    async def async_connect[T](self, coro: Callable[[Connection], Coroutine[Any, Any, T]], retry: bool = False) -> T:
        """Establishes a websocket connection.

        ---

        Updates parameter types along with the updated websocket error handling
        (``InvalidStatusCode`` -> ``InvalidStatus`` and ``exception.status_code`` -> ``exception.response.status_code``).

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
            # Set ITERM2_COOKIE and ITERM2_KEY if needed by making an
            # Applescript request. This cookie might be stale, but we'll try it
            # optimstically.
            have_fresh_cookie: bool = self.authenticate(False)

            try:
                async with self._get_connect_coro() as websocket:
                    done = True
                    self.websocket = websocket
                    # pylint: disable=broad-except
                    try:
                        result = await coro(self)
                        return result
                    except Exception:
                        traceback.print_exc()
                        sys.exit(1)
            except exceptions.InvalidStatus as exception:
                if exception.response.status_code == 401:
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
                elif exception.response.status_code == 406:
                    log.error(
                        "This version of the iterm2 module is too old "
                        "for the current version of iTerm2. Please upgrade."
                    )
                    sys.exit(1)
                    raise
                else:
                    raise
            except exceptions.InvalidMessage:
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
                            f"If you have downgraded from iTerm2 3.3.12+ to an older version, you must manually delete the file at {path}.\n"
                        )
                    done = True
                    raise ConnectionRefusedError("Problem connecting to iTerm2.") from exception
            finally:
                self._remove_auth()
        raise RuntimeError("Unreachable code reached in async_connect.")


@overload
def run[T](
    forever: bool,
    coro: Callable[[connection.Connection], Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
) -> T: ...


@overload
def run[T, **P](
    forever: bool,
    coro: Callable[Concatenate[connection.Connection, P], Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T: ...


def run[T, **P](
    forever: bool,
    coro: Callable[Concatenate[connection.Connection, P], Coroutine[Any, Any, T]],
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
    :type coro: Callable[[connection.Connection, ...], Coroutine[Any, Any, T]]
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
    connection.Connection which then returns a coroutine
    containing None. That will be incorrect if the coroutine
    returns any other type. This wrapper fixes that by
    allowing the caller to specify the return type.

    Additionally, this wrapper allows passing extra arguments
    to the coroutine by creating a closure.

    ---

    :param coro: The coroutine to run which must accept ``connection.Connection``
        as its first argument, and may accept keyword arguments after that.
    :type coro: Callable[[connection.Connection, ...], Coroutine[Any, Any, T]]
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

    :param coro: The coroutine to run which must accept ``connection.Connection``.
    :type coro: Callable[[connection.Connection], Coroutine[Any, Any, None]]
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
