import subprocess


def reveal_hotkey_window():
    """Reveal the iTerm2 hotkey window using AppleScript."""
    script = """
    tell application "iTerm2"
        tell current window
            reveal hotkey window
        end tell
    end tell
    """
    subprocess.run(["osascript", "-e", script], check=True)

