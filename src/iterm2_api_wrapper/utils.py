from collections.abc import Callable, Coroutine
from functools import partial
from typing import Any, Concatenate, ParamSpec, overload

from iterm2 import connection
from rich.console import Console
from rich.pretty import pprint


console = Console()
pp = partial(pprint, console=console, expand_all=True)


P = ParamSpec("P")


@overload
def run[T](
    forever: bool,
    coro: Callable[[connection.Connection], Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
) -> T: ...
@overload
def run[T](
    forever: bool,
    coro: Callable[Concatenate[connection.Connection, P], Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
    **kwargs: P.kwargs,
) -> T: ...
def run[T](
    forever: bool,
    coro: Callable[..., Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
    **kwargs: Any,
) -> T:
    """Run the given coroutine with iTerm2 connection."""

    def coro_wrapper(connection: connection.Connection) -> Coroutine[Any, Any, T]:
        return coro(connection, **kwargs)

    result: T = connection.Connection().run(
        forever=forever, coro=coro_wrapper, retry=retry, debug=debug
    )
    return result


def run_until_complete[T](
    coro: Callable[Concatenate[connection.Connection, P], Coroutine[Any, Any, T]],
    retry: bool = True,
    debug: bool = False,
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
    return run(forever=False, coro=coro, retry=retry, debug=debug, **kwargs)


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
