from __future__ import annotations

from enum import StrEnum, nonmember
from typing import TYPE_CHECKING, Literal, TypeAlias, TypedDict, cast, overload

from iterm2 import profile, prompt, app, session, window, tab


if TYPE_CHECKING:
    from iterm2 import api_pb2

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
    app: app.App
    window: window.Window
    tab: tab.Tab
    session: session.Session
    profile: profile.Profile

    is_hotkey_window: bool
    """Whether the current window is a hotkey window."""


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
    "parentSession",  # - The session that was current when this sessionw as created. This is an alias to the context of that session so you can access its variables.
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
    # > References to Other Contexts
    "tab.id",
    "tab.titleOverrideFormat",
    "tab.titleOverride",
    "tab.tmuxWindow",
    "tab.tmuxWindowTitle",
    "tab.tmuxWindowName",
    "tab.tabTitle",
    "iterm2.effectiveTheme",
    "iterm2.localhostName",
    "iterm2.pid",
    "iterm2.appBundlePath",
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
    "currentSession.autoNameFormat",
    "currentSession.autoName",
    "currentSession.tabName",
    "currentSession.presentationName",
    "currentSession.terminalIconName",
    "currentSession.terminalWindowName",
    "currentSession.triggerName",
    "currentSession.columns",
    "currentSession.commandLine",
    "currentSession.jobName",
    "currentSession.jobPid",
    "currentSession.mouseReportingMode",
    "currentSession.parentSession",
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
    "iterm2.effectiveTheme",
    "iterm2.localhostName",
    "iterm2.pid",
    "iterm2.appBundlePath",
    "window.titleOverride",
    "window.titleOverrideFormat",
    "window.id",
    "window.frame",
    "window.style",
    "window.number",
    "window.isHotkeyWindow",
]
"""
The only variables that users may directly control are those in the "user" scope of a session.
For example, you could set a variable named "gitBranch" to the name of the current git branch.
This value would then be available to display in the session title, badge, or other places,
and would be available to Python API scripts. You'd reference it as user.gitBranch.

See "Setting User-Defined Variables" in Scripting Fundamentals for details on setting them.
"""

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
    "currentTab.id",
    "currentTab.titleOverrideFormat",
    "currentTab.titleOverride",
    "currentTab.tmuxWindow",
    "currentTab.tmuxWindowTitle",
    "currentTab.tmuxWindowName",
    "currentTab.tabTitle",
    "iterm2.effectiveTheme",
    "iterm2.localhostName",
    "iterm2.pid",
    "iterm2.appBundlePath",
]
"""Defined in the context of a window"""

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
    tabName = "tabName"
    presentationName = "presentationName"
    terminalIconName = "terminalIconName"
    terminalWindowName = "terminalWindowName"
    triggerName = "triggerName"
    columns = "columns"
    commandLine = "commandLine"
    jobName = "jobName"
    jobPid = "jobPid"
    mouseReportingMode = "mouseReportingMode"
    parentSession = "parentSession"
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


class SessionVar(StrEnum):
    """Defined in the context of a session"""

    all = SessionEnum.all
    """All possible session variables."""

    # Session Name
    autoNameFormat = SessionEnum.autoNameFormat
    """This is an interpolated string from which the autoName variable is computed. It can be modified by changing the "Session Name" field in Edit Session…, by a trigger that sets the session name, or by an OSC control sequence that sets the icon title. It is initialized to the profile name when a new session is created."""
    autoName = SessionEnum.autoName
    """The result of evaluating the autoNameFormat interpolated string. This attempts to match the user's intuition of the what the session's name is."""
    tabName = SessionEnum.tabName
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
    parentSession = SessionEnum.parentSession
    """The session that was current when this sessionw as created. This is an alias to the context of that session so you can access its variables."""
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

    # > References to Other Contexts
    tab = nonmember(PrefixedEnum(TabEnum, "tab"))
    """A reference to the context of the active tab."""
    iterm2 = nonmember(PrefixedEnum(GlobalVar, "iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    user = nonmember(PrefixedEnum(StrEnum, "user"))
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
    currentTab = nonmember(PrefixedEnum(TabEnum, "currentTab"))
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
    currentSession = nonmember(PrefixedEnum(SessionEnum, "currentSession"))
    """A reference to the context of the active session in this tab."""
    iterm2 = nonmember(PrefixedEnum(GlobalVar, "iterm2"))
    """A reference to the variables belonging to the application (i.e., the global context)."""
    window = nonmember(PrefixedEnum(WindowEnum, "window"))
    """A reference to the context of the enclosing window."""


type NestedSessionVariables = SessionVar.iterm2 | SessionVar.tab | SessionVar.user
type SessionVariable = SessionVar | NestedSessionVariables | SessionVars

type NestedTabVariables = TabVar.currentSession | TabVar.iterm2 | TabVar.window
type TabVariable = TabVar | NestedTabVariables | TabVars

type NestedWindowVariables = WindowVar.currentTab | WindowVar.iterm2
type WindowVariable = WindowVar | NestedWindowVariables | WindowVars

type GlobalVariable = GlobalVar | GlobalVars

type NestedEnumVariables = NestedSessionVariables | NestedTabVariables | NestedWindowVariables
type EnumVariables = SessionVar | TabVar | WindowVar | GlobalVar | NestedEnumVariables
type LiteralVariables = SessionVars | TabVars | WindowVars | GlobalVars
type Variable = EnumVariables | LiteralVariables


class Prompt(prompt.Prompt):
    _Prompt__proto: api_pb2.GetPromptResponse


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
    async def async_get(connection: Connection, guids: list[str] | None = None) -> list[PartialProfile]: # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[PartialProfile], await profile.PartialProfile.async_get(connection, guids))

    @staticmethod
    async def async_get_default(connection: Connection, properties: list[str] | None = None) -> PartialProfile:
        properties = properties or ["Guid", "Name"]
        return cast(PartialProfile, await profile.PartialProfile.async_get_default(connection, properties))

    @staticmethod
    async def async_query(connection: Connection, guids: list[str] | None = None, properties: list[str] | None = None) -> list[PartialProfile]: # pyright: ignore[reportIncompatibleMethodOverride]
        properties = properties or ["Guid", "Name"]
        return cast(list[PartialProfile], await profile.PartialProfile.async_query(connection, guids, properties))


class Session(session.Session):
    async def async_get_profile(self) -> Profile:
        return cast(Profile, await super().async_get_profile())


class Tab(tab.Tab):
    @property
    def all_sessions(self) -> list[Session]: # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Session], super().all_sessions)


class Window(window.Window):
    @property
    def tabs(self) -> list[Tab]: # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Tab], super().tabs)

    async def async_create_tab(self, profile: str | None = None, command: str | None = None, index: int | None = None, profile_customizations: profile.LocalWriteOnlyProfile | None = None) -> Tab | None:
        return cast(Tab, await super().async_create_tab(profile, command, index, profile_customizations))


class App(app.App):
    @property
    def windows(self) -> list[Window]: # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Window], super().windows)

    def get_session_by_id(self, session_id: str, include_buried: bool = True) -> Session | None:
        return cast(Session | None, super().get_session_by_id(session_id, include_buried))

    async def window_delegate_get_tab_by_id(self, tab_id: str) -> Tab | None:
        return cast(Tab, await super().window_delegate_get_tab_by_id(tab_id))

    async def tab_delegate_get_window_by_id(self, window_id: str) -> Window | None:
        return cast(Window, await super().tab_delegate_get_window_by_id(window_id))


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
