from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum, nonmember
from typing import TYPE_CHECKING, ClassVar, Literal, Tuple, TypeAlias, TypedDict, cast, overload

from iterm2 import app, profile, prompt, session, tab, window, capabilities


if TYPE_CHECKING:
    from iterm2.api_pb2 import GetPromptResponse

    from iterm2_api_wrapper.connection import Connection


class iTermSetupKwargs(TypedDict, total=False):
    new_tab: bool
    """Whether to open a new tab for the session."""
    dedicated_profile_name: str | None
    """If provided, the name of the profile to use for the session.
        If not provided, the current profile will be used."""
    debug: bool
    """Whether to enable debug logging."""


class iTermStateKwargs(TypedDict, total=True):
    connection: Connection
    app: App
    window: Window
    tab: Tab
    session: Session
    profile: Profile

    is_hotkey_window: bool
    """Whether the current window is a hotkey window."""


class HexCode(StrEnum):
    def __new__(cls, codepoint: int) -> HexCode:
        length = (codepoint.bit_length() + 7) // 8 or 1
        chars = codepoint.to_bytes(length, "big").decode("latin-1")
        obj = str.__new__(cls, chars)
        obj._value_ = chars
        return obj

    # ── C0 control bytes (Ctrl-<key>) ────────────────────────────────
    CNTRL_A = 0x01
    """Move to start of line (readline: beginning-of-line)"""
    CNTRL_B = 0x02
    """Move back one character"""
    CNTRL_C = 0x03
    """Interrupt (SIGINT)"""
    CNTRL_D = 0x04
    """EOF / delete char to the right"""
    CNTRL_E = 0x05
    """Move to end of line"""
    CNTRL_F = 0x06
    """Move forward one character"""
    CNTRL_G = 0x07
    """Bell / abort current edit"""
    CNTRL_H = 0x08
    """Backspace (delete char to the left)"""
    CNTRL_I = 0x09
    """Tab / complete"""
    CNTRL_J = 0x0A
    """Line feed (newline / accept line)"""
    CNTRL_K = 0x0B
    """Delete from cursor to end of line"""
    CNTRL_L = 0x0C
    """Clear screen"""
    CNTRL_M = 0x0D
    """Carriage return (accept line)"""
    CNTRL_N = 0x0E
    """Next history entry"""
    CNTRL_O = 0x0F
    """Operate-and-get-next"""
    CNTRL_P = 0x10
    """Previous history entry"""
    CNTRL_Q = 0x11
    """Resume output (XON)"""
    CNTRL_R = 0x12
    """Reverse incremental history search"""
    CNTRL_S = 0x13
    """Forward incremental search (XOFF on some terms)"""
    CNTRL_T = 0x14
    """Transpose characters"""
    CNTRL_U = 0x15
    """Delete entire line (or to start, shell-dependent)"""
    CNTRL_V = 0x16
    """Quoted insert (literal next)"""
    CNTRL_W = 0x17
    """Delete word to the left"""
    CNTRL_X = 0x18
    """Prefix key for extended bindings"""
    CNTRL_Y = 0x19
    """Yank (paste killed text)"""
    CNTRL_Z = 0x1A
    """Suspend (SIGTSTP)"""
    CNTRL_BACKSLASH = 0x1C
    """Quit (SIGQUIT)"""
    CNTRL_RBRACKET = 0x1D
    """Group separator / tmux-style escape"""
    CNTRL_UNDERSCORE = 0x1F
    """Undo (readline)"""

    # ── Standalone keys ──────────────────────────────────────────────
    A = 0x61
    B = 0x62
    C = 0x63
    D = 0x64
    E = 0x65
    F = 0x66
    G = 0x67
    H = 0x68
    I = 0x69  # noqa: E741
    J = 0x6A
    K = 0x6B
    L = 0x6C
    M = 0x6D
    N = 0x6E
    O = 0x6F  # noqa: E741
    P = 0x70
    Q = 0x71
    R = 0x72
    S = 0x73
    T = 0x74
    U = 0x75
    V = 0x76
    W = 0x77
    X = 0x78
    Y = 0x79
    Z = 0x7A
    ESCAPE = ESC = 0x1B
    """Escape"""
    TAB = 0x09
    """Tab"""
    RETURN = ENTER = 0x0D
    """Carriage return"""
    NEWLINE = LINE_FEED = 0x0A
    """Line feed"""
    BACKSPACE = 0x08
    """Backspace (BS)"""
    DELETE = DEL = 0x7F
    """Delete (DEL / rubout)"""
    SPACE = 0x20
    """Space"""
    NUL = 0x00
    """Null byte"""

    # ── Meta / Alt sequences (ESC + char) ────────────────────────────
    ESCAPE_B = ESC_B = ALT_B = 0x1B62
    """Move back one word"""
    ESCAPE_F = ESC_F = ALT_F = 0x1B66
    """Move forward one word"""
    ESCAPE_D = ESC_D = ALT_D = 0x1B64
    """Delete word to the right"""
    ALT_BACKSPACE = 0x1B7F
    """Delete word to the left"""
    ALT_DOT = 0x1B2E
    """Insert last argument of previous command"""
    ALT_U = 0x1B75
    """Uppercase word"""
    ALT_L = 0x1B6C
    """Lowercase word"""
    ALT_C = 0x1B63
    """Capitalize word"""
    ALT_T = 0x1B74
    """Transpose words"""

    # ── Cursor / navigation (ESC [ X) ────────────────────────────────
    UP = ARROW_UP = 0x1B5B41
    """Cursor up — \\x1b[A"""
    DOWN = ARROW_DOWN = 0x1B5B42
    """Cursor down — \\x1b[B"""
    RIGHT = ARROW_RIGHT = 0x1B5B43
    """Cursor right — \\x1b[C"""
    LEFT = ARROW_LEFT = 0x1B5B44
    """Cursor left — \\x1b[D"""
    HOME = 0x1B5B48
    """Home — \\x1b[H"""
    END = 0x1B5B46
    """End — \\x1b[F"""

    # ── Application cursor mode / DECCKM (ESC O X) ───────────────────
    # Sent when the app enables application cursor keys (ESC [ ? 1 h),
    # e.g. vim, less, some shells. Differs from the CSI forms only in
    # byte 2: O (0x4f, SS3) instead of [ (0x5b, CSI).
    APP_UP = 0x1B4F41
    """Cursor up (app mode) — \\x1bOA"""
    APP_DOWN = 0x1B4F42
    """Cursor down (app mode) — \\x1bOB"""
    APP_RIGHT = 0x1B4F43
    """Cursor right (app mode) — \\x1bOC"""
    APP_LEFT = 0x1B4F44
    """Cursor left (app mode) — \\x1bOD"""
    APP_HOME = 0x1B4F48
    """Home (app mode) — \\x1bOH"""
    APP_END = 0x1B4F46
    """End (app mode) — \\x1bOF"""

    # ── Editing / paging (ESC [ N ~) ─────────────────────────────────
    INSERT = 0x1B5B327E
    """Insert — \\x1b[2~"""
    DELETE_KEY = 0x1B5B337E
    """Forward delete — \\x1b[3~"""
    PAGE_UP = 0x1B5B357E
    """Page up — \\x1b[5~"""
    PAGE_DOWN = 0x1B5B367E
    """Page down — \\x1b[6~"""
    HOME_TILDE = 0x1B5B317E
    """Home (alt form) — \\x1b[1~"""
    END_TILDE = 0x1B5B347E
    """End (alt form) — \\x1b[4~"""

    # ── Function keys ────────────────────────────────────────────────
    F1 = 0x1B4F50
    """\\x1bOP"""
    F2 = 0x1B4F51
    """\\x1bOQ"""
    F3 = 0x1B4F52
    """\\x1bOR"""
    F4 = 0x1B4F53
    """\\x1bOS"""
    F5 = 0x1B5B31357E
    """\\x1b[15~"""
    F6 = 0x1B5B31377E
    """\\x1b[17~"""
    F7 = 0x1B5B31387E
    """\\x1b[18~"""
    F8 = 0x1B5B31397E
    """\\x1b[19~"""
    F9 = 0x1B5B32307E
    """\\x1b[20~"""
    F10 = 0x1B5B32317E
    """\\x1b[21~"""
    F11 = 0x1B5B32337E
    """\\x1b[23~"""
    F12 = 0x1B5B32347E
    """\\x1b[24~"""


# fmt: off
HexCodeValue: TypeAlias = Literal[
    # ── C0 control bytes (Ctrl-<key>) ────────────────────────────────
    "CNTRL_A", "CNTRL_B", "CNTRL_C", "CNTRL_D", "CNTRL_E", "CNTRL_F", "CNTRL_G",
    "CNTRL_H", "CNTRL_I", "CNTRL_J", "CNTRL_K", "CNTRL_L", "CNTRL_M", "CNTRL_N",
    "CNTRL_O", "CNTRL_P", "CNTRL_Q", "CNTRL_R", "CNTRL_S", "CNTRL_T", "CNTRL_U",
    "CNTRL_V", "CNTRL_W", "CNTRL_X", "CNTRL_Y", "CNTRL_Z",
    "CNTRL_BACKSLASH", "CNTRL_RBRACKET", "CNTRL_UNDERSCORE",
    # ── Standalone keys ──────────────────────────────────────────────
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
    "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
    "ESCAPE", "ESC",
    "TAB",
    "RETURN", "ENTER",
    "NEWLINE", "LINE_FEED",
    "BACKSPACE",
    "DELETE", "DEL",
    "SPACE",
    "NUL",
    # ── Meta / Alt sequences (ESC + char) ────────────────────────────
    "ESCAPE_B", "ESC_B", "ALT_B",
    "ESCAPE_F", "ESC_F", "ALT_F",
    "ESCAPE_D", "ESC_D", "ALT_D",
    "ALT_BACKSPACE", "ALT_DOT", "ALT_U", "ALT_L", "ALT_C", "ALT_T",
    # ── Cursor / navigation (ESC [ X) ────────────────────────────────
    "UP", "ARROW_UP",
    "DOWN", "ARROW_DOWN",
    "RIGHT", "ARROW_RIGHT",
    "LEFT", "ARROW_LEFT",
    "HOME", "END",
    # ── Application cursor mode / DECCKM (ESC O X) ───────────────────
    "APP_UP", "APP_DOWN", "APP_RIGHT", "APP_LEFT", "APP_HOME", "APP_END",
    # ── Editing / paging (ESC [ N ~) ─────────────────────────────────
    "INSERT", "DELETE_KEY", "PAGE_UP", "PAGE_DOWN", "HOME_TILDE", "END_TILDE",
    # ── Function keys ────────────────────────────────────────────────
    "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
]
"""All member names (including aliases) of :class:`HexCode`, for name-based autocomplete."""
# fmt: on


