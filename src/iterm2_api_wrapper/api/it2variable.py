from enum import auto
from typing import Generic, Literal, TypeVar, cast, overload

from iterm2_api_wrapper.core.typings import StrEnum


_T = TypeVar("_T", bound=StrEnum)
_ContextT = TypeVar("_ContextT")


class _EnumContext(Generic[_ContextT]):
    """Expose a context class from an enum without creating an enum member."""

    def __init__(self, context: _ContextT) -> None:
        self.context = context

    def __get__(self, instance: object | None, owner: type[object] | None = None) -> _ContextT:
        return self.context


# NOTE: Check https://iterm2.com/documentation-variables.html for potential updates


@overload
def PrefixedEnum(EnumT: None, prefix: str) -> type[StrEnum]: ...
@overload
def PrefixedEnum(EnumT: type[_T], prefix=None) -> type[_T]: ...
def PrefixedEnum(EnumT: type[StrEnum] | None, prefix: str | None = None) -> type[StrEnum]:
    if EnumT is None:

        class _PrefixedStrEnum(StrEnum):
            @staticmethod
            def _generate_next_value_(name, start, count, last_values) -> str:
                return f"{prefix}.{name}"

        return _PrefixedStrEnum

    actual_prefix = prefix or EnumT.__name__.removeprefix("_")
    members = {m.name: f"{actual_prefix}.{m.value}" for m in EnumT if m.value != "*"}
    # members = {m.name: f"{actual_prefix}.{m.value}" for m in EnumT if not m.value.endswith("*")}

    # Pure-wildcard contexts (e.g. UserVar) have no concrete members; keep the
    # wildcard itself, prefixed, so e.g. SessionVar.user.all -> "user.*".
    if not members:
        # members = {m.name: f"{actual_prefix}.*" for m in EnumT if m.value == "*"}
        members = {m.name: f"{actual_prefix}.*" if m.value == "*" else m.value for m in EnumT if m.value == "*"}

    generated_enum = cast(type[StrEnum], StrEnum(f"_{EnumT.__name__}Prefixed", names=members))

    # Functional enums have no inspectable class statement. Copy the
    # adjacent docstrings that MetaEnum already extracted from EnumT.
    for member_name, generated_member in generated_enum.__members__.items():
        source_member = EnumT.__members__.get(member_name)
        if source_member is None:
            continue

        # Inspect the member instance directly. Accessing source_member.__doc__
        # would return an inherited generic Enum/str docstring when no explicit
        # member documentation was assigned.
        member_doc = source_member.__dict__.get("__doc__")
        if isinstance(member_doc, str):
            generated_member.__doc__ = member_doc

    return generated_enum


class _WindowReference(StrEnum):
    all = "*"
    """All possible window variables."""
    windowTitle = "title"
    """The title of the window."""
    titleOverride = auto()
    """The value from evaluating the interpeted string in titleOverrideFormat, if set."""
    titleOverrideFormat = auto()
    """The window's interpolated string title. If not set, the current tab's title is used."""
    id = auto()
    """The window ID."""
    frame = auto()
    """An array of integers giving the x origin, y origin, width, and height."""
    style = auto()
    """The window style. Takes one of these values: normal, non-native full screen, native full screen, full-width top, full-width bottom, full-height left, full-height right, bottom, top, left, right, no-title-bar, compact, accessory."""
    number = auto()
    """The window number. Corresponds to the keyboard shortcut that switches to the window. Begins at 1. Unlike the keyboard shortcut, this is set even if the number is larger than 9."""
    isHotkeyWindow = auto()
    """A boolean indicating if this is a hotkey window."""


class AppVarEnum(StrEnum):
    """Defined in the global context"""

    all = "*"
    """All possible global variables."""
    effectiveTheme = auto()
    """A space-delimited list of words describing the OS theme (e.g., "dark", "light highContrast", "dark minimal")"""
    localhostName = auto()
    """The best guess of what localhost's hostname is"""
    pid = auto()
    """The process ID of the iTerm2 app"""
    appBundlePath = auto()
    """The path to the iTerm.app executable."""


