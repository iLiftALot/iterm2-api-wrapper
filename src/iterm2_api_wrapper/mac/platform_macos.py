from AppKit import (
    NSRunningApplication,  # ty:ignore[unresolved-import]
    NSWorkspace,  # ty:ignore[unresolved-import]
    NSWorkspaceLaunchAndHide,  # ty:ignore[unresolved-import]
)
import applescript
from pathlib import Path


def maybe_reveal_hotkey_window(is_hotkey: bool):
    apple_script = applescript.AppleScript(
        path=str(Path(__file__).parent / "applescripts" / "iterm_osa.scpt")
    )
    result = apple_script.run(is_hotkey)
    return result


def _activate_iterm_app() -> None:
    """Activate iTerm2 application using pyobjc (AppKit)."""
    bundle = "com.googlecode.iterm2"
    ws = NSWorkspace.sharedWorkspace()
    if not NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle):
        ok, _ = (
            ws.launchAppWithBundleIdentifier_options_additionalEventParamDescriptor_launchIdentifier_(
                bundle,
                # NSWorkspaceLaunchDefault,
                NSWorkspaceLaunchAndHide,
                # NSWorkspaceLaunchAndPrint,
                # NSWorkspaceLaunchNewInstance,
                None,
                None,
            )
        )
        if not ok:
            raise RuntimeError("Could not launch iTerm2 application")