class CommandExitCode(IntEnum):
    """
    Known shell-level command exit statuses.

    This enum is intentionally non-exhaustive. Many exit statuses are
    utility-specific, so unknown values should remain raw ints.

    POSIX shell-level conventions:
    - 0: success
    - 1: general error
    - 126: found but not executable
    - 127: command not found
    - 128: unrecoverable shell read error
    - >128: signal-related status, implementation-defined

    zsh specifically uses:
    - 128 + signal number
    """

    SUCCESS = 0
    """Command completed successfully."""
    GENERAL_FAILURE = 1
    """Conventional generic failure status. The exact meaning is utility-specific."""
    MISUSE_ERROR = 2
    """Conventional shell misuse/syntax status. The exact meaning is shell/utility-specific."""
    NOT_EXECUTABLE = 126
    """A file to be executed was found, but it was not an executable utility."""
    NOT_FOUND = 127
    """A utility to be executed was not found."""
    SHELL_READ_ERROR = 128
    """The shell detected an unrecoverable read error while reading commands."""

    # Common zsh/common-shell signal-derived statuses.
    SIGINT = 130
    """SIGINT: interrupt signal, commonly Ctrl+C."""
    SIGKILL = 137
    """SIGKILL: process was forcefully killed."""
    SIGPIPE = 141
    """SIGPIPE: broken pipe."""
    SIGTERM = 143
    """SIGTERM: graceful termination request."""

    @classmethod
    def coerce(cls, code: int) -> CommandExitCode | int:
        """
        Convert a raw integer exit status to a known enum member when possible.

        Unknown utility-specific statuses are returned unchanged.
        """
        try:
            return cls(code)
        except ValueError:
            return code


@dataclass
class CommandStatus:
    prompt_id: str | None
    command: str | None
    exit_code: CommandExitCode | int
    timed_out: bool = False

    ExitCode: ClassVar[type[CommandExitCode]] = CommandExitCode

    def __post_init__(self) -> None:
        """
        Normalize real command exit codes into CommandExitCode when known.

        Timeout statuses are intentionally not coerced. A timeout is wrapper state,
        not a process exit status.
        """
        if self.timed_out:
            return

        if not isinstance(self.exit_code, CommandExitCode):
            self.exit_code = CommandExitCode.coerce(self.exit_code)

    @property
    def code(self) -> int:
        """Return the numeric exit code."""
        return int(self.exit_code)

    @property
    def succeeded(self) -> bool:
        """Whether the command exited successfully."""
        return not self.timed_out and self.code == CommandExitCode.SUCCESS

    @property
    def failed(self) -> bool:
        """Whether the command failed or timed out."""
        return not self.succeeded

    @property
    def known_exit_code(self) -> CommandExitCode | None:
        """Return the enum value if this status is a known command exit code."""
        if self.timed_out:
            return None

        if isinstance(self.exit_code, CommandExitCode):
            return self.exit_code

        return None

    @property
    def was_signaled(self) -> bool:
        """
        Whether this looks like a signal-derived shell status.

        POSIX only requires signal-related statuses to be greater than 128.
        zsh specifically uses 128 + signal number.
        """
        return not self.timed_out and self.code > 128

    @property
    def signal_number(self) -> int | None:
        """
        Interpret this as a zsh/common-shell signal status.

        POSIX only requires signal-related statuses to be greater than 128;
        zsh specifically uses 128 + signal number.
        """
        if self.was_signaled:
            return self.code - 128

        return None


@overload
def PrefixedEnum(EnumT: None, prefix: str) -> type[StrEnum]: ...
@overload
def PrefixedEnum[T: StrEnum](EnumT: type[T], prefix=None) -> type[T]: ...
def PrefixedEnum(EnumT: type[StrEnum] | None, prefix: str | None = None) -> type[StrEnum]:
    if EnumT is None:

        class _PrefixedStrEnum(StrEnum):
            @staticmethod
            def _generate_next_value_(name, start, count, last_values) -> str:
                return f"{prefix}.{name}"

        return _PrefixedStrEnum

    actual_prefix = prefix or EnumT.__name__.removeprefix("__")
    members = {m.name: f"{actual_prefix}.{m.value}" for m in EnumT if m.value != "*"}
    # Pure-wildcard contexts (e.g. UserVar) have no concrete members; keep the
    # wildcard itself, prefixed, so e.g. SessionVar.user.all -> "user.*".
    if not members:
        members = {m.name: f"{actual_prefix}.*" for m in EnumT if m.value == "*"}
    # print(EnumT.__name__, json.dumps(members, indent=4), sep="\n")
    return cast(type[StrEnum], StrEnum(f"_{EnumT.__name__}Prefixed", names=members))


# NOTE: Check https://iterm2.com/documentation-variables.html for potential updates

type VariableContext = Literal["iterm2", "window", "tab", "session", "user"]

SessionVars: TypeAlias = Literal[
    "*",  # - All possible session variables.
    # Session Name
    "autoNameFormat",  # - This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created.
    "autoName",  # - The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is.
    "name",  # - The formatted name as it appears in the tab bar (excluding tmux integration decoration). For example, if the profile is configured to show the session name and job, this would take a value like My Profile (vim).
    "presentationName",  # - The session name exactly as it appears in the session title bar.
    "terminalIconName",  # - The "icon" title, as set by the control sequence OSC 0 or OSC 1.
    "terminalWindowName",  # - The "window" title, as set by the control sequence OSC 0 or OSC 2.
    "triggerName",  # - The last session name set by a trigger.
    # Terminal
    "columns",  # - Session's width in columns
    "commandLine",  # - Command line of the current foreground job (job name including arguments)
    "jobName",  # - The name of the current foreground job (e.g., "emacs")
    "jobPid",  # - The process ID of the current foreground job in this session.
    "mouseReportingMode",  # - A number indicating how mouse events are reported. -1: Not reported, 0: button clicks reported, 1: not currently implemented, 2: reports clicks and drags, 3: reports clicks, drags, and movement
    "pid",  # - The process ID of the root process in this session (typically login).
    "processTitle",  # - The (perhaps modified by the process) title of a process from its argv.
    "rows",  # - The session's height in rows
    "selection",  # - The currently selected text.
    "selectionLength",  # - The length in UTF-8 bytes of the currently selected text.
    "termid",  # - Window, tab, and pane number as used in the $TERM_SESSION_ID environment variable.
    "tty",  # - The path to the local TTY device
    "uname",  # - Information about the operating system on the current host.
    "shell",  # - The shell on the current host.
    "sshIntegrationLevel",  # - 0: No ssh integration. 1: Basic ssh integration. 2: Full ssh integration with all features available.
    "homeDirectory",  # - The home directory on the current host.
    "applicationKeypad",  # - A boolean indicating if the session is in application keypad mode.
    "mouseInfo",  # - Describes the last mouse event. Is an array: [x coord, y coord, button number, click count, array of modifiers, bitmask of side effects, event type].
    "bellCount",  # - Number of times the bell has rung.
    # Shell Integration
    "hostname",  # - The current hostname
    "lastCommand",  # - The last command run in the session
    "path",  # - The current working directory (this works without shell integration, but not if you ssh elsewhere)
    "username",  # - The current user name
    # Logging
    "autoLogId",  # - When automatic logging is enabled, this is the random number portion of the filename.
    "creationTimeString",  # - A string giving the initial creation time of the session, used as part of the filename when automatic logging is enabled
    "logFilename",  # - If set, the filename that logging goes to. If unset, logging is off. New in version 3.4.7.
    # tmux Integration
    "tmuxClientName",  # - The name of the tmux session when tmux integration is in use (e.g., user@localhost).
    "tmuxPaneTitle",  # - The title of the tmux window pane.
    "tmuxRole",  # - Unset if tmux integration is not in use. Otherwise, is "gateway" for the session in which tmux -CC is running or "client" in tmux integration sessions.
    "tmuxStatusLeft",  # - In tmux integration, the value of the left side of the status bar.
    "tmuxStatusRight",  # - In tmux integration, the value of the right side of the status bar.
    "tmuxWindowPane",  # - In tmux integration, this gives the window pane number.
    "tmuxWindowTitle",  # - If tmux integration is in use, this gives the name of the window title from tmux.
    "tmuxWindowPaneIndex",  # - In tmux integration, this gives the index of the window pane. It corresponds to the pane_index property in tmux.
    # Other
    "badge",  # - The value of the badge. Note that the user can enter an interpolated string in the UI, but this value contains the string result of evaluating it.
    "id",  # - A unique identifier for the session
    "profileName",  # - The name of the current profile.
    # Runtime (undocumented; not in iTerm2 variable docs)
    "showingAlternateScreen",  # - "1" if the alternate screen buffer is active (e.g., a full-screen TUI like vim or less), otherwise "0".
    "effective_root_pid",  # - The process ID of the effective root process of the session.
    "foregroundJobAncestors",  # - A newline-delimited list of the foreground job's ancestor process names.
    "isBroadcastSource",  # - "1" if this session is currently a source for input broadcasting, otherwise "0".
    # > References to Other Contexts
    # parentSession (-> session context)
    "parentSession.autoNameFormat",
    "parentSession.autoName",
    "parentSession.name",
    "parentSession.presentationName",
    "parentSession.terminalIconName",
    "parentSession.terminalWindowName",
    "parentSession.triggerName",
    "parentSession.columns",
    "parentSession.commandLine",
    "parentSession.jobName",
    "parentSession.jobPid",
    "parentSession.mouseReportingMode",
    "parentSession.pid",
    "parentSession.processTitle",
    "parentSession.rows",
    "parentSession.selection",
    "parentSession.selectionLength",
    "parentSession.termid",
    "parentSession.tty",
    "parentSession.uname",
    "parentSession.shell",
    "parentSession.sshIntegrationLevel",
    "parentSession.homeDirectory",
    "parentSession.applicationKeypad",
    "parentSession.mouseInfo",
    "parentSession.bellCount",
    "parentSession.hostname",
    "parentSession.lastCommand",
    "parentSession.path",
    "parentSession.username",
    "parentSession.autoLogId",
    "parentSession.creationTimeString",
    "parentSession.logFilename",
    "parentSession.tmuxClientName",
    "parentSession.tmuxPaneTitle",
    "parentSession.tmuxRole",
    "parentSession.tmuxStatusLeft",
    "parentSession.tmuxStatusRight",
    "parentSession.tmuxWindowPane",
    "parentSession.tmuxWindowTitle",
    "parentSession.tmuxWindowPaneIndex",
    "parentSession.badge",
    "parentSession.id",
    "parentSession.profileName",
    "parentSession.showingAlternateScreen",
    "parentSession.effective_root_pid",
    "parentSession.foregroundJobAncestors",
    "parentSession.isBroadcastSource",
    "parentSession.tab.id",
    "parentSession.tab.titleOverrideFormat",
    "parentSession.tab.titleOverride",
    "parentSession.tab.tmuxWindow",
    "parentSession.tab.tmuxWindowTitle",
    "parentSession.tab.tmuxWindowName",
    "parentSession.tab.title",
    "parentSession.iterm2.effectiveTheme",
    "parentSession.iterm2.localhostName",
    "parentSession.iterm2.pid",
    "parentSession.iterm2.appBundlePath",
    "parentSession.user.*",
    # tab (-> tab context)
    "tab.id",
    "tab.titleOverrideFormat",
    "tab.titleOverride",
    "tab.tmuxWindow",
    "tab.tmuxWindowTitle",
    "tab.tmuxWindowName",
    "tab.title",
    "tab.iterm2.effectiveTheme",
    "tab.iterm2.localhostName",
    "tab.iterm2.pid",
    "tab.iterm2.appBundlePath",
    "tab.window.titleOverride",
    "tab.window.titleOverrideFormat",
    "tab.window.id",
    "tab.window.frame",
    "tab.window.style",
    "tab.window.number",
    "tab.window.isHotkeyWindow",
    # iterm2 (-> global context)
    "iterm2.effectiveTheme",
    "iterm2.localhostName",
    "iterm2.pid",
    "iterm2.appBundlePath",
    # user (-> user context)
    "user.*",
]
"""Defined in the context of a session"""

