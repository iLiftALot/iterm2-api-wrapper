from __future__ import annotations

import os
import subprocess
from pathlib import Path

from AppKit import (
    NSRunningApplication,  # pyright: ignore[reportAttributeAccessIssue]
    NSWorkspace,  # pyright: ignore[reportAttributeAccessIssue]
    NSWorkspaceLaunchAndHide,  # pyright: ignore[reportAttributeAccessIssue]
)


try:
    import applescript  # pyright: ignore[reportMissingImports]

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


def activate_iterm_app(app_path: str | None = None) -> None:
    """Activate iTerm2, optionally targeting a specific app bundle path."""
    target_path = app_path or os.getenv("IT2_APP_PATH")

    if target_path:
        bundle_path = str(Path(target_path).expanduser().resolve())
        result = subprocess.run(["open", "-g", bundle_path], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Could not launch iTerm2 at {bundle_path}: {result.stderr.strip()}")
        return

    bundle = "com.googlecode.iterm2"
    ws = NSWorkspace.sharedWorkspace()
    if not NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle):
        ok, _ = ws.launchAppWithBundleIdentifier_options_additionalEventParamDescriptor_launchIdentifier_(
            bundle,
            # NSWorkspaceLaunchDefault,
            NSWorkspaceLaunchAndHide,
            # NSWorkspaceLaunchAndPrint,
            # NSWorkspaceLaunchNewInstance,
            None,
            None,
        )
        if not ok:
            raise RuntimeError("Could not launch iTerm2 application")