class UserVarEnum(StrEnum):
    all = "*"


# ---------------------------------------------------------------------------
# Reference views: concrete enums that mirror the 2-hop reference paths in the
# literal aliases above so that enum access (e.g. SessionVar.tab.title)
# autocompletes and resolves to the correct dotted variable string at runtime.
# Generated to match the literal coverage exactly; do not hand-add deeper paths.
# ---------------------------------------------------------------------------


class _SessionAtCurrentTabCurrentSession(StrEnum, prefix="currentTab.currentSession"):
    """Reference view: currentTab.currentSession (the window's active session)."""

    all = "currentTab.currentSession.*"
    """All possible session variables."""

    autoNameFormat = auto()
    """This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created."""
    autoName = auto()
    """The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is."""
    deepestJob = auto()
    """The name of the deepest job in the process tree of the current foreground job."""
    isLocalhost = auto()
    """A boolean indicating whether the session is running on the local host or a remote host."""
    sessionName = "currentTab.currentSession.name"
    """The formatted name as it appears in the tab bar (excluding tmux integration decoration). For example, if the profile is configured to show the session sessionName and job, this would take a value like My Profile (vim)."""
    presentationName = auto()
    """The session name exactly as it appears in the session title bar."""
    terminalIconName = auto()
    """The "icon" title, as set by the control sequence OSC 0 or OSC 1."""
    terminalWindowName = auto()
    """The "window" title, as set by the control sequence OSC 0 or OSC 2."""
    triggerName = auto()
    """The last session name set by a trigger."""
    columns = auto()
    """Session's width in columns"""
    commandLine = auto()
    """Command line of the current foreground job (job name including arguments)"""
    jobName = auto()
    """The name of the current foreground job (e.g., "emacs")"""
    jobPid = auto()
    """The process ID of the current foreground job in this session."""
    mouseReportingMode = auto()
    """A number indicating how mouse events are reported. -1: Not reported, 0: button clicks reported, 1: not currently implemented, 2: reports clicks and drags, 3: reports clicks, drags, and movement"""
    pid = auto()
    """The process ID of the root process in this session (typically login)."""
    processTitle = auto()
    """The (perhaps modified by the process) title of a process from its argv."""
    rows = auto()
    """The session's height in rows"""
    selection = auto()
    """The currently selected text."""
    selectionLength = auto()
    """The length in UTF-8 bytes of the currently selected text."""
    termid = auto()
    """Window, tab, and pane number as used in the $TERM_SESSION_ID environment variable."""
    tty = auto()
    """The path to the local TTY device"""
    uname = auto()
    """Information about the operating system on the current host."""
    shell = auto()
    """The shell on the current host."""
    sshIntegrationLevel = auto()
    """0: No ssh integration. 1: Basic ssh integration. 2: Full ssh integration with all features available."""
    homeDirectory = auto()
    """The home directory on the current host."""
    applicationKeypad = auto()
    """A boolean indicating if the session is in application keypad mode."""
    mouseInfo = auto()
    """Describes the last mouse event. Is an array: [x coord, y coord, button number, click count, array of modifiers, bitmask of side effects, event type]. x coord is 0-based and gives the location in columns from the leftmost column. y coord is 0 at the first line in history, including lines which have since been lost if there are more lines of history than the maximum. button number is 0 for left, 1 for right, and 2 or greater for other buttons. click count is 1 for single click, 2 for double click, etc., and isn't artifically bounded. array of modifiers contains numbers for each modifier key that is pressed. They keys are: Control = 1; Option = 2; Command = 3; Shift = 4. bitmask of side effects comes by summing these values: Modify selection = 1; Perform action = 2; Open target (e.g., a URL or file) = 4; Report = 8; Move cursor = 16; Move find-on-page start location = 32; Open password manager = 64; Drag = 128. event type is 0 for mouse-up, 1 for mouse-down, 2 for drag."""
    bellCount = auto()
    """Number of times the bell has rung."""
    hostname = auto()
    """The current hostname"""
    lastCommand = auto()
    """The last command run in the session"""
    path = auto()
    """The current working directory (this works without shell integration, but not if you ssh elsewhere)"""
    username = auto()
    """The current user name"""
    autoLogId = auto()
    """When automatic logging is enabled, this is the random number portion of the filename."""
    creationTimeString = auto()
    """A string giving the initial creation time of the session, used as part of the filename when automatic logging is enabled"""
    logFilename = auto()
    """If set, the filename that logging goes to. If unset, logging is off. New in version 3.4.7."""
    tmuxClientName = auto()
    """The name of the tmux session when tmux integration is in use (e.g., user@localhost)."""
    tmuxPaneTitle = auto()
    """The title of the tmux window pane."""
    tmuxRole = auto()
    """Unset if tmux integration is not in use. Otherwise, is "gateway" for the session in which tmux -CC is running or "client" in tmux integration sessions."""
    tmuxStatusLeft = auto()
    """In tmux integration, the value of the left side of the status bar."""
    tmuxStatusRight = auto()
    """In tmux integration, the value of the right side of the status bar."""
    tmuxWindowPane = auto()
    """In tmux integration, this gives the window pane number."""
    tmuxWindowTitle = auto()
    """If tmux integration is in use, this gives the name of the window title from tmux."""
    tmuxWindowPaneIndex = auto()
    """In tmux integration, this gives the index of the window pane. It corresponds to the pane_index property in tmux."""
    badge = auto()
    """The value of the badge. Note that the user can enter an interpolated string in the UI, but this value contains the string result of evaluating it."""
    id = auto()
    """A unique identifier for the session"""
    profileName = auto()
    """The name of the current profile."""
    showingAlternateScreen = auto()
    """\"1\" if the alternate screen buffer is active (e.g., a full-screen TUI like vim or less), otherwise \"0\"."""
    effective_root_pid = auto()
    """The process ID of the effective root process of the session."""
    foregroundJobAncestors = auto()
    """A newline-delimited list of the foreground job's ancestor process names."""
    isBroadcastSource = auto()
    """\"1\" if this session is currently a source for input broadcasting, otherwise \"0\"."""

    user = _EnumContext(PrefixedEnum(UserVarEnum, "currentTab.currentSession.user"))
    """A context for user-set variables. Variables may be set with a custom control sequence or by using the Python scripting API. They are often set when using shell integration. See User-Defined Variables for more information."""


