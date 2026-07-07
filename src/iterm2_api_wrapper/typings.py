from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, ClassVar, Literal, TypeAlias, TypedDict


if TYPE_CHECKING:
    from .api.it2app import App
    from .api.it2connection import Connection
    from .api.it2profile import Profile
    from .api.it2session import Session
    from .api.it2tab import Tab
    from .api.it2window import Window
    from .gateway import _Connection


iTermConnection = type["_Connection | Connection"]


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return str.__str__(self)


class iTermStateSetupKwargs(TypedDict, total=False):
    new_tab: bool
    """Whether to open a new tab for the session."""
    dedicated_profile_name: str | None
    """If provided, the name of the profile to use for the session.
        If not provided, the current profile will be used."""
    service_name: str | None
    extra_id: str | None
    debug: bool
    """Whether to enable debug logging."""
    activate: bool
    """Whether to bring iTerm2 to the foreground during setup."""


class iTermStateKwargs(TypedDict, total=True):
    connection: Connection
    app: App
    window: Window
    tab: Tab
    session: Session
    profile: Profile

    is_hotkey_window: bool
    """Whether the current window is a hotkey window."""


class HexCodeEnum(StrEnum):
    def __new__(cls, codepoint: int) -> HexCodeEnum:
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
    """Quoted insert (literal text)"""
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
    NULL = 0x00
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

    @classmethod
    def resolve(cls, seq: HexCode | str) -> HexCode | str:
        if isinstance(seq, HexCodeEnum):
            return str(seq)

        # Resolve a HexCode member name (including aliases) to its bytes.
        member = HexCodeEnum.__members__.get(seq)
        return str(member) if member is not None else seq


# fmt: off
HexCodeKey: TypeAlias = Literal[
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
    "NULL",
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

HexCode = HexCodeEnum | HexCodeKey


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
        if not (0 <= code <= 255):
            raise ValueError("Exit codes must be between 0 and 255.")

        try:
            return cls(code)
        except ValueError:
            return code


@dataclass
class CommandExecutionStatus:
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


@dataclass
class CommandExecutionResult:
    output: str
    status: CommandExecutionStatus | None

    def __str__(self) -> str:
        return self.output
