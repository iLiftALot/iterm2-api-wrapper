from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Concatenate

from .._logging import PrettyLog
from .pyobjc_typings import (
    NSURL,
    NSApplicationActivateAllWindows,
    NSApplicationActivateIgnoringOtherApps,
    NSRunningApplication,
    NSWorkspace,
    NSWorkspaceOpenConfiguration,
)


if TYPE_CHECKING:
    from ..api.it2connection import Connection
    from ..gateway import _Connection


log = PrettyLog.get_logger(__name__)

ITERM2_BUNDLE_ID = os.getenv("ITERM2_BUNDLE_ID", "com.googlecode.iterm2")
ITERM2_EXECTUABLE_PATH = os.getenv("IT2_APP_PATH", None) or os.getenv(
    "ITERM2_EXECTUABLE_PATH", "/Applications/iTerm.app"
)
_DEFAULT_NEW_APP_TIMEOUT_S = 15.0
_CONNECTION_READY_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.5


def _get_new_app_timeout_s() -> float:
    raw_timeout = os.getenv("ITERM_NEW_APP_TIMEOUT", _DEFAULT_NEW_APP_TIMEOUT_S)

    try:
        return max(0.0, float(raw_timeout))
    except ValueError:
        log.warning(f"Invalid ITERM_NEW_APP_TIMEOUT={raw_timeout!r}; using {_DEFAULT_NEW_APP_TIMEOUT_S:.1f}s.")
        return _DEFAULT_NEW_APP_TIMEOUT_S


def _log_launch_completion(
    running_app: NSRunningApplication | None,
    error: Exception | Any,
) -> None:
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


def _activation_options() -> int:
    return NSApplicationActivateAllWindows | NSApplicationActivateIgnoringOtherApps


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
    workspace: NSWorkspace = field(default_factory=NSWorkspace.sharedWorkspace)
    url: NSURL = field(default_factory=lambda: NSURL.fileURLWithPath_(ITERM2_EXECTUABLE_PATH))
    config: NSWorkspaceOpenConfiguration = field(default_factory=lambda: NSWorkspaceOpenConfiguration.alloc().init())

    def __post_init__(self):
        iterm_url = self.workspace.URLForApplicationWithBundleIdentifier_(ITERM2_BUNDLE_ID)
        if iterm_url is None:
            raise RuntimeError(
                "The iTerm application is currently closed and attempts derive the "
                f"absolute iTerm path via the bundle identifier ({ITERM2_BUNDLE_ID}) "
                "has failed."
            )
        self.url = iterm_url
        self.__configure()

    @property
    def running_iterm_apps(self) -> list[NSRunningApplication]:
        return NSRunningApplication.runningApplicationsWithBundleIdentifier_(ITERM2_BUNDLE_ID)

    def __configure(self) -> None:
        self.config.setActivates_(False)

    def launch(self) -> None:
        """Request that macOS launch iTerm2, then return currently running matches.

        This intentionally does not run a nested Cocoa console event loop. The
        completion handler is useful for logging, but readiness is determined by
        polling NSRunningApplication and then by connecting to iTerm2's API socket.
        """
        self.workspace.openApplicationAtURL_configuration_completionHandler_(
            self.url,
            self.config,
            _log_launch_completion,
        )
        log.debug(f"Requested iTerm launch via NSWorkspace: {self.url.absoluteString()}")

    def first_finished_application(self) -> NSRunningApplication | None:
        for application in self.running_iterm_apps:
            if application.isFinishedLaunching():
                return application
        return None

    def activate(self, app: NSRunningApplication) -> None:
        if app.isActive():
            return

        if not app.activateWithOptions_(_activation_options()):
            raise RuntimeError("Could not activate iTerm2 application.")

    def kill_all(self):
        stats = {}
        for app in self.running_iterm_apps:
            app_name = app.localizedName()
            stats[app_name] = {
                "localizedName": app.localizedName(),
                "bundleIdentifier": app.bundleIdentifier(),
                "processIdentifier": app.processIdentifier(),
                "executableURL": app.executableURL(),
                "launchDate": app.launchDate(),
                "isActive": app.isActive(),
                "isFinishedLaunching": app.isFinishedLaunching(),
                "isHidden": app.isHidden(),
            }
            terminated: bool = app.forceTerminate()
            stats[app_name]["terminated"] = terminated

    async def async_for_each_app[T, **P](
        self,
        func: Callable[Concatenate[NSRunningApplication, P], Coroutine[Any, Any, T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> list[T]:
        outputs: list[T] = []
        for app in self.running_iterm_apps:
            outputs.append(await func(app, *args, **kwargs))
        return outputs

    def for_each_app[T, **P](
        self, func: Callable[Concatenate[NSRunningApplication, P], T], *args: P.args, **kwargs: P.kwargs
    ) -> list[T]:
        outputs = []
        for app in self.running_iterm_apps:
            outputs.append(func(app, *args, **kwargs))
        return outputs


def is_iterm_app_running() -> bool:
    return bool(NSRunningApplication.runningApplicationsWithBundleIdentifier_(ITERM2_BUNDLE_ID))


def iterm_not_open() -> bool:
    closed = not is_iterm_app_running()
    log.debug("iTerm application was found to be closed." if closed else "iTerm application was found to be open.")
    return closed


async def async_ensure_iterm_app_running(
    *,
    activate: bool = False,
    timeout_s: float = ITERM_NEW_APP_TIMEOUT,
    poll_interval_s: float = _POLL_INTERVAL_S,
) -> NSRunningApplication:
    app_container = PyObjcContainer()
    if not app_container.running_iterm_apps:
        log.debug("iTerm application is not running; requesting launch.")
        app_container.launch()
    else:
        log.debug("iTerm application is already running; waiting for readiness.")

    iterm_application = await _wait_for_finished_application(
        app_container,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
    )

    if activate:
        app_container.activate(iterm_application)

    log.debug(f"Successfully loaded {iterm_application.bundleIdentifier()} ({iterm_application.bundleURL()})")
    return iterm_application


async def async_create_app_with_retry(
    connection_cls: type[_Connection | Connection],
    *,
    activate: bool = False,
) -> Connection:
    """Launch iTerm2 if needed, wait for app launch, then wait for API readiness."""
    from ..gateway import _async_create_connection_with_retry

    await async_ensure_iterm_app_running(activate=activate)

    return await _async_create_connection_with_retry(
        connection_cls=connection_cls,
        timeout_s=_CONNECTION_READY_TIMEOUT_S,
    )