TabVars: TypeAlias = Literal[
    "*",  # - All possible tab variables.
    # Tab Context
    "id",  # - The unique identifier for this tab.
    "titleOverrideFormat",  # - An interpolated string giving the title to use for the tab. If not set, the session's title will be used. Note the session's title is configurable in Prefs > Profiles > General > Title and is not necessarily equal to the autoName, but may be derived from it (or not).
    "titleOverride",  # - The value of titleOverrideFormat after evaluating it as an interpolated string.
    "tmuxWindow",  # - In tmux integration, this is the tmux window number this tab represents.
    "tmuxWindowTitle",  # - In tmux integration, this is the tmux window title. It will only be set if the tmux option set-title is on. It comes from evaluating the tmux set-titles-strings option.
    "tmuxWindowName",  # - In tmux integration, this is the tmux window name.
    "title",  # - The fully formatted title as it appears in the tab bar.
    # > References to Other Contexts
    # currentSession (-> session context)
    "currentSession.autoNameFormat",
    "currentSession.autoName",
    "currentSession.name",
    "currentSession.presentationName",
    "currentSession.terminalIconName",
    "currentSession.terminalWindowName",
    "currentSession.triggerName",
    "currentSession.columns",
    "currentSession.commandLine",
    "currentSession.jobName",
    "currentSession.jobPid",
    "currentSession.mouseReportingMode",
    "currentSession.pid",
    "currentSession.processTitle",
    "currentSession.rows",
    "currentSession.selection",
    "currentSession.selectionLength",
    "currentSession.termid",
    "currentSession.tty",
    "currentSession.uname",
    "currentSession.shell",
    "currentSession.sshIntegrationLevel",
    "currentSession.homeDirectory",
    "currentSession.applicationKeypad",
    "currentSession.mouseInfo",
    "currentSession.bellCount",
    "currentSession.hostname",
    "currentSession.lastCommand",
    "currentSession.path",
    "currentSession.username",
    "currentSession.autoLogId",
    "currentSession.creationTimeString",
    "currentSession.logFilename",
    "currentSession.tmuxClientName",
    "currentSession.tmuxPaneTitle",
    "currentSession.tmuxRole",
    "currentSession.tmuxStatusLeft",
    "currentSession.tmuxStatusRight",
    "currentSession.tmuxWindowPane",
    "currentSession.tmuxWindowTitle",
    "currentSession.tmuxWindowPaneIndex",
    "currentSession.badge",
    "currentSession.id",
    "currentSession.profileName",
    "currentSession.showingAlternateScreen",
    "currentSession.effective_root_pid",
    "currentSession.foregroundJobAncestors",
    "currentSession.isBroadcastSource",
    "currentSession.parentSession.autoNameFormat",
    "currentSession.parentSession.autoName",
    "currentSession.parentSession.name",
    "currentSession.parentSession.presentationName",
    "currentSession.parentSession.terminalIconName",
    "currentSession.parentSession.terminalWindowName",
    "currentSession.parentSession.triggerName",
    "currentSession.parentSession.columns",
    "currentSession.parentSession.commandLine",
    "currentSession.parentSession.jobName",
    "currentSession.parentSession.jobPid",
    "currentSession.parentSession.mouseReportingMode",
    "currentSession.parentSession.pid",
    "currentSession.parentSession.processTitle",
    "currentSession.parentSession.rows",
    "currentSession.parentSession.selection",
    "currentSession.parentSession.selectionLength",
    "currentSession.parentSession.termid",
    "currentSession.parentSession.tty",
    "currentSession.parentSession.uname",
    "currentSession.parentSession.shell",
    "currentSession.parentSession.sshIntegrationLevel",
    "currentSession.parentSession.homeDirectory",
    "currentSession.parentSession.applicationKeypad",
    "currentSession.parentSession.mouseInfo",
    "currentSession.parentSession.bellCount",
    "currentSession.parentSession.hostname",
    "currentSession.parentSession.lastCommand",
    "currentSession.parentSession.path",
    "currentSession.parentSession.username",
    "currentSession.parentSession.autoLogId",
    "currentSession.parentSession.creationTimeString",
    "currentSession.parentSession.logFilename",
    "currentSession.parentSession.tmuxClientName",
    "currentSession.parentSession.tmuxPaneTitle",
    "currentSession.parentSession.tmuxRole",
    "currentSession.parentSession.tmuxStatusLeft",
    "currentSession.parentSession.tmuxStatusRight",
    "currentSession.parentSession.tmuxWindowPane",
    "currentSession.parentSession.tmuxWindowTitle",
    "currentSession.parentSession.tmuxWindowPaneIndex",
    "currentSession.parentSession.badge",
    "currentSession.parentSession.id",
    "currentSession.parentSession.profileName",
    "currentSession.parentSession.showingAlternateScreen",
    "currentSession.parentSession.effective_root_pid",
    "currentSession.parentSession.foregroundJobAncestors",
    "currentSession.parentSession.isBroadcastSource",
    "currentSession.parentSession.user.*",
    "currentSession.iterm2.effectiveTheme",
    "currentSession.iterm2.localhostName",
    "currentSession.iterm2.pid",
    "currentSession.iterm2.appBundlePath",
    "currentSession.user.*",
    # iterm2 (-> global context)
    "iterm2.effectiveTheme",
    "iterm2.localhostName",
    "iterm2.pid",
    "iterm2.appBundlePath",
    # window (-> window context)
    "window.titleOverride",
    "window.titleOverrideFormat",
    "window.id",
    "window.frame",
    "window.style",
    "window.number",
    "window.isHotkeyWindow",
    "window.iterm2.effectiveTheme",
    "window.iterm2.localhostName",
    "window.iterm2.pid",
    "window.iterm2.appBundlePath",
]
"""Defined in the context of a tab"""

WindowVars: TypeAlias = Literal[
    "*",  # - All possible window variables.
    # Window Title
    "titleOverride",  # - The value from evaluating the interpeted string in titleOverrideFormat, if set.
    "titleOverrideFormat",  # - The window's interpolated string title. If not set, the current tab's title is used.
    # Other
    "id",  # - The window ID.
    "frame",  # - An array of integers giving the x origin, y origin, width, and height.
    "style",  # - The window style. Takes one of these values: normal, non-native full screen, native full screen, full-width top, full-width bottom, full-height left, full-height right, bottom, top, left, right, no-title-bar, compact, accessory.
    "number",  # - The window number. Corresponds to the keyboard shortcut that switches to the window. Begins at 1. Unlike the keyboard shortcut, this is set even if the number is larger than 9.
    "isHotkeyWindow",  # - A boolean indicating if this is a hotkey window.
    # > References to Other Contexts
    # currentTab (-> tab context)
    "currentTab.id",
    "currentTab.titleOverrideFormat",
    "currentTab.titleOverride",
    "currentTab.tmuxWindow",
    "currentTab.tmuxWindowTitle",
    "currentTab.tmuxWindowName",
    "currentTab.title",
    "currentTab.currentSession.autoNameFormat",
    "currentTab.currentSession.autoName",
    "currentTab.currentSession.name",
    "currentTab.currentSession.presentationName",
    "currentTab.currentSession.terminalIconName",
    "currentTab.currentSession.terminalWindowName",
    "currentTab.currentSession.triggerName",
    "currentTab.currentSession.columns",
    "currentTab.currentSession.commandLine",
    "currentTab.currentSession.jobName",
    "currentTab.currentSession.jobPid",
    "currentTab.currentSession.mouseReportingMode",
    "currentTab.currentSession.pid",
    "currentTab.currentSession.processTitle",
    "currentTab.currentSession.rows",
    "currentTab.currentSession.selection",
    "currentTab.currentSession.selectionLength",
    "currentTab.currentSession.termid",
    "currentTab.currentSession.tty",
    "currentTab.currentSession.uname",
    "currentTab.currentSession.shell",
    "currentTab.currentSession.sshIntegrationLevel",
    "currentTab.currentSession.homeDirectory",
    "currentTab.currentSession.applicationKeypad",
    "currentTab.currentSession.mouseInfo",
    "currentTab.currentSession.bellCount",
    "currentTab.currentSession.hostname",
    "currentTab.currentSession.lastCommand",
    "currentTab.currentSession.path",
    "currentTab.currentSession.username",
    "currentTab.currentSession.autoLogId",
    "currentTab.currentSession.creationTimeString",
    "currentTab.currentSession.logFilename",
    "currentTab.currentSession.tmuxClientName",
    "currentTab.currentSession.tmuxPaneTitle",
    "currentTab.currentSession.tmuxRole",
    "currentTab.currentSession.tmuxStatusLeft",
    "currentTab.currentSession.tmuxStatusRight",
    "currentTab.currentSession.tmuxWindowPane",
    "currentTab.currentSession.tmuxWindowTitle",
    "currentTab.currentSession.tmuxWindowPaneIndex",
    "currentTab.currentSession.badge",
    "currentTab.currentSession.id",
    "currentTab.currentSession.profileName",
    "currentTab.currentSession.showingAlternateScreen",
    "currentTab.currentSession.effective_root_pid",
    "currentTab.currentSession.foregroundJobAncestors",
    "currentTab.currentSession.isBroadcastSource",
    "currentTab.currentSession.user.*",
    "currentTab.iterm2.effectiveTheme",
    "currentTab.iterm2.localhostName",
    "currentTab.iterm2.pid",
    "currentTab.iterm2.appBundlePath",
    # iterm2 (-> global context)
    "iterm2.effectiveTheme",
    "iterm2.localhostName",
    "iterm2.pid",
    "iterm2.appBundlePath",
]
"""Defined in the context of a window"""

UserVars: TypeAlias = Literal["*"] | str
"""
The only variables that users may directly control are those in the "user" scope of a session.
For example, you could set a variable named "gitBranch" to the name of the current git branch.
This value would then be available to display in the session title, badge, or other places,
and would be available to Python API scripts. You'd reference it as user.gitBranch.

See "Setting User-Defined Variables" in Scripting Fundamentals for details on setting them.
"""

GlobalVars: TypeAlias = Literal[
    "*",  # - All possible global variables.
    "effectiveTheme",  # - A space-delimited list of words describing the OS theme (e.g., "dark", "light highContrast", "dark minimal")
    "localhostName",  # - The best guess of what localhost's hostname is
    "pid",  # - The process ID of the iTerm2 app
    "appBundlePath",  # - The path to the iTerm.app executable.
]
"""Defined in the global context"""


