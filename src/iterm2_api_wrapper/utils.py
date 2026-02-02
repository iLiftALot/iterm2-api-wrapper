from collections.abc import Callable, Coroutine
from functools import partial
from pathlib import Path
from typing import Any, Concatenate, Literal, ParamSpec, TypeVar, overload

from iterm2 import connection
from rich.console import Console
from rich.pretty import pprint


log_path = Path(__file__).resolve().parents[2] / "logs" / "iterm2_api_wrapper.log"
log_path.parent.mkdir(parents=True, exist_ok=True)
log_path.write_text("")  # Clear log file on each run
file_console = Console(
    file=open(log_path, "a"), log_time=True, log_time_format="%Y-%m-%d %H:%M:%S"
)
terminal_console = Console(emoji=True)
pp = partial(pprint, console=terminal_console, expand_all=True)


def log(message: str, *args, mode: Literal["terminal", "file", "all"] = "all", **kwargs) -> None:
    """Log a message to both the log file and the terminal."""
    if mode in ("file", "all"):
        file_console.print(message, *args, **kwargs)
    if mode in ("terminal", "all"):
        terminal_console.log(message, *args, **kwargs)


P = ParamSpec("P")
T = TypeVar("T")


@overload
def run[T](
    forever: bool,
    coro: Callable[[connection.Connection], Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
) -> T: ...


@overload
def run(
    forever: bool,
    coro: Callable[Concatenate[connection.Connection, P], Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T: ...


def run(
    forever: bool,
    coro: Callable[Concatenate[connection.Connection, P], Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run the given coroutine with iTerm2 connection."""

    def coro_wrapper(connection: connection.Connection) -> Coroutine[Any, Any, T]:
        return coro(connection, *args, **kwargs)

    result: T = connection.Connection().run(
        forever=forever, coro=coro_wrapper, retry=retry, debug=debug
    )
    return result


def run_until_complete(
    coro: Callable[Concatenate[connection.Connection, P], Coroutine[Any, Any, T]],
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

    :param coro: The coroutine to run which must accept ``connection.Connection``
        as its first argument, and may accept keyword arguments after that.
    :type coro: ``Callable[[connection.Connection, ...], Coroutine[Any, Any, T]]``
    :param retry: Whether to retry on failure. Defaults to ``True``.
    :type retry: ``bool``
    :param debug: Whether to enable debug output. Defaults to ``False``.
    :type debug: ``bool``
    :param kwargs: Additional keyword arguments to pass to the coroutine.
    :type kwargs: ``Any``
    :returns: The result of the coroutine.
    :rtype: ``T``
    """
    return run(False, coro, retry, debug, *args, **kwargs)


def run_forever(
    coro: Callable[[connection.Connection], Coroutine[Any, Any, None]],
    retry: bool = True,
    debug: bool = False,
) -> None:
    """Run the given coroutine forever, with optional retry and debug.

    :param coro: The coroutine to run which must accept ``connection.Connection``.
    :type coro: ``Callable[[connection.Connection], Coroutine[Any, Any, None]]``
    :param retry: Whether to retry on failure. Defaults to ``True``.
    :type retry: ``bool``
    :param debug: Whether to enable debug output. Defaults to ``False``.
    :type debug: ``bool``
    """
    run(forever=True, coro=coro, retry=retry, debug=debug)
