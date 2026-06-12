from __future__ import annotations

import os
import subprocess
from pathlib import Path

from AppKit import (
    NSRunningApplication,  # pyright: ignore[reportAttributeAccessIssue] # ty:ignore[unresolved-import]
    NSWorkspace,  # pyright: ignore[reportAttributeAccessIssue] # ty:ignore[unresolved-import]
    NSWorkspaceLaunchAndHide,  # pyright: ignore[reportAttributeAccessIssue] # ty:ignore[unresolved-import]
)

from .._logging import PrettyLog


try:
    import applescript  # pyright: ignore[reportMissingImports] # ty:ignore[unresolved-import]

    def maybe_reveal_hotkey_window(is_hotkey: bool):  # pyright: ignore[reportRedeclaration]
        apple_script = applescript.AppleScript(path=str(Path(__file__).parent / "applescripts" / "iterm_osa.scpt"))
        result = apple_script.run(is_hotkey)
        return result

except ImportError:

    def maybe_reveal_hotkey_window(is_hotkey: bool):
        raise ImportError(
            "The 'applescript' package is required to reveal the hotkey window. "
            "Install it using 'uv add --extra=applescript'."
        )


log = PrettyLog.get_logger(__name__)


def activate_iterm_app(app_path: str | None = None, confirm_closed: bool = False) -> bool | None:
    """Activate iTerm2, optionally targeting a specific app bundle path."""
    target_path = app_path or os.getenv("IT2_APP_PATH")
    log.debug(f"Initial target path: {target_path}")

    if target_path:
        bundle_path = str(Path(target_path).expanduser().resolve())
        result = subprocess.run(["open", "-g", bundle_path], capture_output=True, text=True)

        if result.returncode != 0:
            log.error(f"Could not launch iTerm2 at {bundle_path}: {result.stderr.strip()}")
            raise RuntimeError(f"Could not launch iTerm2 at {bundle_path}: {result.stderr.strip()}")

        log.debug(f"iTerm2 launched from target path -> bundle path: {bundle_path}")
        return (None if not confirm_closed else False)

    bundle = "com.googlecode.iterm2"
    ws = NSWorkspace.sharedWorkspace()



    if not NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle):
        log.debug("Application was found to be closed! Fixing that now.")
        ok, _launch_id = ws.launchAppWithBundleIdentifier_options_additionalEventParamDescriptor_launchIdentifier_(
            bundle,
            # NSWorkspaceLaunchDefault,
            NSWorkspaceLaunchAndHide,
            # NSWorkspaceLaunchAndPrint,
            # NSWorkspaceLaunchNewInstance,
            None,
            None,
        )
        if not ok:
            log.error("Could not launch iTerm2 application.")
            raise RuntimeError("Could not launch iTerm2 application.")