class SessionEnum(StrEnum):
    all = "*"
    autoNameFormat = "autoNameFormat"
    autoName = "autoName"
    sessionName = "name"
    presentationName = "presentationName"
    terminalIconName = "terminalIconName"
    terminalWindowName = "terminalWindowName"
    triggerName = "triggerName"
    columns = "columns"
    commandLine = "commandLine"
    jobName = "jobName"
    jobPid = "jobPid"
    mouseReportingMode = "mouseReportingMode"
    pid = "pid"
    processTitle = "processTitle"
    rows = "rows"
    selection = "selection"
    selectionLength = "selectionLength"
    termid = "termid"
    tty = "tty"
    uname = "uname"
    shell = "shell"
    sshIntegrationLevel = "sshIntegrationLevel"
    homeDirectory = "homeDirectory"
    applicationKeypad = "applicationKeypad"
    mouseInfo = "mouseInfo"
    bellCount = "bellCount"
    hostname = "hostname"
    lastCommand = "lastCommand"
    path = "path"
    username = "username"
    autoLogId = "autoLogId"
    creationTimeString = "creationTimeString"
    logFilename = "logFilename"
    tmuxClientName = "tmuxClientName"
    tmuxPaneTitle = "tmuxPaneTitle"
    tmuxRole = "tmuxRole"
    tmuxStatusLeft = "tmuxStatusLeft"
    tmuxStatusRight = "tmuxStatusRight"
    tmuxWindowPane = "tmuxWindowPane"
    tmuxWindowTitle = "tmuxWindowTitle"
    tmuxWindowPaneIndex = "tmuxWindowPaneIndex"
    badge = "badge"
    id = "id"
    profileName = "profileName"
    # Runtime (undocumented)
    showingAlternateScreen = "showingAlternateScreen"
    effective_root_pid = "effective_root_pid"
    foregroundJobAncestors = "foregroundJobAncestors"
    isBroadcastSource = "isBroadcastSource"


class TabEnum(StrEnum):
    all = "*"
    id = "id"
    titleOverrideFormat = "titleOverrideFormat"
    titleOverride = "titleOverride"
    tmuxWindow = "tmuxWindow"
    tmuxWindowTitle = "tmuxWindowTitle"
    tmuxWindowName = "tmuxWindowName"
    tabTitle = "title"


class WindowEnum(StrEnum):
    all = "*"
    titleOverride = "titleOverride"
    titleOverrideFormat = "titleOverrideFormat"
    id = "id"
    frame = "frame"
    style = "style"
    number = "number"
    isHotkeyWindow = "isHotkeyWindow"


class UserEnum(StrEnum):
    all = "*"


class GlobalVar(StrEnum):
    """Defined in the global context"""

    all = "*"
    """All possible global variables."""
    effectiveTheme = "effectiveTheme"
    """A space-delimited list of words describing the OS theme (e.g., "dark", "light highContrast", "dark minimal")"""
    localhostName = "localhostName"
    """The best guess of what localhost's hostname is"""
    pid = "pid"
    """The process ID of the iTerm2 app"""
    appBundlePath = "appBundlePath"
    """The path to the iTerm.app executable."""


class UserVar(StrEnum):
    all = UserEnum.all


# ---------------------------------------------------------------------------
# Reference views: concrete enums that mirror the 2-hop reference paths in the
# literal aliases above so that enum access (e.g. SessionVar.parentSession.tab.title)
# autocompletes and resolves to the correct dotted variable string at runtime.
# Generated to match the literal coverage exactly; do not hand-add deeper paths.
# ---------------------------------------------------------------------------
class _SessionAtCurrentSessionParentSession(StrEnum):
    """Reference view: currentSession.parentSession (the parent of the tab's active session)."""

    autoNameFormat = "currentSession.parentSession.autoNameFormat"
    """This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created."""
    autoName = "currentSession.parentSession.autoName"
    """The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is."""
    sessionName = "currentSession.parentSession.name"
    """The formatted name as it appears in the tab bar (excluding tmux integration decoration). For example, if the profile is configured to show the session name and job, this would take a value like My Profile (vim)."""
    presentationName = "currentSession.parentSession.presentationName"
    """The session name exactly as it appears in the session title bar."""
    terminalIconName = "currentSession.parentSession.terminalIconName"
    """The "icon" title, as set by the control sequence OSC 0 or OSC 1."""
    terminalWindowName = "currentSession.parentSession.terminalWindowName"
    """The "window" title, as set by the control sequence OSC 0 or OSC 2."""
    triggerName = "currentSession.parentSession.triggerName"
    """The last session name set by a trigger."""
    columns = "currentSession.parentSession.columns"
    """Session's width in columns"""
    commandLine = "currentSession.parentSession.commandLine"
    """Command line of the current foreground job (job name including arguments)"""
    jobName = "currentSession.parentSession.jobName"
    """The name of the current foreground job (e.g., "emacs")"""
    jobPid = "currentSession.parentSession.jobPid"
    """The process ID of the current foreground job in this session."""
    mouseReportingMode = "currentSession.parentSession.mouseReportingMode"
    """A number indicating how mouse events are reported. -1: Not reported, 0: button clicks reported, 1: not currently implemented, 2: reports clicks and drags, 3: reports clicks, drags, and movement"""
    pid = "currentSession.parentSession.pid"
    """The process ID of the root process in this session (typically login)."""
    processTitle = "currentSession.parentSession.processTitle"
    """The (perhaps modified by the process) title of a process from its argv."""
    rows = "currentSession.parentSession.rows"
    """The session's height in rows"""
    selection = "currentSession.parentSession.selection"
    """The currently selected text."""
    selectionLength = "currentSession.parentSession.selectionLength"
    """The length in UTF-8 bytes of the currently selected text."""
    termid = "currentSession.parentSession.termid"
    """Window, tab, and pane number as used in the $TERM_SESSION_ID environment variable."""
    tty = "currentSession.parentSession.tty"
    """The path to the local TTY device"""
    uname = "currentSession.parentSession.uname"
    """Information about the operating system on the current host."""
    shell = "currentSession.parentSession.shell"
    """The shell on the current host."""
    sshIntegrationLevel = "currentSession.parentSession.sshIntegrationLevel"
    """0: No ssh integration. 1: Basic ssh integration. 2: Full ssh integration with all features available."""
    homeDirectory = "currentSession.parentSession.homeDirectory"
    """The home directory on the current host."""
    applicationKeypad = "currentSession.parentSession.applicationKeypad"
    """A boolean indicating if the session is in application keypad mode."""
    mouseInfo = "currentSession.parentSession.mouseInfo"
    """Describes the last mouse event. Is an array: [x coord, y coord, button number, click count, array of modifiers, bitmask of side effects, event type]. x coord is 0-based and gives the location in columns from the leftmost column. y coord is 0 at the first line in history, including lines which have since been lost if there are more lines of history than the maximum. button number is 0 for left, 1 for right, and 2 or greater for other buttons. click count is 1 for single click, 2 for double click, etc., and isn't artifically bounded. array of modifiers contains numbers for each modifier key that is pressed. They keys are: Control = 1; Option = 2; Command = 3; Shift = 4. bitmask of side effects comes by summing these values: Modify selection = 1; Perform action = 2; Open target (e.g., a URL or file) = 4; Report = 8; Move cursor = 16; Move find-on-page start location = 32; Open password manager = 64; Drag = 128. event type is 0 for mouse-up, 1 for mouse-down, 2 for drag."""
    bellCount = "currentSession.parentSession.bellCount"
    """Number of times the bell has rung."""
    hostname = "currentSession.parentSession.hostname"
    """The current hostname"""
    lastCommand = "currentSession.parentSession.lastCommand"
    """The last command run in the session"""
    path = "currentSession.parentSession.path"
    """The current working directory (this works without shell integration, but not if you ssh elsewhere)"""
    username = "currentSession.parentSession.username"
    """The current user name"""
    autoLogId = "currentSession.parentSession.autoLogId"
    """When automatic logging is enabled, this is the random number portion of the filename."""
    creationTimeString = "currentSession.parentSession.creationTimeString"
    """A string giving the initial creation time of the session, used as part of the filename when automatic logging is enabled"""
    logFilename = "currentSession.parentSession.logFilename"
    """If set, the filename that logging goes to. If unset, logging is off. New in version 3.4.7."""
    tmuxClientName = "currentSession.parentSession.tmuxClientName"
    """The name of the tmux session when tmux integration is in use (e.g., user@localhost)."""
    tmuxPaneTitle = "currentSession.parentSession.tmuxPaneTitle"
    """The title of the tmux window pane."""
    tmuxRole = "currentSession.parentSession.tmuxRole"
    """Unset if tmux integration is not in use. Otherwise, is "gateway" for the session in which tmux -CC is running or "client" in tmux integration sessions."""
    tmuxStatusLeft = "currentSession.parentSession.tmuxStatusLeft"
    """In tmux integration, the value of the left side of the status bar."""
    tmuxStatusRight = "currentSession.parentSession.tmuxStatusRight"
    """In tmux integration, the value of the right side of the status bar."""
    tmuxWindowPane = "currentSession.parentSession.tmuxWindowPane"
    """In tmux integration, this gives the window pane number."""
    tmuxWindowTitle = "currentSession.parentSession.tmuxWindowTitle"
    """If tmux integration is in use, this gives the name of the window title from tmux."""
    tmuxWindowPaneIndex = "currentSession.parentSession.tmuxWindowPaneIndex"
    """In tmux integration, this gives the index of the window pane. It corresponds to the pane_index property in tmux."""
    badge = "currentSession.parentSession.badge"
    """The value of the badge. Note that the user can enter an interpolated string in the UI, but this value contains the string result of evaluating it."""
    id = "currentSession.parentSession.id"
    """A unique identifier for the session"""
    profileName = "currentSession.parentSession.profileName"
    """The name of the current profile."""
    showingAlternateScreen = "currentSession.parentSession.showingAlternateScreen"
    """\"1\" if the alternate screen buffer is active (e.g., a full-screen TUI like vim or less), otherwise \"0\"."""
    effective_root_pid = "currentSession.parentSession.effective_root_pid"
    """The process ID of the effective root process of the session."""
    foregroundJobAncestors = "currentSession.parentSession.foregroundJobAncestors"
    """A newline-delimited list of the foreground job's ancestor process names."""
    isBroadcastSource = "currentSession.parentSession.isBroadcastSource"
    """\"1\" if this session is currently a source for input broadcasting, otherwise \"0\"."""

    user = nonmember(PrefixedEnum(UserVar, "currentSession.parentSession.user"))
    """A context for user-set variables. Variables may be set with a custom control sequence or by using the Python scripting API. They are often set when using shell integration. See User-Defined Variables for more information."""


