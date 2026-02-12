from AppKit import (
    NSRunningApplication,  # ty:ignore[unresolved-import]
    NSWorkspace,  # ty:ignore[unresolved-import]
    NSWorkspaceLaunchAndHide,  # ty:ignore[unresolved-import]
)
from pathlib import Path

try:
    import applescript  # type: ignore[import]

    def maybe_reveal_hotkey_window(is_hotkey: bool):
        apple_script = applescript.AppleScript(
            path=str(Path(__file__).parent / "applescripts" / "iterm_osa.scpt")
        )
        result = apple_script.run(is_hotkey)
        return result
except ImportError:
    def maybe_reveal_hotkey_window(is_hotkey: bool):
        raise ImportError(
            "The 'applescript' package is required to reveal the hotkey window. "
            "Install it using 'uv add --extra=applescript'."
        )


def activate_iterm_app() -> None:
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
