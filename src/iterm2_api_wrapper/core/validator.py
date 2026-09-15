from __future__ import annotations

import asyncio
from functools import wraps
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Concatenate, Coroutine, ParamSpec, TypeVar, cast

from websockets import ConcurrencyError, ConnectionClosed

from .._logging import PrettyLog


if TYPE_CHECKING:
    from ..state import iTermState


P = ParamSpec("P")
T = TypeVar("T")
StateClassT = TypeVar("StateClassT", bound=type[Any])
log = PrettyLog.get_logger(__name__)


def _validate_state(
    method: Callable[Concatenate[iTermState, P], Coroutine[Any, Any, T]], *, ensure_state_name: str = "_ensure_state"
) -> Callable[Concatenate[iTermState, P], Coroutine[Any, Any, T]]:
    """Validate state and route the method to the correct event loop."""

    if not iscoroutinefunction(method):
        raise TypeError(
            "The _validate_state decorator can only be applied to async methods. "
            f"iTermState.{method!r} is not asynchronous."
        )

    @wraps(method)
    async def async_wrapper(self: iTermState, *args: P.args, **kwargs: P.kwargs) -> T:
        if not self.on_correct_loop:
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
                    f"future.cancel() -> {cancelled} "
                    f"(done={future.done()} "
                    f"cancelled={future.cancelled()})"
                )
                raise

        ensure_state = cast(Callable[[], Awaitable[None]], getattr(self, ensure_state_name))

        # We're on the correct loop — validate + execute
        try:
            await ensure_state()
            return await method(self, *args, **kwargs)
        except (ConnectionClosed, ConcurrencyError):
            log.warning("Connection closed, refreshing state and retrying...")
            await ensure_state()  # Uses the `iTermState._refresh_callback`
            return await method(self, *args, **kwargs)

    return async_wrapper


def validator(cls: StateClassT) -> StateClassT:
    """Apply state validation to every public async instance method."""

    ensure_state_name = "_ensure_state"

    ensure_state = vars(cls).get(ensure_state_name)
    if not iscoroutinefunction(ensure_state):
        raise TypeError(f"{cls.__qualname__} must define an async internal method named _ensure_state.")

    for name, attribute in tuple(vars(cls).items()):
        # Internal and dunder methods are implementation details, not public API.
        if name.startswith("_"):
            continue

        # State validation requires an instance, so these are not eligible.
        if isinstance(attribute, (classmethod, staticmethod)):
            continue

        if iscoroutinefunction(attribute):
            setattr(cls, name, _validate_state(attribute, ensure_state_name=ensure_state_name))

    return cls