class _SessionAtCurrentTabCurrentSession(StrEnum):
    """Reference view: currentTab.currentSession (the window's active session)."""

    autoNameFormat = "currentTab.currentSession.autoNameFormat"
    """This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created."""
    autoName = "currentTab.currentSession.autoName"
    """The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is."""
    sessionName = "currentTab.currentSession.name"
    """The formatted name as it appears in the tab bar (excluding tmux integration decoration). For example, if the profile is configured to show the session name and job, this would take a value like My Profile (vim)."""
    presentationName = "currentTab.currentSession.presentationName"
    """The session name exactly as it appears in the session title bar."""
    terminalIconName = "currentTab.currentSession.terminalIconName"
    """The "icon" title, as set by the control sequence OSC 0 or OSC 1."""
    terminalWindowName = "currentTab.currentSession.terminalWindowName"
    """The "window" title, as set by the control sequence OSC 0 or OSC 2."""
    triggerName = "currentTab.currentSession.triggerName"
    """The last session name set by a trigger."""
    columns = "currentTab.currentSession.columns"
    """Session's width in columns"""
    commandLine = "currentTab.currentSession.commandLine"
    """Command line of the current foreground job (job name including arguments)"""
    jobName = "currentTab.currentSession.jobName"
    """The name of the current foreground job (e.g., "emacs")"""
    jobPid = "currentTab.currentSession.jobPid"
    """The process ID of the current foreground job in this session."""
    mouseReportingMode = "currentTab.currentSession.mouseReportingMode"
    """A number indicating how mouse events are reported. -1: Not reported, 0: button clicks reported, 1: not currently implemented, 2: reports clicks and drags, 3: reports clicks, drags, and movement"""
    pid = "currentTab.currentSession.pid"
    """The process ID of the root process in this session (typically login)."""
    processTitle = "currentTab.currentSession.processTitle"
    """The (perhaps modified by the process) title of a process from its argv."""
    rows = "currentTab.currentSession.rows"
    """The session's height in rows"""
    selection = "currentTab.currentSession.selection"
    """The currently selected text."""
    selectionLength = "currentTab.currentSession.selectionLength"
    """The length in UTF-8 bytes of the currently selected text."""
    termid = "currentTab.currentSession.termid"
    """Window, tab, and pane number as used in the $TERM_SESSION_ID environment variable."""
    tty = "currentTab.currentSession.tty"
    """The path to the local TTY device"""
    uname = "currentTab.currentSession.uname"
    """Information about the operating system on the current host."""
    shell = "currentTab.currentSession.shell"
    """The shell on the current host."""
    sshIntegrationLevel = "currentTab.currentSession.sshIntegrationLevel"
    """0: No ssh integration. 1: Basic ssh integration. 2: Full ssh integration with all features available."""
    homeDirectory = "currentTab.currentSession.homeDirectory"
    """The home directory on the current host."""
    applicationKeypad = "currentTab.currentSession.applicationKeypad"
    """A boolean indicating if the session is in application keypad mode."""
    mouseInfo = "currentTab.currentSession.mouseInfo"
    """Describes the last mouse event. Is an array: [x coord, y coord, button number, click count, array of modifiers, bitmask of side effects, event type]. x coord is 0-based and gives the location in columns from the leftmost column. y coord is 0 at the first line in history, including lines which have since been lost if there are more lines of history than the maximum. button number is 0 for left, 1 for right, and 2 or greater for other buttons. click count is 1 for single click, 2 for double click, etc., and isn't artifically bounded. array of modifiers contains numbers for each modifier key that is pressed. They keys are: Control = 1; Option = 2; Command = 3; Shift = 4. bitmask of side effects comes by summing these values: Modify selection = 1; Perform action = 2; Open target (e.g., a URL or file) = 4; Report = 8; Move cursor = 16; Move find-on-page start location = 32; Open password manager = 64; Drag = 128. event type is 0 for mouse-up, 1 for mouse-down, 2 for drag."""
    bellCount = "currentTab.currentSession.bellCount"
    """Number of times the bell has rung."""
    hostname = "currentTab.currentSession.hostname"
    """The current hostname"""
    lastCommand = "currentTab.currentSession.lastCommand"
    """The last command run in the session"""
    path = "currentTab.currentSession.path"
    """The current working directory (this works without shell integration, but not if you ssh elsewhere)"""
    username = "currentTab.currentSession.username"
    """The current user name"""
    autoLogId = "currentTab.currentSession.autoLogId"
    """When automatic logging is enabled, this is the random number portion of the filename."""
    creationTimeString = "currentTab.currentSession.creationTimeString"
    """A string giving the initial creation time of the session, used as part of the filename when automatic logging is enabled"""
    logFilename = "currentTab.currentSession.logFilename"
    """If set, the filename that logging goes to. If unset, logging is off. New in version 3.4.7."""
    tmuxClientName = "currentTab.currentSession.tmuxClientName"
    """The name of the tmux session when tmux integration is in use (e.g., user@localhost)."""
    tmuxPaneTitle = "currentTab.currentSession.tmuxPaneTitle"
    """The title of the tmux window pane."""
    tmuxRole = "currentTab.currentSession.tmuxRole"
    """Unset if tmux integration is not in use. Otherwise, is "gateway" for the session in which tmux -CC is running or "client" in tmux integration sessions."""
    tmuxStatusLeft = "currentTab.currentSession.tmuxStatusLeft"
    """In tmux integration, the value of the left side of the status bar."""
    tmuxStatusRight = "currentTab.currentSession.tmuxStatusRight"
    """In tmux integration, the value of the right side of the status bar."""
    tmuxWindowPane = "currentTab.currentSession.tmuxWindowPane"
    """In tmux integration, this gives the window pane number."""
    tmuxWindowTitle = "currentTab.currentSession.tmuxWindowTitle"
    """If tmux integration is in use, this gives the name of the window title from tmux."""
    tmuxWindowPaneIndex = "currentTab.currentSession.tmuxWindowPaneIndex"
    """In tmux integration, this gives the index of the window pane. It corresponds to the pane_index property in tmux."""
    badge = "currentTab.currentSession.badge"
    """The value of the badge. Note that the user can enter an interpolated string in the UI, but this value contains the string result of evaluating it."""
    id = "currentTab.currentSession.id"
    """A unique identifier for the session"""
    profileName = "currentTab.currentSession.profileName"
    """The name of the current profile."""
    showingAlternateScreen = "currentTab.currentSession.showingAlternateScreen"
    """\"1\" if the alternate screen buffer is active (e.g., a full-screen TUI like vim or less), otherwise \"0\"."""
    effective_root_pid = "currentTab.currentSession.effective_root_pid"
    """The process ID of the effective root process of the session."""
    foregroundJobAncestors = "currentTab.currentSession.foregroundJobAncestors"
    """A newline-delimited list of the foreground job's ancestor process names."""
    isBroadcastSource = "currentTab.currentSession.isBroadcastSource"
    """\"1\" if this session is currently a source for input broadcasting, otherwise \"0\"."""

    user = nonmember(PrefixedEnum(UserVar, "currentTab.currentSession.user"))
    """A context for user-set variables. Variables may be set with a custom control sequence or by using the Python scripting API. They are often set when using shell integration. See User-Defined Variables for more information."""


