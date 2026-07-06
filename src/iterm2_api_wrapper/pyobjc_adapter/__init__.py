from __future__ import annotations

import asyncio
import inspect
import os
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Any, Concatenate, Literal, TypedDict

from .._logging import PrettyLog
from .pyobjc_typings import (
    NSURL,
    NSApplicationActivateAllWindows,
    NSBundle,
    NSDate,
    NSRunningApplication,
    NSWorkspace,
    NSWorkspaceOpenConfiguration,
    autorelease_pool,
)


if TYPE_CHECKING:
    from .. import iTermConnection
    from ..api.it2connection import Connection


log = PrettyLog.get_logger(__name__)

ITERM2_BUNDLE_ID = os.getenv("ITERM2_BUNDLE_ID", "com.googlecode.iterm2")
ITERM2_EXECTUABLE_PATH = os.getenv("IT2_APP_PATH", None) or os.getenv(
    "ITERM2_EXECTUABLE_PATH", "/Applications/iTerm.app"
)
_DEFAULT_NEW_APP_TIMEOUT_S = 15.0
_CONNECTION_READY_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.5


class KillResult(TypedDict, total=False):
    localizedName: str | None
    bundleIdentifier: str | None
    processIdentifier: int
    executableURL: NSURL | None
    launchDate: NSDate | None
    isActive: bool
    isFinishedLaunching: bool
    isHidden: bool
    terminated: bool


