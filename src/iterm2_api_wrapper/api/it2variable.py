from enum import StrEnum, nonmember
from typing import Literal, cast, overload


# NOTE: Check https://iterm2.com/documentation-variables.html for potential updates


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

    actual_prefix = prefix or EnumT.__name__.removeprefix("_")
    members = {m.name: f"{actual_prefix}.{m.value}" for m in EnumT if m.value != "*"}
    # Pure-wildcard contexts (e.g. UserVar) have no concrete members; keep the
    # wildcard itself, prefixed, so e.g. SessionVar.user.all -> "user.*".
    if not members:
        members = {m.name: f"{actual_prefix}.*" for m in EnumT if m.value == "*"}
    return cast(type[StrEnum], StrEnum(f"_{EnumT.__name__}Prefixed", names=members))


class _SessionReference(StrEnum):
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


class _TabReference(StrEnum):
    all = "*"
    id = "id"
    titleOverrideFormat = "titleOverrideFormat"
    titleOverride = "titleOverride"
    tmuxWindow = "tmuxWindow"
    tmuxWindowTitle = "tmuxWindowTitle"
    tmuxWindowName = "tmuxWindowName"
    tabTitle = "title"


class _WindowReference(StrEnum):
    all = "*"
    titleOverride = "titleOverride"
    titleOverrideFormat = "titleOverrideFormat"
    id = "id"
    frame = "frame"
    style = "style"
    number = "number"
    isHotkeyWindow = "isHotkeyWindow"


class _UserReference(StrEnum):
    all = "*"


class AppVarEnum(StrEnum):
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