class _SessionAtParentSession(StrEnum):
    """Reference view: parentSession (the session that was current when this session was created)."""

    autoNameFormat = "parentSession.autoNameFormat"
    """This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created."""
    autoName = "parentSession.autoName"
    """The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is."""
    sessionName = "parentSession.name"
    """The formatted name as it appears in the tab bar (excluding tmux integration decoration). For example, if the profile is configured to show the session name and job, this would take a value like My Profile (vim)."""
    presentationName = "parentSession.presentationName"
    """The session name exactly as it appears in the session title bar."""
    terminalIconName = "parentSession.terminalIconName"
    """The "icon" title, as set by the control sequence OSC 0 or OSC 1."""
    terminalWindowName = "parentSession.terminalWindowName"
    """The "window" title, as set by the control sequence OSC 0 or OSC 2."""
    triggerName = "parentSession.triggerName"
    """The last session name set by a trigger."""
    columns = "parentSession.columns"
    """Session's width in columns"""
    commandLine = "parentSession.commandLine"
    """Command line of the current foreground job (job name including arguments)"""
    jobName = "parentSession.jobName"
    """The name of the current foreground job (e.g., "emacs")"""
    jobPid = "parentSession.jobPid"
    """The process ID of the current foreground job in this session."""
    mouseReportingMode = "parentSession.mouseReportingMode"
    """A number indicating how mouse events are reported. -1: Not reported, 0: button clicks reported, 1: not currently implemented, 2: reports clicks and drags, 3: reports clicks, drags, and movement"""
    pid = "parentSession.pid"
    """The process ID of the root process in this session (typically login)."""
    processTitle = "parentSession.processTitle"
    """The (perhaps modified by the process) title of a process from its argv."""
    rows = "parentSession.rows"
    """The session's height in rows"""
    selection = "parentSession.selection"
    """The currently selected text."""
    selectionLength = "parentSession.selectionLength"
    """The length in UTF-8 bytes of the currently selected text."""
    termid = "parentSession.termid"
    """Window, tab, and pane number as used in the $TERM_SESSION_ID environment variable."""
    tty = "parentSession.tty"
    """The path to the local TTY device"""
    uname = "parentSession.uname"
    """Information about the operating system on the current host."""
    shell = "parentSession.shell"
    """The shell on the current host."""
    sshIntegrationLevel = "parentSession.sshIntegrationLevel"
    """0: No ssh integration. 1: Basic ssh integration. 2: Full ssh integration with all features available."""
    homeDirectory = "parentSession.homeDirectory"
    """The home directory on the current host."""
    applicationKeypad = "parentSession.applicationKeypad"
    """A boolean indicating if the session is in application keypad mode."""
    mouseInfo = "parentSession.mouseInfo"
    """Describes the last mouse event. Is an array: [x coord, y coord, button number, click count, array of modifiers, bitmask of side effects, event type]. x coord is 0-based and gives the location in columns from the leftmost column. y coord is 0 at the first line in history, including lines which have since been lost if there are more lines of history than the maximum. button number is 0 for left, 1 for right, and 2 or greater for other buttons. click count is 1 for single click, 2 for double click, etc., and isn't artifically bounded. array of modifiers contains numbers for each modifier key that is pressed. They keys are: Control = 1; Option = 2; Command = 3; Shift = 4. bitmask of side effects comes by summing these values: Modify selection = 1; Perform action = 2; Open target (e.g., a URL or file) = 4; Report = 8; Move cursor = 16; Move find-on-page start location = 32; Open password manager = 64; Drag = 128. event type is 0 for mouse-up, 1 for mouse-down, 2 for drag."""
    bellCount = "parentSession.bellCount"
    """Number of times the bell has rung."""
    hostname = "parentSession.hostname"
    """The current hostname"""
    lastCommand = "parentSession.lastCommand"
    """The last command run in the session"""
    path = "parentSession.path"
    """The current working directory (this works without shell integration, but not if you ssh elsewhere)"""
    username = "parentSession.username"
    """The current user name"""
    autoLogId = "parentSession.autoLogId"
    """When automatic logging is enabled, this is the random number portion of the filename."""
    creationTimeString = "parentSession.creationTimeString"
    """A string giving the initial creation time of the session, used as part of the filename when automatic logging is enabled"""
    logFilename = "parentSession.logFilename"
    """If set, the filename that logging goes to. If unset, logging is off. New in version 3.4.7."""
    tmuxClientName = "parentSession.tmuxClientName"
    """The name of the tmux session when tmux integration is in use (e.g., user@localhost)."""
    tmuxPaneTitle = "parentSession.tmuxPaneTitle"
    """The title of the tmux window pane."""
    tmuxRole = "parentSession.tmuxRole"
    """Unset if tmux integration is not in use. Otherwise, is "gateway" for the session in which tmux -CC is running or "client" in tmux integration sessions."""
    tmuxStatusLeft = "parentSession.tmuxStatusLeft"
    """In tmux integration, the value of the left side of the status bar."""
    tmuxStatusRight = "parentSession.tmuxStatusRight"
    """In tmux integration, the value of the right side of the status bar."""
    tmuxWindowPane = "parentSession.tmuxWindowPane"
    """In tmux integration, this gives the window pane number."""
    tmuxWindowTitle = "parentSession.tmuxWindowTitle"
    """If tmux integration is in use, this gives the name of the window title from tmux."""
    tmuxWindowPaneIndex = "parentSession.tmuxWindowPaneIndex"
    """In tmux integration, this gives the index of the window pane. It corresponds to the pane_index property in tmux."""
    badge = "parentSession.badge"
    """The value of the badge. Note that the user can enter an interpolated string in the UI, but this value contains the string result of evaluating it."""
    id = "parentSession.id"
    """A unique identifier for the session"""
    profileName = "parentSession.profileName"
    """The name of the current profile."""
    showingAlternateScreen = "parentSession.showingAlternateScreen"
    """\"1\" if the alternate screen buffer is active (e.g., a full-screen TUI like vim or less), otherwise \"0\"."""
    effective_root_pid = "parentSession.effective_root_pid"
    """The process ID of the effective root process of the session."""
    foregroundJobAncestors = "parentSession.foregroundJobAncestors"
    """A newline-delimited list of the foreground job's ancestor process names."""
    isBroadcastSource = "parentSession.isBroadcastSource"
    """\"1\" if this session is currently a source for input broadcasting, otherwise \"0\"."""

    tab = nonmember(PrefixedEnum(TabEnum, "parentSession.tab"))
    """A reference to the context of the parent session's active tab."""
    iterm2 = nonmember(PrefixedEnum(GlobalVar, "parentSession.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    user = nonmember(PrefixedEnum(UserVar, "parentSession.user"))
    """A context for user-set variables. Variables may be set with a custom control sequence or by using the Python scripting API. They are often set when using shell integration. See User-Defined Variables for more information."""


class _TabAtTab(StrEnum):
    """Reference view: tab (the active tab containing this session)."""

    id = "tab.id"
    """The unique identifier for this tab."""
    titleOverrideFormat = "tab.titleOverrideFormat"
    """An interpolated string giving the title to use for the tab. If not set, the session's title will be used. Note the session's title is configurable in Prefs > Profiles > General > Title and is not necessarily equal to the autoName, but may be derived from it (or not)."""
    titleOverride = "tab.titleOverride"
    """The value of titleOverrideFormat after evaluating it as an interpolated string."""
    tmuxWindow = "tab.tmuxWindow"
    """In tmux integration, this is the tmux window number this tab represents."""
    tmuxWindowTitle = "tab.tmuxWindowTitle"
    """In tmux integration, this is the tmux window title. It will only be set if the tmux option set-title is on. It comes from evaluating the tmux set-titles-strings option."""
    tmuxWindowName = "tab.tmuxWindowName"
    """In tmux integration, this is the tmux window name."""
    tabTitle = "tab.title"
    """The fully formatted title as it appears in the tab bar."""

    iterm2 = nonmember(PrefixedEnum(GlobalVar, "tab.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    window = nonmember(PrefixedEnum(WindowEnum, "tab.window"))
    """A reference to the context of the enclosing window."""


class _SessionAtCurrentSession(StrEnum):
    """Reference view: currentSession (the active session in this tab)."""

    autoNameFormat = "currentSession.autoNameFormat"
    """This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created."""
    autoName = "currentSession.autoName"
    """The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is."""
    sessionName = "currentSession.name"
    """The formatted name as it appears in the tab bar (excluding tmux integration decoration). For example, if the profile is configured to show the session name and job, this would take a value like My Profile (vim)."""
    presentationName = "currentSession.presentationName"
    """The session name exactly as it appears in the session title bar."""
    terminalIconName = "currentSession.terminalIconName"
    """The "icon" title, as set by the control sequence OSC 0 or OSC 1."""
    terminalWindowName = "currentSession.terminalWindowName"
    """The "window" title, as set by the control sequence OSC 0 or OSC 2."""
    triggerName = "currentSession.triggerName"
    """The last session name set by a trigger."""
    columns = "currentSession.columns"
    """Session's width in columns"""
    commandLine = "currentSession.commandLine"
    """Command line of the current foreground job (job name including arguments)"""
    jobName = "currentSession.jobName"
    """The name of the current foreground job (e.g., "emacs")"""
    jobPid = "currentSession.jobPid"
    """The process ID of the current foreground job in this session."""
    mouseReportingMode = "currentSession.mouseReportingMode"
    """A number indicating how mouse events are reported. -1: Not reported, 0: button clicks reported, 1: not currently implemented, 2: reports clicks and drags, 3: reports clicks, drags, and movement"""
    pid = "currentSession.pid"
    """The process ID of the root process in this session (typically login)."""
    processTitle = "currentSession.processTitle"
    """The (perhaps modified by the process) title of a process from its argv."""
    rows = "currentSession.rows"
    """The session's height in rows"""
    selection = "currentSession.selection"
    """The currently selected text."""
    selectionLength = "currentSession.selectionLength"
    """The length in UTF-8 bytes of the currently selected text."""
    termid = "currentSession.termid"
    """Window, tab, and pane number as used in the $TERM_SESSION_ID environment variable."""
    tty = "currentSession.tty"
    """The path to the local TTY device"""
    uname = "currentSession.uname"
    """Information about the operating system on the current host."""
    shell = "currentSession.shell"
    """The shell on the current host."""
    sshIntegrationLevel = "currentSession.sshIntegrationLevel"
    """0: No ssh integration. 1: Basic ssh integration. 2: Full ssh integration with all features available."""
    homeDirectory = "currentSession.homeDirectory"
    """The home directory on the current host."""
    applicationKeypad = "currentSession.applicationKeypad"
    """A boolean indicating if the session is in application keypad mode."""
    mouseInfo = "currentSession.mouseInfo"
    """Describes the last mouse event. Is an array: [x coord, y coord, button number, click count, array of modifiers, bitmask of side effects, event type]. x coord is 0-based and gives the location in columns from the leftmost column. y coord is 0 at the first line in history, including lines which have since been lost if there are more lines of history than the maximum. button number is 0 for left, 1 for right, and 2 or greater for other buttons. click count is 1 for single click, 2 for double click, etc., and isn't artifically bounded. array of modifiers contains numbers for each modifier key that is pressed. They keys are: Control = 1; Option = 2; Command = 3; Shift = 4. bitmask of side effects comes by summing these values: Modify selection = 1; Perform action = 2; Open target (e.g., a URL or file) = 4; Report = 8; Move cursor = 16; Move find-on-page start location = 32; Open password manager = 64; Drag = 128. event type is 0 for mouse-up, 1 for mouse-down, 2 for drag."""
    bellCount = "currentSession.bellCount"
    """Number of times the bell has rung."""
    hostname = "currentSession.hostname"
    """The current hostname"""
    lastCommand = "currentSession.lastCommand"
    """The last command run in the session"""
    path = "currentSession.path"
    """The current working directory (this works without shell integration, but not if you ssh elsewhere)"""
    username = "currentSession.username"
    """The current user name"""
    autoLogId = "currentSession.autoLogId"
    """When automatic logging is enabled, this is the random number portion of the filename."""
    creationTimeString = "currentSession.creationTimeString"
    """A string giving the initial creation time of the session, used as part of the filename when automatic logging is enabled"""
    logFilename = "currentSession.logFilename"
    """If set, the filename that logging goes to. If unset, logging is off. New in version 3.4.7."""
    tmuxClientName = "currentSession.tmuxClientName"
    """The name of the tmux session when tmux integration is in use (e.g., user@localhost)."""
    tmuxPaneTitle = "currentSession.tmuxPaneTitle"
    """The title of the tmux window pane."""
    tmuxRole = "currentSession.tmuxRole"
    """Unset if tmux integration is not in use. Otherwise, is "gateway" for the session in which tmux -CC is running or "client" in tmux integration sessions."""
    tmuxStatusLeft = "currentSession.tmuxStatusLeft"
    """In tmux integration, the value of the left side of the status bar."""
    tmuxStatusRight = "currentSession.tmuxStatusRight"
    """In tmux integration, the value of the right side of the status bar."""
    tmuxWindowPane = "currentSession.tmuxWindowPane"
    """In tmux integration, this gives the window pane number."""
    tmuxWindowTitle = "currentSession.tmuxWindowTitle"
    """If tmux integration is in use, this gives the name of the window title from tmux."""
    tmuxWindowPaneIndex = "currentSession.tmuxWindowPaneIndex"
    """In tmux integration, this gives the index of the window pane. It corresponds to the pane_index property in tmux."""
    badge = "currentSession.badge"
    """The value of the badge. Note that the user can enter an interpolated string in the UI, but this value contains the string result of evaluating it."""
    id = "currentSession.id"
    """A unique identifier for the session"""
    profileName = "currentSession.profileName"
    """The name of the current profile."""
    showingAlternateScreen = "currentSession.showingAlternateScreen"
    """\"1\" if the alternate screen buffer is active (e.g., a full-screen TUI like vim or less), otherwise \"0\"."""
    effective_root_pid = "currentSession.effective_root_pid"
    """The process ID of the effective root process of the session."""
    foregroundJobAncestors = "currentSession.foregroundJobAncestors"
    """A newline-delimited list of the foreground job's ancestor process names."""
    isBroadcastSource = "currentSession.isBroadcastSource"
    """\"1\" if this session is currently a source for input broadcasting, otherwise \"0\"."""
    parentSession = nonmember(_SessionAtCurrentSessionParentSession)
    """The session that was current when this session as created. This is an alias to the context of that session so you can access its variables."""

    iterm2 = nonmember(PrefixedEnum(GlobalVar, "currentSession.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    user = nonmember(PrefixedEnum(UserVar, "currentSession.user"))
    """A context for user-set variables. Variables may be set with a custom control sequence or by using the Python scripting API. They are often set when using shell integration. See User-Defined Variables for more information."""


class _WindowAtWindow(StrEnum):
    """Reference view: window (the window enclosing this tab)."""

    titleOverride = "window.titleOverride"
    """The value from evaluating the interpeted string in titleOverrideFormat, if set."""
    titleOverrideFormat = "window.titleOverrideFormat"
    """The window's interpolated string title. If not set, the current tab's title is used."""
    id = "window.id"
    """The window ID."""
    frame = "window.frame"
    """An array of integers giving the x origin, y origin, width, and height."""
    style = "window.style"
    """The window style. Takes one of these values: normal, non-native full screen, native full screen, full-width top, full-width bottom, full-height left, full-height right, bottom, top, left, right, no-title-bar, compact, accessory."""
    number = "window.number"
    """The window number. Corresponds to the keyboard shortcut that switches to the window. Begins at 1. Unlike the keyboard shortcut, this is set even if the number is larger than 9."""
    isHotkeyWindow = "window.isHotkeyWindow"
    """A boolean indicating if this is a hotkey window."""

    iterm2 = nonmember(PrefixedEnum(GlobalVar, "window.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""


class _TabAtCurrentTab(StrEnum):
    """Reference view: currentTab (the active tab in this window)."""

    id = "currentTab.id"
    """The unique identifier for this tab."""
    titleOverrideFormat = "currentTab.titleOverrideFormat"
    """An interpolated string giving the title to use for the tab. If not set, the session's title will be used. Note the session's title is configurable in Prefs > Profiles > General > Title and is not necessarily equal to the autoName, but may be derived from it (or not)."""
    titleOverride = "currentTab.titleOverride"
    """The value of titleOverrideFormat after evaluating it as an interpolated string."""
    tmuxWindow = "currentTab.tmuxWindow"
    """In tmux integration, this is the tmux window number this tab represents."""
    tmuxWindowTitle = "currentTab.tmuxWindowTitle"
    """In tmux integration, this is the tmux window title. It will only be set if the tmux option set-title is on. It comes from evaluating the tmux set-titles-strings option."""
    tmuxWindowName = "currentTab.tmuxWindowName"
    """In tmux integration, this is the tmux window name."""
    tabTitle = "currentTab.title"
    """The fully formatted title as it appears in the tab bar."""

    currentSession = nonmember(_SessionAtCurrentTabCurrentSession)
    """Defined in the context of the tab's current session"""
    iterm2 = nonmember(PrefixedEnum(GlobalVar, "currentTab.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""


class SessionVar(StrEnum):
    """Defined in the context of a session"""

    all = SessionEnum.all
    """All possible session variables."""

    # Session Name
    autoNameFormat = SessionEnum.autoNameFormat
    """This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created."""
    autoName = SessionEnum.autoName
    """The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is."""
    sessionName = SessionEnum.sessionName
    """The formatted name as it appears in the tab bar (excluding tmux integration decoration). For example, if the profile is configured to show the session name and job, this would take a value like My Profile (vim)."""
    presentationName = SessionEnum.presentationName
    """The session name exactly as it appears in the session title bar."""
    terminalIconName = SessionEnum.terminalIconName
    """The "icon" title, as set by the control sequence OSC 0 or OSC 1."""
    terminalWindowName = SessionEnum.terminalWindowName
    """The "window" title, as set by the control sequence OSC 0 or OSC 2."""
    triggerName = SessionEnum.triggerName
    """The last session name set by a trigger."""

    # Terminal
    columns = SessionEnum.columns
    """Session's width in columns"""
    commandLine = SessionEnum.commandLine
    """Command line of the current foreground job (job name including arguments)"""
    jobName = SessionEnum.jobName
    """The name of the current foreground job (e.g., "emacs")"""
    jobPid = SessionEnum.jobPid
    """The process ID of the current foreground job in this session."""
    mouseReportingMode = SessionEnum.mouseReportingMode
    """A number indicating how mouse events are reported. -1: Not reported, 0: button clicks reported, 1: not currently implemented, 2: reports clicks and drags, 3: reports clicks, drags, and movement"""
    pid = SessionEnum.pid
    """The process ID of the root process in this session (typically login)."""
    processTitle = SessionEnum.processTitle
    """The (perhaps modified by the process) title of a process from its argv."""
    rows = SessionEnum.rows
    """The session's height in rows"""
    selection = SessionEnum.selection
    """The currently selected text."""
    selectionLength = SessionEnum.selectionLength
    """The length in UTF-8 bytes of the currently selected text."""
    termid = SessionEnum.termid
    """Window, tab, and pane number as used in the $TERM_SESSION_ID environment variable."""
    tty = SessionEnum.tty
    """The path to the local TTY device"""
    uname = SessionEnum.uname
    """Information about the operating system on the current host."""
    shell = SessionEnum.shell
    """The shell on the current host."""
    sshIntegrationLevel = SessionEnum.sshIntegrationLevel
    """0: No ssh integration. 1: Basic ssh integration. 2: Full ssh integration with all features available."""
    homeDirectory = SessionEnum.homeDirectory
    """The home directory on the current host."""
    applicationKeypad = SessionEnum.applicationKeypad
    """A boolean indicating if the session is in application keypad mode."""
    mouseInfo = SessionEnum.mouseInfo
    """Describes the last mouse event. Is an array: [x coord, y coord, button number, click count, array of modifiers, bitmask of side effects, event type]. x coord is 0-based and gives the location in columns from the leftmost column. y coord is 0 at the first line in history, including lines which have since been lost if there are more lines of history than the maximum. button number is 0 for left, 1 for right, and 2 or greater for other buttons. click count is 1 for single click, 2 for double click, etc., and isn't artifically bounded. array of modifiers contains numbers for each modifier key that is pressed. They keys are: Control = 1; Option = 2; Command = 3; Shift = 4. bitmask of side effects comes by summing these values: Modify selection = 1; Perform action = 2; Open target (e.g., a URL or file) = 4; Report = 8; Move cursor = 16; Move find-on-page start location = 32; Open password manager = 64; Drag = 128. event type is 0 for mouse-up, 1 for mouse-down, 2 for drag."""
    bellCount = SessionEnum.bellCount
    """Number of times the bell has rung."""

    # Shell Integration
    hostname = SessionEnum.hostname
    """The current hostname"""
    lastCommand = SessionEnum.lastCommand
    """The last command run in the session"""
    path = SessionEnum.path
    """The current working directory (this works without shell integration, but not if you ssh elsewhere)"""
    username = SessionEnum.username
    """The current user name"""

    # Logging
    autoLogId = SessionEnum.autoLogId
    """When automatic logging is enabled, this is the random number portion of the filename."""
    creationTimeString = SessionEnum.creationTimeString
    """A string giving the initial creation time of the session, used as part of the filename when automatic logging is enabled"""
    logFilename = SessionEnum.logFilename
    """If set, the filename that logging goes to. If unset, logging is off. New in version 3.4.7."""

    # tmux Integration
    tmuxClientName = SessionEnum.tmuxClientName
    """The name of the tmux session when tmux integration is in use (e.g., user@localhost)."""
    tmuxPaneTitle = SessionEnum.tmuxPaneTitle
    """The title of the tmux window pane."""
    tmuxRole = SessionEnum.tmuxRole
    """Unset if tmux integration is not in use. Otherwise, is "gateway" for the session in which tmux -CC is running or "client" in tmux integration sessions."""
    tmuxStatusLeft = SessionEnum.tmuxStatusLeft
    """In tmux integration, the value of the left side of the status bar."""
    tmuxStatusRight = SessionEnum.tmuxStatusRight
    """In tmux integration, the value of the right side of the status bar."""
    tmuxWindowPane = SessionEnum.tmuxWindowPane
    """In tmux integration, this gives the window pane number."""
    tmuxWindowTitle = SessionEnum.tmuxWindowTitle
    """If tmux integration is in use, this gives the name of the window title from tmux."""
    tmuxWindowPaneIndex = SessionEnum.tmuxWindowPaneIndex
    """In tmux integration, this gives the index of the window pane. It corresponds to the pane_index property in tmux."""

    # Other
    badge = SessionEnum.badge
    """The value of the badge. Note that the user can enter an interpolated string in the UI, but this value contains the string result of evaluating it."""
    id = SessionEnum.id
    """A unique identifier for the session"""
    profileName = SessionEnum.profileName
    """The name of the current profile."""

    # Runtime (undocumented; not in iTerm2 variable docs)
    showingAlternateScreen = SessionEnum.showingAlternateScreen
    """\"1\" if the alternate screen buffer is active (e.g., a full-screen TUI like vim or less), otherwise \"0\"."""
    effective_root_pid = SessionEnum.effective_root_pid
    """The process ID of the effective root process of the session."""
    foregroundJobAncestors = SessionEnum.foregroundJobAncestors
    """A newline-delimited list of the foreground job's ancestor process names."""
    isBroadcastSource = SessionEnum.isBroadcastSource
    """\"1\" if this session is currently a source for input broadcasting, otherwise \"0\"."""
    parentSession = nonmember(_SessionAtParentSession)
    """The session that was current when this session as created. This is an alias to the context of that session so you can access its variables."""

    # > References to Other Contexts
    tab = nonmember(_TabAtTab)
    """A reference to the context of the active tab."""
    iterm2 = nonmember(PrefixedEnum(GlobalVar, "iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    user = nonmember(PrefixedEnum(UserVar, "user"))
    """A context for user-set variables. Variables may be set with a custom control sequence or by using the Python scripting API. They are often set when using shell integration. See User-Defined Variables for more information."""


class WindowVar(StrEnum):
    """Defined in the context of a window"""

    all = WindowEnum.all
    """All possible window variables."""

    # Window Title
    titleOverride = WindowEnum.titleOverride
    """The value from evaluating the interpeted string in titleOverrideFormat, if set."""
    titleOverrideFormat = WindowEnum.titleOverrideFormat
    """The window's interpolated string title. If not set, the current tab's title is used."""

    # Other
    id = WindowEnum.id
    """The window ID."""
    frame = WindowEnum.frame
    """An array of integers giving the x origin, y origin, width, and height."""
    style = WindowEnum.style
    """The window style. Takes one of these values: normal, non-native full screen, native full screen, full-width top, full-width bottom, full-height left, full-height right, bottom, top, left, right, no-title-bar, compact, accessory."""
    number = WindowEnum.number
    """The window number. Corresponds to the keyboard shortcut that switches to the window. Begins at 1. Unlike the keyboard shortcut, this is set even if the number is larger than 9."""
    isHotkeyWindow = WindowEnum.isHotkeyWindow
    """A boolean indicating if this is a hotkey window."""

    # References to Other Contexts
    currentTab = nonmember(_TabAtCurrentTab)
    """A reference to the context of the active tab."""
    iterm2 = nonmember(PrefixedEnum(GlobalVar, "iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""


class TabVar(StrEnum):
    """Defined in the context of a tab"""

    all = TabEnum.all
    """All possible tab variables."""
    id = TabEnum.id
    """The unique identifier for this tab."""
    titleOverrideFormat = TabEnum.titleOverrideFormat
    """An interpolated string giving the title to use for the tab. If not set, the session's title will be used. Note the session's title is configurable in Prefs > Profiles > General > Title and is not necessarily equal to the autoName, but may be derived from it (or not)."""
    titleOverride = TabEnum.titleOverride
    """The value of titleOverrideFormat after evaluating it as an interpolated string."""
    tmuxWindow = TabEnum.tmuxWindow
    """In tmux integration, this is the tmux window number this tab represents."""
    tmuxWindowTitle = TabEnum.tmuxWindowTitle
    """In tmux integration, this is the tmux window title. It will only be set if the tmux option set-title is on. It comes from evaluating the tmux set-titles-strings option."""
    tmuxWindowName = TabEnum.tmuxWindowName
    """In tmux integration, this is the tmux window name."""
    tabTitle = TabEnum.tabTitle
    """The fully formatted title as it appears in the tab bar."""

    # > References to Other Contexts
    currentSession = nonmember(_SessionAtCurrentSession)
    """A reference to the context of the active session in this tab."""
    iterm2 = nonmember(PrefixedEnum(GlobalVar, "iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    window = nonmember(_WindowAtWindow)
    """A reference to the context of the enclosing window."""


type NestedSessionVariables = SessionVar.parentSession | SessionVar.tab | SessionVar.iterm2 | SessionVar.user
type SessionVariable = SessionVar | NestedSessionVariables | SessionVars

type NestedTabVariables = TabVar.currentSession | TabVar.iterm2 | TabVar.window
type TabVariable = TabVar | NestedTabVariables | TabVars

type NestedWindowVariables = WindowVar.currentTab | WindowVar.iterm2
type WindowVariable = WindowVar | NestedWindowVariables | WindowVars

type GlobalVariable = GlobalVar | GlobalVars

type UserVariable = UserVar | UserVars

type NestedEnumVariables = NestedSessionVariables | NestedTabVariables | NestedWindowVariables
type EnumVariables = SessionVar | TabVar | WindowVar | GlobalVar | UserVar | NestedEnumVariables
type LiteralVariables = SessionVars | TabVars | WindowVars | GlobalVars | UserVars
type Variable = EnumVariables | LiteralVariables


class Prompt(prompt.Prompt):
    _Prompt__proto: GetPromptResponse


PromptEvent: TypeAlias = Tuple[Literal[prompt.PromptMonitor.Mode.PROMPT], Prompt | None]
PromptEventWithId: TypeAlias = Tuple[Literal[prompt.PromptMonitor.Mode.PROMPT], Prompt | None, str | None]

CommandStartEvent: TypeAlias = Tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_START], str]
CommandStartEventWithId: TypeAlias = Tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_START], str, str | None]

CommandEndEvent: TypeAlias = Tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_END], int]
CommandEndEventWithId: TypeAlias = Tuple[Literal[prompt.PromptMonitor.Mode.COMMAND_END], int, str | None]

PromptMonitorEvent: TypeAlias = PromptEvent | CommandStartEvent | CommandEndEvent
PromptMonitorEventWithId: TypeAlias = PromptEventWithId | CommandStartEventWithId | CommandEndEventWithId


class PromptMonitor(prompt.PromptMonitor):
    @overload
    async def async_get(self, include_id: Literal[False] = False, *, mode: None = None) -> PromptMonitorEvent: ...
    @overload
    async def async_get(self, include_id: Literal[True], *, mode: None = None) -> PromptMonitorEventWithId: ...

    @overload
    async def async_get(
        self, include_id: Literal[False] = False, *, mode: Literal[prompt.PromptMonitor.Mode.PROMPT]
    ) -> PromptEvent: ...
    @overload
    async def async_get(
        self, include_id: Literal[True], *, mode: Literal[prompt.PromptMonitor.Mode.PROMPT]
    ) -> PromptEventWithId: ...

    @overload
    async def async_get(
        self, include_id: Literal[False] = False, *, mode: Literal[prompt.PromptMonitor.Mode.COMMAND_START]
    ) -> CommandStartEvent: ...
    @overload
    async def async_get(
        self, include_id: Literal[True], *, mode: Literal[prompt.PromptMonitor.Mode.COMMAND_START]
    ) -> CommandStartEventWithId: ...

    @overload
    async def async_get(
        self, include_id: Literal[False] = False, *, mode: Literal[prompt.PromptMonitor.Mode.COMMAND_END]
    ) -> CommandEndEvent: ...
    @overload
    async def async_get(
        self, include_id: Literal[True], *, mode: Literal[prompt.PromptMonitor.Mode.COMMAND_END]
    ) -> CommandEndEventWithId: ...

    async def async_get(
        self, include_id: bool = False, *, mode: prompt.PromptMonitor.Mode | None = None
    ) -> PromptMonitorEvent | PromptMonitorEventWithId:
        while True:
            result = cast(PromptMonitorEvent | PromptMonitorEventWithId, await super().async_get(include_id))
            if mode is None or result[0] == mode:
                return result


class Profile(profile.Profile):
    guid: str  # pyright: ignore[reportIncompatibleMethodOverride]
    original_guid: str  # pyright: ignore[reportIncompatibleMethodOverride]

    @staticmethod
    async def async_get(connection: Connection, guids: list[str] | None = None) -> list[Profile]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Profile], await profile.Profile.async_get(connection, guids))

    @staticmethod
    async def async_get_default(connection: Connection) -> Profile:
        return cast(Profile, await profile.Profile.async_get_default(connection))


class PartialProfile(profile.PartialProfile):
    @staticmethod
    async def async_get(connection: Connection, guids: list[str] | None = None) -> list[PartialProfile]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[PartialProfile], await profile.PartialProfile.async_get(connection, guids))

    @staticmethod
    async def async_get_default(connection: Connection, properties: list[str] | None = None) -> PartialProfile:
        properties = properties or ["Guid", "Name"]
        return cast(PartialProfile, await profile.PartialProfile.async_get_default(connection, properties))

    @staticmethod
    async def async_query(  # pyright: ignore[reportIncompatibleMethodOverride]
        connection: Connection, guids: list[str] | None = None, properties: list[str] | None = None
    ) -> list[PartialProfile]:
        properties = properties or ["Guid", "Name"]
        return cast(list[PartialProfile], await profile.PartialProfile.async_query(connection, guids, properties))


class Session(session.Session):
    name: str

    async def async_get_profile(self) -> Profile:
        return cast(Profile, await super().async_get_profile())

    @property
    def tab(self) -> Tab | None:
        return cast(Tab | None, super().tab)


class Tab(tab.Tab):
    @property
    def all_sessions(self) -> list[Session]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Session], super().all_sessions)

    @property
    def sessions(self) -> list[Session]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Session], super().sessions)

    @property
    def current_session(self) -> Session | None:
        return cast(Session, super().current_session)


class Window(window.Window):
    """Represents a terminal window.

    Do not create an instance of `Window` by calling the initializer yourself.
    To get a reference to an existing window, use :class:`~iterm2.app.App` and
    query its `windows` property. To create a new window, use
    :meth:`async_create`.
    """

    @property
    def tabs(self) -> list[Tab]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Tab], super().tabs)

    @property
    def current_tab(self) -> Tab | None:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(Tab | None, super().current_tab)

    @staticmethod
    async def async_create(  # pyright: ignore[reportIncompatibleMethodOverride]
        connection: Connection,
        profile: str | None = None,
        command: str | None = None,
        profile_customizations: profile.LocalWriteOnlyProfile | None = None,
    ) -> Window | None:
        return cast(
            Window | None, await window.Window.async_create(connection, profile, command, profile_customizations)
        )

    async def async_create_tab(
        self,
        profile: str | None = None,
        command: str | None = None,
        index: int | None = None,
        profile_customizations: profile.LocalWriteOnlyProfile | None = None,
    ) -> Tab | None:
        return cast(Tab | None, await super().async_create_tab(profile, command, index, profile_customizations))


class App(app.App):
    @property
    def windows(self) -> list[Window]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Window], super().windows)

    @property
    def current_window(self) -> Window | None:
        return cast(Window | None, super().current_window)

    def get_window_by_id(self, window_id: str) -> Window | None:
        return cast(Window | None, super().get_window_by_id(window_id))

    def get_session_by_id(self, session_id: str, include_buried: bool = True) -> Session | None:
        return cast(Session | None, super().get_session_by_id(session_id, include_buried))

    def get_tab_by_id(self, tab_id: str) -> Tab | None:
        return cast(Tab | None, super().get_tab_by_id(tab_id))

    def get_window_for_tab(self, tab_id: str) -> Window | None:
        return cast(Window | None, super().get_window_for_tab(tab_id))

    def get_window_and_tab_for_session(self, session: Session) -> Tuple[None, None] | Tuple[Window, Tab]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(Tuple[Window, Tab] | Tuple[None, None], super().get_window_and_tab_for_session(session))

    async def window_delegate_get_tab_by_id(self, tab_id: str) -> Tab | None:
        return cast(Tab | None, await super().window_delegate_get_tab_by_id(tab_id))

    async def tab_delegate_get_window_by_id(self, window_id: str) -> Window | None:
        return cast(Window | None, await super().tab_delegate_get_window_by_id(window_id))

    def session_delegate_get_tab(self, session) -> Tab | None:
        return cast(Tab | None, super().session_delegate_get_tab(session))