class _SessionAtCurrentSession(StrEnum, prefix="currentSession"):
    """Reference view: currentSession (the active session in this tab)."""

    all = "currentSession.*"
    """All possible session variables."""

    autoNameFormat = auto()
    """This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created."""
    autoName = auto()
    """The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is."""
    deepestJob = auto()
    """The name of the deepest job in the process tree of the current foreground job."""
    isLocalhost = auto()
    """A boolean indicating whether the session is running on the local host or a remote host."""
    sessionName = "currentSession.name"
    """The formatted name as it appears in the tab bar (excluding tmux integration decoration). For example, if the profile is configured to show the session sessionName and job, this would take a value like My Profile (vim)."""
    presentationName = auto()
    """The session name exactly as it appears in the session title bar."""
    terminalIconName = auto()
    """The "icon" title, as set by the control sequence OSC 0 or OSC 1."""
    terminalWindowName = auto()
    """The "window" title, as set by the control sequence OSC 0 or OSC 2."""
    triggerName = auto()
    """The last session name set by a trigger."""
    columns = auto()
    """Session's width in columns"""
    commandLine = auto()
    """Command line of the current foreground job (job name including arguments)"""
    jobName = auto()
    """The name of the current foreground job (e.g., "emacs")"""
    jobPid = auto()
    """The process ID of the current foreground job in this session."""
    mouseReportingMode = auto()
    """A number indicating how mouse events are reported. -1: Not reported, 0: button clicks reported, 1: not currently implemented, 2: reports clicks and drags, 3: reports clicks, drags, and movement"""
    pid = auto()
    """The process ID of the root process in this session (typically login)."""
    processTitle = auto()
    """The (perhaps modified by the process) title of a process from its argv."""
    rows = auto()
    """The session's height in rows"""
    selection = auto()
    """The currently selected text."""
    selectionLength = auto()
    """The length in UTF-8 bytes of the currently selected text."""
    termid = auto()
    """Window, tab, and pane number as used in the $TERM_SESSION_ID environment variable."""
    tty = auto()
    """The path to the local TTY device"""
    uname = auto()
    """Information about the operating system on the current host."""
    shell = auto()
    """The shell on the current host."""
    sshIntegrationLevel = auto()
    """0: No ssh integration. 1: Basic ssh integration. 2: Full ssh integration with all features available."""
    homeDirectory = auto()
    """The home directory on the current host."""
    applicationKeypad = auto()
    """A boolean indicating if the session is in application keypad mode."""
    mouseInfo = auto()
    """Describes the last mouse event. Is an array: [x coord, y coord, button number, click count, array of modifiers, bitmask of side effects, event type]. x coord is 0-based and gives the location in columns from the leftmost column. y coord is 0 at the first line in history, including lines which have since been lost if there are more lines of history than the maximum. button number is 0 for left, 1 for right, and 2 or greater for other buttons. click count is 1 for single click, 2 for double click, etc., and isn't artifically bounded. array of modifiers contains numbers for each modifier key that is pressed. They keys are: Control = 1; Option = 2; Command = 3; Shift = 4. bitmask of side effects comes by summing these values: Modify selection = 1; Perform action = 2; Open target (e.g., a URL or file) = 4; Report = 8; Move cursor = 16; Move find-on-page start location = 32; Open password manager = 64; Drag = 128. event type is 0 for mouse-up, 1 for mouse-down, 2 for drag."""
    bellCount = auto()
    """Number of times the bell has rung."""
    hostname = auto()
    """The current hostname"""
    lastCommand = auto()
    """The last command run in the session"""
    path = auto()
    """The current working directory (this works without shell integration, but not if you ssh elsewhere)"""
    username = auto()
    """The current user name"""
    autoLogId = auto()
    """When automatic logging is enabled, this is the random number portion of the filename."""
    creationTimeString = auto()
    """A string giving the initial creation time of the session, used as part of the filename when automatic logging is enabled"""
    logFilename = auto()
    """If set, the filename that logging goes to. If unset, logging is off. New in version 3.4.7."""
    tmuxClientName = auto()
    """The name of the tmux session when tmux integration is in use (e.g., user@localhost)."""
    tmuxPaneTitle = auto()
    """The title of the tmux window pane."""
    tmuxRole = auto()
    """Unset if tmux integration is not in use. Otherwise, is "gateway" for the session in which tmux -CC is running or "client" in tmux integration sessions."""
    tmuxStatusLeft = auto()
    """In tmux integration, the value of the left side of the status bar."""
    tmuxStatusRight = auto()
    """In tmux integration, the value of the right side of the status bar."""
    tmuxWindowPane = auto()
    """In tmux integration, this gives the window pane number."""
    tmuxWindowTitle = auto()
    """If tmux integration is in use, this gives the name of the window title from tmux."""
    tmuxWindowPaneIndex = auto()
    """In tmux integration, this gives the index of the window pane. It corresponds to the pane_index property in tmux."""
    badge = auto()
    """The value of the badge. Note that the user can enter an interpolated string in the UI, but this value contains the string result of evaluating it."""
    id = auto()
    """A unique identifier for the session"""
    profileName = auto()
    """The name of the current profile."""
    showingAlternateScreen = auto()
    """\"1\" if the alternate screen buffer is active (e.g., a full-screen TUI like vim or less), otherwise \"0\"."""
    effective_root_pid = auto()
    """The process ID of the effective root process of the session."""
    foregroundJobAncestors = auto()
    """A newline-delimited list of the foreground job's ancestor process names."""
    isBroadcastSource = auto()
    """\"1\" if this session is currently a source for input broadcasting, otherwise \"0\"."""

    iterm2 = _EnumContext(PrefixedEnum(AppVarEnum, "currentSession.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    user = _EnumContext(PrefixedEnum(UserVarEnum, "currentSession.user"))
    """A context for user-set variables. Variables may be set with a custom control sequence or by using the Python scripting API. They are often set when using shell integration. See User-Defined Variables for more information."""


class _TabAtTab(StrEnum, prefix="tab"):
    """Reference view: tab (the active tab containing this session)."""

    all = "tab.*"
    """All possible tab variables."""

    id = auto()
    """The unique identifier for this tab."""
    titleOverrideFormat = auto()
    """An interpolated string giving the title to use for the tab. If not set, the session's title will be used. Note the session's title is configurable in Prefs > Profiles > General > Title and is not necessarily equal to the autoName, but may be derived from it (or not)."""
    titleOverride = auto()
    """The value of titleOverrideFormat after evaluating it as an interpolated string."""
    tmuxWindow = auto()
    """In tmux integration, this is the tmux window number this tab represents."""
    tmuxWindowTitle = auto()
    """In tmux integration, this is the tmux window title. It will only be set if the tmux option set-title is on. It comes from evaluating the tmux set-titles-strings option."""
    tmuxWindowName = auto()
    """In tmux integration, this is the tmux window name."""
    tabTitle = "tab.title"
    """The fully formatted title as it appears in the tab bar."""

    iterm2 = _EnumContext(PrefixedEnum(AppVarEnum, "tab.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    window = _EnumContext(PrefixedEnum(_WindowReference, "tab.window"))
    """A reference to the context of the enclosing window."""


class _TabAtCurrentTab(StrEnum, prefix="currentTab"):
    """Reference view: currentTab (the active tab in this window)."""

    all = "currentTab.*"
    """All possible tab variables."""

    id = auto()
    """The unique identifier for this tab."""
    titleOverrideFormat = auto()
    """An interpolated string giving the title to use for the tab. If not set, the session's title will be used. Note the session's title is configurable in Prefs > Profiles > General > Title and is not necessarily equal to the autoName, but may be derived from it (or not)."""
    titleOverride = auto()
    """The value of titleOverrideFormat after evaluating it as an interpolated string."""
    tmuxWindow = auto()
    """In tmux integration, this is the tmux window number this tab represents."""
    tmuxWindowTitle = auto()
    """In tmux integration, this is the tmux window title. It will only be set if the tmux option set-title is on. It comes from evaluating the tmux set-titles-strings option."""
    tmuxWindowName = auto()
    """In tmux integration, this is the tmux window name."""
    tabTitle = "currentTab.title"
    """The fully formatted title as it appears in the tab bar."""

    currentSession = _EnumContext(_SessionAtCurrentTabCurrentSession)
    """Defined in the context of currentSession tab's current session"""
    iterm2 = _EnumContext(PrefixedEnum(AppVarEnum, "currentTab.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""


class _WindowAtWindow(StrEnum, prefix="window"):
    """Reference view: window (the window enclosing this tab)."""

    all = "window.*"
    """All possible window variables."""

    windowTitle = "window.title"
    """The title of the window."""
    titleOverride = auto()
    """The value from evaluating the interpeted string in titleOverrideFormat, if set."""
    titleOverrideFormat = auto()
    """The window's interpolated string title. If not set, the current tab's title is used."""
    id = auto()
    """The window ID."""
    frame = auto()
    """An array of integers giving the x origin, y origin, width, and height."""
    style = auto()
    """The window style. Takes one of these values: normal, non-native full screen, native full screen, full-width top, full-width bottom, full-height left, full-height right, bottom, top, left, right, no-title-bar, compact, accessory."""
    number = auto()
    """The window number. Corresponds to the keyboard shortcut that switches to the window. Begins at 1. Unlike the keyboard shortcut, this is set even if the number is larger than 9."""
    isHotkeyWindow = auto()
    """A boolean indicating if this is a hotkey window."""

    currentTab = _EnumContext(_TabAtCurrentTab)
    """A reference to the context of the active tab."""


class SessionVarEnum(StrEnum):
    """Defined in the context of a session"""

    all = "*"
    """All possible session variables."""

    # Session Name
    autoNameFormat = auto()
    """This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created."""
    autoName = auto()
    """The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is."""
    deepestJob = auto()
    """The name of the deepest job in the process tree of the current foreground job."""
    isLocalhost = auto()
    """A boolean indicating whether the session is running on the local host or a remote host."""
    sessionName = "name"
    """The formatted name as it appears in the tab bar (excluding tmux integration decoration). For example, if the profile is configured to show the session name and job, this would take a value like My Profile (vim)."""
    presentationName = auto()
    """The session name exactly as it appears in the session title bar."""
    terminalIconName = auto()
    """The "icon" title, as set by the control sequence OSC 0 or OSC 1."""
    terminalWindowName = auto()
    """The "window" title, as set by the control sequence OSC 0 or OSC 2."""
    triggerName = auto()
    """The last session name set by a trigger."""

    # Terminal
    columns = auto()
    """Session's width in columns"""
    commandLine = auto()
    """Command line of the current foreground job (job name including arguments)"""
    jobName = auto()
    """The name of the current foreground job (e.g., "emacs")"""
    jobPid = auto()
    """The process ID of the current foreground job in this session."""
    mouseReportingMode = auto()
    """A number indicating how mouse events are reported. -1: Not reported, 0: button clicks reported, 1: not currently implemented, 2: reports clicks and drags, 3: reports clicks, drags, and movement"""
    pid = auto()
    """The process ID of the root process in this session (typically login)."""
    processTitle = auto()
    """The (perhaps modified by the process) title of a process from its argv."""
    rows = auto()
    """The session's height in rows"""
    selection = auto()
    """The currently selected text."""
    selectionLength = auto()
    """The length in UTF-8 bytes of the currently selected text."""
    termid = auto()
    """Window, tab, and pane number as used in the $TERM_SESSION_ID environment variable."""
    tty = auto()
    """The path to the local TTY device"""
    uname = auto()
    """Information about the operating system on the current host."""
    shell = auto()
    """The shell on the current host."""
    sshIntegrationLevel = auto()
    """0: No ssh integration. 1: Basic ssh integration. 2: Full ssh integration with all features available."""
    homeDirectory = auto()
    """The home directory on the current host."""
    applicationKeypad = auto()
    """A boolean indicating if the session is in application keypad mode."""
    mouseInfo = auto()
    """Describes the last mouse event. Is an array: [x coord, y coord, button number, click count, array of modifiers, bitmask of side effects, event type]. x coord is 0-based and gives the location in columns from the leftmost column. y coord is 0 at the first line in history, including lines which have since been lost if there are more lines of history than the maximum. button number is 0 for left, 1 for right, and 2 or greater for other buttons. click count is 1 for single click, 2 for double click, etc., and isn't artifically bounded. array of modifiers contains numbers for each modifier key that is pressed. They keys are: Control = 1; Option = 2; Command = 3; Shift = 4. bitmask of side effects comes by summing these values: Modify selection = 1; Perform action = 2; Open target (e.g., a URL or file) = 4; Report = 8; Move cursor = 16; Move find-on-page start location = 32; Open password manager = 64; Drag = 128. event type is 0 for mouse-up, 1 for mouse-down, 2 for drag."""
    bellCount = auto()
    """Number of times the bell has rung."""

    # Shell Integration
    hostname = auto()
    """The current hostname"""
    lastCommand = auto()
    """The last command run in the session"""
    path = auto()
    """The current working directory (this works without shell integration, but not if you ssh elsewhere)"""
    username = auto()
    """The current user name"""

    # Logging
    autoLogId = auto()
    """When automatic logging is enabled, this is the random number portion of the filename."""
    creationTimeString = auto()
    """A string giving the initial creation time of the session, used as part of the filename when automatic logging is enabled"""
    logFilename = auto()
    """If set, the filename that logging goes to. If unset, logging is off. New in version 3.4.7."""

    # tmux Integration
    tmuxClientName = auto()
    """The name of the tmux session when tmux integration is in use (e.g., user@localhost)."""
    tmuxPaneTitle = auto()
    """The title of the tmux window pane."""
    tmuxRole = auto()
    """Unset if tmux integration is not in use. Otherwise, is "gateway" for the session in which tmux -CC is running or "client" in tmux integration sessions."""
    tmuxStatusLeft = auto()
    """In tmux integration, the value of the left side of the status bar."""
    tmuxStatusRight = auto()
    """In tmux integration, the value of the right side of the status bar."""
    tmuxWindowPane = auto()
    """In tmux integration, this gives the window pane number."""
    tmuxWindowTitle = auto()
    """If tmux integration is in use, this gives the name of the window title from tmux."""
    tmuxWindowPaneIndex = auto()
    """In tmux integration, this gives the index of the window pane. It corresponds to the pane_index property in tmux."""

    # Other
    badge = auto()
    """The value of the badge. Note that the user can enter an interpolated string in the UI, but this value contains the string result of evaluating it."""
    id = auto()
    """A unique identifier for the session"""
    profileName = auto()
    """The name of the current profile."""

    # Runtime (undocumented; not in iTerm2 variable docs)
    showingAlternateScreen = auto()
    """\"1\" if the alternate screen buffer is active (e.g., a full-screen TUI like vim or less), otherwise \"0\"."""
    effective_root_pid = auto()
    """The process ID of the effective root process of the session."""
    foregroundJobAncestors = auto()
    """A newline-delimited list of the foreground job's ancestor process names."""
    isBroadcastSource = auto()
    """\"1\" if this session is currently a source for input broadcasting, otherwise \"0\"."""

    # > References to Other Contexts
    tab = _EnumContext(_TabAtTab)
    """A reference to the context of the active tab."""
    iterm2 = _EnumContext(PrefixedEnum(AppVarEnum, "iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    user = _EnumContext(PrefixedEnum(UserVarEnum, "user"))
    """A context for user-set variables. Variables may be set with a custom control sequence or by using the Python scripting API. They are often set when using shell integration. See User-Defined Variables for more information."""


class WindowVarEnum(StrEnum):
    """Defined in the context of a window"""

    all = "*"
    """All possible window variables."""

    # Window Title
    windowTitle = "title"
    """The title of the window."""
    titleOverride = auto()
    """The value from evaluating the interpeted string in titleOverrideFormat, if set."""
    titleOverrideFormat = auto()
    """The window's interpolated string title. If not set, the current tab's title is used."""

    # Other
    id = auto()
    """The window ID."""
    frame = auto()
    """An array of integers giving the x origin, y origin, width, and height."""
    style = auto()
    """The window style. Takes one of these values: normal, non-native full screen, native full screen, full-width top, full-width bottom, full-height left, full-height right, bottom, top, left, right, no-title-bar, compact, accessory."""
    number = auto()
    """The window number. Corresponds to the keyboard shortcut that switches to the window. Begins at 1. Unlike the keyboard shortcut, this is set even if the number is larger than 9."""
    isHotkeyWindow = auto()
    """A boolean indicating if this is a hotkey window."""

    # References to Other Contexts
    currentTab = _EnumContext(_TabAtCurrentTab)
    """A reference to the context of the active tab."""
    iterm2 = _EnumContext(PrefixedEnum(AppVarEnum, "iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""


class TabVarEnum(StrEnum):
    """Defined in the context of a tab"""

    all = "*"
    """All possible tab variables."""

    id = auto()
    """The unique identifier for this tab."""
    titleOverrideFormat = auto()
    """An interpolated string giving the title to use for the tab. If not set, the session's title will be used. Note the session's title is configurable in Prefs > Profiles > General > Title and is not necessarily equal to the autoName, but may be derived from it (or not)."""
    titleOverride = auto()
    """The value of titleOverrideFormat after evaluating it as an interpolated string."""
    tmuxWindow = auto()
    """In tmux integration, this is the tmux window number this tab represents."""
    tmuxWindowTitle = auto()
    """In tmux integration, this is the tmux window title. It will only be set if the tmux option set-title is on. It comes from evaluating the tmux set-titles-strings option."""
    tmuxWindowName = auto()
    """In tmux integration, this is the tmux window name."""
    tabTitle = "title"
    """The fully formatted title as it appears in the tab bar."""

    # > References to Other Contexts
    currentSession = _EnumContext(_SessionAtCurrentSession)
    """A reference to the context of the active session in this tab."""
    iterm2 = _EnumContext(PrefixedEnum(AppVarEnum, "iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    window = _EnumContext(_WindowAtWindow)
    """A reference to the context of the enclosing window."""


AppScope = Literal["iterm2"] | AppVarEnum
WindowScope = Literal["window"] | WindowVarEnum
TabScope = Literal["tab"] | TabVarEnum
SessionScope = Literal["session"] | SessionVarEnum
UserScope = Literal["user"] | UserVarEnum
VariableScope = AppScope | WindowScope | TabScope | SessionScope | UserScope

SessionVarKey = Literal[
    "*",  # - All possible session variables.
    # Session Name
    "autoNameFormat",  # - This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created.
    "autoName",  # - The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is.
    "deepestJob",  # - The name of the deepest job in the process tree of the current foreground job.
    "isLocalhost",  # - A boolean indicating whether the session is running on the local host or a remote host.
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

TabVarKey = Literal[
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
    "window.title",
    "window.titleOverride",
    "window.titleOverrideFormat",
    "window.id",
    "window.frame",
    "window.style",
    "window.number",
    "window.isHotkeyWindow",
]
"""Defined in the context of a tab"""

WindowVarKey = Literal[
    "*",  # - All possible window variables.
    # Window Title
    "title",
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

UserVarKey = Literal["*"] | str
"""
The only variables that users may directly control are those in the "user" scope of a session.
For example, you could set a variable named "gitBranch" to the name of the current git branch.
This value would then be available to display in the session title, badge, or other places,
and would be available to Python API scripts. You'd reference it as user.gitBranch.

See "Setting User-Defined Variables" in Scripting Fundamentals for details on setting them.
"""

AppVarKey = Literal[
    "*",  # - All possible global variables.
    "effectiveTheme",  # - A space-delimited list of words describing the OS theme (e.g., "dark", "light highContrast", "dark minimal")
    "localhostName",  # - The best guess of what localhost's hostname is
    "pid",  # - The process ID of the iTerm2 app
    "appBundlePath",  # - The path to the iTerm.app executable.
]
"""Defined in the global context"""


AppVariable = AppVarEnum | AppVarKey | str
UserVariable = UserVarEnum | UserVarKey | str

_NestedSessionVariables = SessionVarEnum.tab | SessionVarEnum.iterm2 | SessionVarEnum.user
SessionVariable = SessionVarEnum | _NestedSessionVariables | SessionVarKey | str

_NestedTabVariables = TabVarEnum.currentSession | TabVarEnum.iterm2 | TabVarEnum.window
TabVariable = TabVarEnum | _NestedTabVariables | TabVarKey | str

_NestedWindowVariables = WindowVarEnum.currentTab | WindowVarEnum.iterm2
WindowVariable = WindowVarEnum | _NestedWindowVariables | WindowVarKey | str

Variable = AppVariable | UserVariable | SessionVariable | TabVariable | WindowVariable