class UserVarEnum(StrEnum):
    all = _UserReference.all


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

    user = nonmember(PrefixedEnum(UserVarEnum, "currentSession.parentSession.user"))
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

    user = nonmember(PrefixedEnum(UserVarEnum, "currentTab.currentSession.user"))
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

    tab = nonmember(PrefixedEnum(_TabReference, "parentSession.tab"))
    """A reference to the context of the parent session's active tab."""
    iterm2 = nonmember(PrefixedEnum(AppVarEnum, "parentSession.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    user = nonmember(PrefixedEnum(UserVarEnum, "parentSession.user"))
    """A context for user-set variables. Variables may be set with a custom control sequence or by using the Python scripting API. They are often set when using shell integration. See User-Defined Variables for more information."""


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

    iterm2 = nonmember(PrefixedEnum(AppVarEnum, "currentSession.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    user = nonmember(PrefixedEnum(UserVarEnum, "currentSession.user"))
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

    iterm2 = nonmember(PrefixedEnum(AppVarEnum, "tab.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    window = nonmember(PrefixedEnum(_WindowReference, "tab.window"))
    """A reference to the context of the enclosing window."""


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
    iterm2 = nonmember(PrefixedEnum(AppVarEnum, "currentTab.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""


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

    iterm2 = nonmember(PrefixedEnum(AppVarEnum, "window.iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""


class SessionVarEnum(StrEnum):
    """Defined in the context of a session"""

    all = _SessionReference.all
    """All possible session variables."""

    # Session Name
    autoNameFormat = _SessionReference.autoNameFormat
    """This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created."""
    autoName = _SessionReference.autoName
    """The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is."""
    sessionName = _SessionReference.sessionName
    """The formatted name as it appears in the tab bar (excluding tmux integration decoration). For example, if the profile is configured to show the session name and job, this would take a value like My Profile (vim)."""
    presentationName = _SessionReference.presentationName
    """The session name exactly as it appears in the session title bar."""
    terminalIconName = _SessionReference.terminalIconName
    """The "icon" title, as set by the control sequence OSC 0 or OSC 1."""
    terminalWindowName = _SessionReference.terminalWindowName
    """The "window" title, as set by the control sequence OSC 0 or OSC 2."""
    triggerName = _SessionReference.triggerName
    """The last session name set by a trigger."""

    # Terminal
    columns = _SessionReference.columns
    """Session's width in columns"""
    commandLine = _SessionReference.commandLine
    """Command line of the current foreground job (job name including arguments)"""
    jobName = _SessionReference.jobName
    """The name of the current foreground job (e.g., "emacs")"""
    jobPid = _SessionReference.jobPid
    """The process ID of the current foreground job in this session."""
    mouseReportingMode = _SessionReference.mouseReportingMode
    """A number indicating how mouse events are reported. -1: Not reported, 0: button clicks reported, 1: not currently implemented, 2: reports clicks and drags, 3: reports clicks, drags, and movement"""
    pid = _SessionReference.pid
    """The process ID of the root process in this session (typically login)."""
    processTitle = _SessionReference.processTitle
    """The (perhaps modified by the process) title of a process from its argv."""
    rows = _SessionReference.rows
    """The session's height in rows"""
    selection = _SessionReference.selection
    """The currently selected text."""
    selectionLength = _SessionReference.selectionLength
    """The length in UTF-8 bytes of the currently selected text."""
    termid = _SessionReference.termid
    """Window, tab, and pane number as used in the $TERM_SESSION_ID environment variable."""
    tty = _SessionReference.tty
    """The path to the local TTY device"""
    uname = _SessionReference.uname
    """Information about the operating system on the current host."""
    shell = _SessionReference.shell
    """The shell on the current host."""
    sshIntegrationLevel = _SessionReference.sshIntegrationLevel
    """0: No ssh integration. 1: Basic ssh integration. 2: Full ssh integration with all features available."""
    homeDirectory = _SessionReference.homeDirectory
    """The home directory on the current host."""
    applicationKeypad = _SessionReference.applicationKeypad
    """A boolean indicating if the session is in application keypad mode."""
    mouseInfo = _SessionReference.mouseInfo
    """Describes the last mouse event. Is an array: [x coord, y coord, button number, click count, array of modifiers, bitmask of side effects, event type]. x coord is 0-based and gives the location in columns from the leftmost column. y coord is 0 at the first line in history, including lines which have since been lost if there are more lines of history than the maximum. button number is 0 for left, 1 for right, and 2 or greater for other buttons. click count is 1 for single click, 2 for double click, etc., and isn't artifically bounded. array of modifiers contains numbers for each modifier key that is pressed. They keys are: Control = 1; Option = 2; Command = 3; Shift = 4. bitmask of side effects comes by summing these values: Modify selection = 1; Perform action = 2; Open target (e.g., a URL or file) = 4; Report = 8; Move cursor = 16; Move find-on-page start location = 32; Open password manager = 64; Drag = 128. event type is 0 for mouse-up, 1 for mouse-down, 2 for drag."""
    bellCount = _SessionReference.bellCount
    """Number of times the bell has rung."""

    # Shell Integration
    hostname = _SessionReference.hostname
    """The current hostname"""
    lastCommand = _SessionReference.lastCommand
    """The last command run in the session"""
    path = _SessionReference.path
    """The current working directory (this works without shell integration, but not if you ssh elsewhere)"""
    username = _SessionReference.username
    """The current user name"""

    # Logging
    autoLogId = _SessionReference.autoLogId
    """When automatic logging is enabled, this is the random number portion of the filename."""
    creationTimeString = _SessionReference.creationTimeString
    """A string giving the initial creation time of the session, used as part of the filename when automatic logging is enabled"""
    logFilename = _SessionReference.logFilename
    """If set, the filename that logging goes to. If unset, logging is off. New in version 3.4.7."""

    # tmux Integration
    tmuxClientName = _SessionReference.tmuxClientName
    """The name of the tmux session when tmux integration is in use (e.g., user@localhost)."""
    tmuxPaneTitle = _SessionReference.tmuxPaneTitle
    """The title of the tmux window pane."""
    tmuxRole = _SessionReference.tmuxRole
    """Unset if tmux integration is not in use. Otherwise, is "gateway" for the session in which tmux -CC is running or "client" in tmux integration sessions."""
    tmuxStatusLeft = _SessionReference.tmuxStatusLeft
    """In tmux integration, the value of the left side of the status bar."""
    tmuxStatusRight = _SessionReference.tmuxStatusRight
    """In tmux integration, the value of the right side of the status bar."""
    tmuxWindowPane = _SessionReference.tmuxWindowPane
    """In tmux integration, this gives the window pane number."""
    tmuxWindowTitle = _SessionReference.tmuxWindowTitle
    """If tmux integration is in use, this gives the name of the window title from tmux."""
    tmuxWindowPaneIndex = _SessionReference.tmuxWindowPaneIndex
    """In tmux integration, this gives the index of the window pane. It corresponds to the pane_index property in tmux."""

    # Other
    badge = _SessionReference.badge
    """The value of the badge. Note that the user can enter an interpolated string in the UI, but this value contains the string result of evaluating it."""
    id = _SessionReference.id
    """A unique identifier for the session"""
    profileName = _SessionReference.profileName
    """The name of the current profile."""

    # Runtime (undocumented; not in iTerm2 variable docs)
    showingAlternateScreen = _SessionReference.showingAlternateScreen
    """\"1\" if the alternate screen buffer is active (e.g., a full-screen TUI like vim or less), otherwise \"0\"."""
    effective_root_pid = _SessionReference.effective_root_pid
    """The process ID of the effective root process of the session."""
    foregroundJobAncestors = _SessionReference.foregroundJobAncestors
    """A newline-delimited list of the foreground job's ancestor process names."""
    isBroadcastSource = _SessionReference.isBroadcastSource
    """\"1\" if this session is currently a source for input broadcasting, otherwise \"0\"."""
    parentSession = nonmember(_SessionAtParentSession)
    """The session that was current when this session as created. This is an alias to the context of that session so you can access its variables."""

    # > References to Other Contexts
    tab = nonmember(_TabAtTab)
    """A reference to the context of the active tab."""
    iterm2 = nonmember(PrefixedEnum(AppVarEnum, "iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    user = nonmember(PrefixedEnum(UserVarEnum, "user"))
    """A context for user-set variables. Variables may be set with a custom control sequence or by using the Python scripting API. They are often set when using shell integration. See User-Defined Variables for more information."""


class WindowVarEnum(StrEnum):
    """Defined in the context of a window"""

    all = _WindowReference.all
    """All possible window variables."""

    # Window Title
    titleOverride = _WindowReference.titleOverride
    """The value from evaluating the interpeted string in titleOverrideFormat, if set."""
    titleOverrideFormat = _WindowReference.titleOverrideFormat
    """The window's interpolated string title. If not set, the current tab's title is used."""

    # Other
    id = _WindowReference.id
    """The window ID."""
    frame = _WindowReference.frame
    """An array of integers giving the x origin, y origin, width, and height."""
    style = _WindowReference.style
    """The window style. Takes one of these values: normal, non-native full screen, native full screen, full-width top, full-width bottom, full-height left, full-height right, bottom, top, left, right, no-title-bar, compact, accessory."""
    number = _WindowReference.number
    """The window number. Corresponds to the keyboard shortcut that switches to the window. Begins at 1. Unlike the keyboard shortcut, this is set even if the number is larger than 9."""
    isHotkeyWindow = _WindowReference.isHotkeyWindow
    """A boolean indicating if this is a hotkey window."""

    # References to Other Contexts
    currentTab = nonmember(_TabAtCurrentTab)
    """A reference to the context of the active tab."""
    iterm2 = nonmember(PrefixedEnum(AppVarEnum, "iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""


class TabVarEnum(StrEnum):
    """Defined in the context of a tab"""

    all = _TabReference.all
    """All possible tab variables."""
    id = _TabReference.id
    """The unique identifier for this tab."""
    titleOverrideFormat = _TabReference.titleOverrideFormat
    """An interpolated string giving the title to use for the tab. If not set, the session's title will be used. Note the session's title is configurable in Prefs > Profiles > General > Title and is not necessarily equal to the autoName, but may be derived from it (or not)."""
    titleOverride = _TabReference.titleOverride
    """The value of titleOverrideFormat after evaluating it as an interpolated string."""
    tmuxWindow = _TabReference.tmuxWindow
    """In tmux integration, this is the tmux window number this tab represents."""
    tmuxWindowTitle = _TabReference.tmuxWindowTitle
    """In tmux integration, this is the tmux window title. It will only be set if the tmux option set-title is on. It comes from evaluating the tmux set-titles-strings option."""
    tmuxWindowName = _TabReference.tmuxWindowName
    """In tmux integration, this is the tmux window name."""
    tabTitle = _TabReference.tabTitle
    """The fully formatted title as it appears in the tab bar."""

    # > References to Other Contexts
    currentSession = nonmember(_SessionAtCurrentSession)
    """A reference to the context of the active session in this tab."""
    iterm2 = nonmember(PrefixedEnum(AppVarEnum, "iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    window = nonmember(_WindowAtWindow)
    """A reference to the context of the enclosing window."""


type AppScope = Literal["iterm2"] | AppVarEnum
type WindowScope = Literal["window"] | WindowVarEnum
type TabScope = Literal["tab"] | TabVarEnum
type SessionScope = Literal["session"] | SessionVarEnum
type UserScope = Literal["user"] | UserVarEnum
type VariableScope = AppScope | WindowScope | TabScope | SessionScope | UserScope

type SessionVarKey = Literal[
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

type TabVarKey = Literal[
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

type WindowVarKey = Literal[
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

type UserVarKey = Literal["*"] | str
"""
The only variables that users may directly control are those in the "user" scope of a session.
For example, you could set a variable named "gitBranch" to the name of the current git branch.
This value would then be available to display in the session title, badge, or other places,
and would be available to Python API scripts. You'd reference it as user.gitBranch.

See "Setting User-Defined Variables" in Scripting Fundamentals for details on setting them.
"""

type AppVarKey = Literal[
    "*",  # - All possible global variables.
    "effectiveTheme",  # - A space-delimited list of words describing the OS theme (e.g., "dark", "light highContrast", "dark minimal")
    "localhostName",  # - The best guess of what localhost's hostname is
    "pid",  # - The process ID of the iTerm2 app
    "appBundlePath",  # - The path to the iTerm.app executable.
]
"""Defined in the global context"""


type AppVariable = AppVarEnum | AppVarKey
type UserVariable = UserVarEnum | UserVarKey

type _NestedSessionVariables = (
    SessionVarEnum.parentSession | SessionVarEnum.tab | SessionVarEnum.iterm2 | SessionVarEnum.user
)
type SessionVariable = SessionVarEnum | _NestedSessionVariables | SessionVarKey

type _NestedTabVariables = TabVarEnum.currentSession | TabVarEnum.iterm2 | TabVarEnum.window
type TabVariable = TabVarEnum | _NestedTabVariables | TabVarKey

type _NestedWindowVariables = WindowVarEnum.currentTab | WindowVarEnum.iterm2
type WindowVariable = WindowVarEnum | _NestedWindowVariables | WindowVarKey

type Variable = AppVariable | UserVariable | SessionVariable | TabVariable | WindowVariable