@overload
async def async_get_app(connection: Connection, create_if_needed: Literal[True]) -> App: ...
@overload
async def async_get_app(connection: Connection, create_if_needed: Literal[False]) -> App | None: ...
async def async_get_app(connection: Connection, create_if_needed: bool = True) -> App | None:
    """Returns the app singleton, creating it if needed.

    :param connection: The connection to iTerm2.
    :type connection: :class:`Connection`
    :param create_if_needed: If `True`, create the global :class:`App` instance
      if one does not already exists. If `False`, do not create it.

    :returns: The global :class:`App` instance. If :param:`create_if_needed` is False,
    then this may return `None` if no such instance exists.
    :rtype: :class:`App` | None
    """
    return cast(App, await app.async_get_app(connection, create_if_needed))


async def async_get_last_prompt(connection: Connection, session_id: str) -> Prompt | None:
    """
    Fetches info about the last prompt in a session.

    :param connection: The connection to iTerm2.
    :type connection: :class:`Connection`
    :param session_id: The session ID for which to fetch the most recent prompt.

    :returns: The prompt if one exists, or else `None`.
    :rtype: :class:`iterm2.prompt.Prompt` | None

    :raises: :class:`iterm2.rpc.RPCException` if something goes wrong.
    """
    return cast(Prompt | None, await prompt.async_get_last_prompt(connection, session_id))


async def async_get_prompt_by_id(connection: Connection, session_id: str, prompt_unique_id: str) -> Prompt | None:
    """
    Fetches a Prompt by its unique ID.

    :param connection: The connection to iTerm2.
    :type connection: :class:`Connection`
    :param session_id: The Session ID the prompt belongs to.
    :param prompt_unique_id: The unique ID of the prompt.

    :returns: The prompt if one exists or else `None`.
    :rtype: :class:`iterm2.prompt.Prompt` | None

    :raises: :class:`iterm2.rpc.RPCException` if something goes wrong.
    """
    return cast(Prompt | None, await prompt.async_get_prompt_by_id(connection, session_id, prompt_unique_id))


def check_supports_prompt_monitor_modes(connection):
    """Die if you can't monitor multiple prompt monitor modes."""
    if not capabilities.supports_prompt_monitor_modes(connection):
        raise capabilities.AppVersionTooOld(
            "This version of iTerm2 is too old to monitor the "
            "prompt in different modes. You should upgrade to "
            "run this script."
        )
