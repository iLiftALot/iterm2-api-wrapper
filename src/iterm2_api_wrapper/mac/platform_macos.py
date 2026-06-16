from __future__ import annotations

from pathlib import Path


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