def autoreleased[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Run a synchronous PyObjC-facing function inside a fresh autorelease pool.

    Do not use this decorator on async functions. An autorelease pool should not
    span arbitrary ``await`` suspension points.
    """
    if inspect.iscoroutinefunction(func) or inspect.isasyncgenfunction(func):
        func_type_label = "generator" if inspect.isasyncgenfunction(func) else "function"
        raise TypeError(
            f"@autoreleased cannot decorate async {func_type_label} ({func.__qualname__!r}). "
            "Wrap only the synchronous PyObjC calls, or extract them into a sync helper."
        )

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with autorelease_pool():
            return func(*args, **kwargs)

    return wrapper


def _get_new_app_timeout_s() -> float:
    raw_timeout = os.getenv("ITERM_NEW_APP_TIMEOUT", _DEFAULT_NEW_APP_TIMEOUT_S)

    try:
        return max(0.0, float(raw_timeout))
    except ValueError:
        log.warning(f"Invalid ITERM_NEW_APP_TIMEOUT={raw_timeout!r}; using {_DEFAULT_NEW_APP_TIMEOUT_S:.1f}s.")
        return _DEFAULT_NEW_APP_TIMEOUT_S


@autoreleased
def _log_launch_completion(running_app: NSRunningApplication | None, error: Exception | Any) -> None:
    if error is not None:
        log.warning(f"iTerm launch callback returned an error: {error}")
        return

    if running_app is None:
        log.debug("iTerm launch callback completed without a running application.")
        return

    log.debug(
        "iTerm launch callback completed: "
        f"bundle={running_app.bundleIdentifier()} "
        f"finishedLaunching={running_app.isFinishedLaunching()}"
    )


ITERM_NEW_APP_TIMEOUT = _get_new_app_timeout_s()


def _activation_options() -> Literal[1]:
    return NSApplicationActivateAllWindows


async def _wait_for_finished_application(
    app_container: PyObjcContainer,
    *,
    timeout_s: float = ITERM_NEW_APP_TIMEOUT,
    poll_interval_s: float = _POLL_INTERVAL_S,
) -> NSRunningApplication:
    """Wait until macOS reports an iTerm2 instance has finished launching."""
    deadline = time.monotonic() + timeout_s
    iteration = 0

    while True:
        if finished_application := app_container.first_finished_application():
            return finished_application

        now = time.monotonic()
        if now >= deadline:
            raise RuntimeError(
                f"Unable to find an iTerm application that has finished loading within {timeout_s:.1f}s."
            )

        iteration += 1
        log.debug(f"Waiting for a finished iTerm application: iteration={iteration}")

        await asyncio.sleep(min(poll_interval_s, max(0.0, deadline - now)))


@dataclass
class PyObjcContainer:
    bundle_id: str | None = None
    executable_path: str | None = None

    @autoreleased
    def __post_init__(self):
        self.workspace = NSWorkspace.sharedWorkspace()
        self.config = NSWorkspaceOpenConfiguration.alloc().init()

        if self.bundle_id is None and self.executable_path is None:
            self.bundle_id = ITERM2_BUNDLE_ID
            self.executable_path = ITERM2_EXECTUABLE_PATH

        iterm_url = self._resolve_application_url()

        if iterm_url is None:
            raise RuntimeError(
                "Could not resolve the iTerm application from either "
                f"bundle_id={self.bundle_id!r} or executable_path={self.executable_path!r}."
            )

        self.url = iterm_url
        self.executable_path = iterm_url.path() or self.executable_path
        self.bundle_id = self._resolve_bundle_id(iterm_url) or self.bundle_id

        if self.bundle_id is None:
            raise RuntimeError(f"Could not resolve a bundle identifier from application URL {iterm_url!r}.")

        self.__configure()

    def __configure(self) -> None:
        """Internal method that is only called from methods with :func:`autoreleased` decorator."""
        self.config.setActivates_(False)

    @autoreleased
    def _resolve_application_url(self) -> NSURL | None:
        if self.bundle_id:
            app_url = self.workspace.URLForApplicationWithBundleIdentifier_(self.bundle_id)
            if app_url is not None:
                return app_url

        if self.executable_path:
            return NSURL.fileURLWithPath_(self.executable_path)

        return None

    @staticmethod
    @autoreleased
    def _resolve_bundle_id(app_url: NSURL) -> str | None:
        bundle = NSBundle.bundleWithURL_(app_url)
        if bundle is None:
            return None
        return bundle.bundleIdentifier()

    @property
    @autoreleased
    def running_apps(self) -> list[NSRunningApplication]:
        return self.workspace.runningApplications()

    @property
    @autoreleased
    def running_iterm_apps(self) -> list[NSRunningApplication]:
        if self.bundle_id is None:
            raise RuntimeError("Running apps cannot be extracted when PyObjcContainer.bundle_id is None.")
        return NSRunningApplication.runningApplicationsWithBundleIdentifier_(self.bundle_id)

    @autoreleased
    def launch(self) -> None:
        """Request that macOS launch iTerm2, then return currently running matches.

        This intentionally does not run a nested Cocoa console event loop. The
        completion handler is useful for logging, but readiness is determined by
        polling NSRunningApplication and then by connecting to iTerm2's API socket.
        """
        self.workspace.openApplicationAtURL_configuration_completionHandler_(
            self.url, self.config, _log_launch_completion
        )
        log.debug(f"Requested iTerm launch via NSWorkspace: {self.url.absoluteString()}")

    @autoreleased
    def first_finished_application(self) -> NSRunningApplication | None:
        for application in self.running_iterm_apps:
            if application.isFinishedLaunching():
                return application
        return None

    @autoreleased
    def activate(self, app: NSRunningApplication) -> None:
        if app.isActive():
            return

        if not app.activateWithOptions_(_activation_options()):
            raise RuntimeError("Could not activate iTerm2 application.")

    @autoreleased
    def kill_all(self) -> dict[str, KillResult]:
        stats: dict[str, KillResult] = {}
        for idx, app in enumerate(self.running_iterm_apps, 1):
            app_name = app.localizedName() or f"UnknownApp_{idx}_{app.bundleIdentifier()}_{app.processIdentifier()}"
            stats[app_name] = KillResult(
                localizedName=app.localizedName(),
                bundleIdentifier=app.bundleIdentifier(),
                processIdentifier=app.processIdentifier(),
                executableURL=app.executableURL(),
                launchDate=app.launchDate(),
                isActive=app.isActive(),
                isFinishedLaunching=app.isFinishedLaunching(),
                isHidden=app.isHidden(),
                terminated=app.forceTerminate(),
            )
            # terminated: bool = app.forceTerminate()
            # stats[app_name]["terminated"] = terminated
        return stats

    async def async_for_each_app[**P, T](
        self,
        func: Callable[Concatenate[NSRunningApplication, P], Coroutine[Any, Any, T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> list[T]:
        outputs: list[T] = []
        for app in self.running_iterm_apps:
            outputs.append(await func(app, *args, **kwargs))
        return outputs

    def for_each_app[**P, T](
        self, func: Callable[Concatenate[NSRunningApplication, P], T], *args: P.args, **kwargs: P.kwargs
    ) -> list[T]:
        outputs = []
        for app in self.running_iterm_apps:
            outputs.append(func(app, *args, **kwargs))
        return outputs


@autoreleased
def is_iterm_app_running(bundle_id: str = ITERM2_BUNDLE_ID) -> bool:
    return bool(NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id))


def iterm_not_open() -> bool:
    closed = not is_iterm_app_running()
    log.debug("iTerm application was found to be closed." if closed else "iTerm application was found to be open.")
    return closed


def _create_app_container() -> PyObjcContainer:
    """Create a :class:`PyObjcContainer` through its :func:`autoreleased` `__post_init__` path.

    Used by async flows to keep :class:`~pyobjc_typings.objc` setup inside synchronous autorelease
    boundaries without decorating async functions.
    """
    return PyObjcContainer()


async def async_ensure_iterm_app_running(
    *, activate: bool = False, timeout_s: float = ITERM_NEW_APP_TIMEOUT, poll_interval_s: float = _POLL_INTERVAL_S
) -> NSRunningApplication:
    app_container = _create_app_container()
    if not app_container.running_iterm_apps:
        log.debug("iTerm application is not running; requesting launch.")
        app_container.launch()
    else:
        log.debug("iTerm application is already running; waiting for readiness.")

    iterm_application = await _wait_for_finished_application(
        app_container, timeout_s=timeout_s, poll_interval_s=poll_interval_s
    )

    if activate is True:
        app_container.activate(iterm_application)

    @autoreleased
    def _log_loaded_application(iterm_application: NSRunningApplication) -> None:
        log.debug(f"Successfully loaded {iterm_application.bundleIdentifier()} ({iterm_application.bundleURL()})")

    _log_loaded_application(iterm_application)
    return iterm_application


async def async_create_app_with_retry(connection_cls: iTermConnection, *, activate: bool = False) -> Connection:
    """Launch iTerm2 if needed, wait for app launch, then wait for API readiness.

    This is the main entrypoint for async flows that need to ensure iTerm2 is running and ready to accept API connections.

    ---

    :param connection_cls: The class to use for creating the iTerm2 connection.
    :type connection_cls: :class:`iTermConnection`
    :param activate: Whether to activate the iTerm2 application after launching.
    :type activate: `bool`, default=False
    :return: An instance of the established connection.
    :rtype: `Connection`
    """

    from ..gateway import _async_create_connection_with_retry

    await async_ensure_iterm_app_running(activate=activate)

    return await _async_create_connection_with_retry(
        connection_cls=connection_cls, timeout_s=_CONNECTION_READY_TIMEOUT_S
    )
