"""Typed views of the iTerm2 profile property dictionary.

``Profile.all_properties`` returns the raw plist-backed dictionary keyed by
iTerm2's human-readable property names (e.g. ``"Load Shell Integration
Automatically"``). Those keys contain spaces, hyphens, colons, and
parentheses, so the types below use the functional ``TypedDict`` syntax to
preserve the exact key strings while still providing key autocompletion and
per-key value types.

All top-level keys are ``total=False`` because a profile dictionary only
contains the properties that have been explicitly set for that profile.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, NotRequired, Protocol, TypedDict, cast

from iterm2 import profile


if TYPE_CHECKING:
    from .it2connection import Connection


type ColorSpace = Literal["sRGB", "Dev", "P3"]
type BoolInt = Literal[0, 1]

ProfileColor = TypedDict(
    "ProfileColor",
    {
        "Alpha Component": float,
        "Blue Component": float,
        "Color Space": NotRequired[ColorSpace],
        "Green Component": float,
        "Red Component": float,
    },
)

KeyboardMapEntry = TypedDict(
    "KeyboardMapEntry", {"Action": int, "Apply Mode": BoolInt, "Escaping": int, "Text": str, "Version": int}
)

type KeyboardMap = dict[str, KeyboardMapEntry]
"""Maps keystroke identifiers like ``"0x74-0x100000"`` to their bound actions."""


class SemanticHistory(TypedDict):
    action: str
    editor: str
    text: str


class SmartSelectionAction(TypedDict):
    action: int
    parameter: str
    title: str


class SmartSelectionRule(TypedDict):
    notes: str
    precision: Literal["very_low", "low", "normal", "high", "very_high"]
    regex: str
    actions: NotRequired[list[SmartSelectionAction]]


class TriggerEventParams(TypedDict, total=False):
    jobName: str
    exitCodeFilter: str
    threshold: int
    sequenceId: str


class Trigger(TypedDict):
    action: str
    contentregex: str
    disabled: bool
    matchType: int
    name: str
    parameter: str
    partial: bool
    regex: str
    eventParams: NotRequired[TriggerEventParams]


class TitleFunctionEntry(TypedDict):
    value: str


class StatusBarAction(TypedDict):
    action: int
    applyMode: BoolInt
    escaping: BoolInt
    parameter: str
    title: str
    version: int


StatusBarAdvancedConfiguration = TypedDict(
    "StatusBarAdvancedConfiguration",
    {"algorithm": BoolInt, "auto-rainbow style": BoolInt, "font": str, "remove empty components": bool},
    total=False,
)

StatusBarKnobs = TypedDict(
    "StatusBarKnobs",
    {
        "action": StatusBarAction,
        "base: compression resistance": float,
        "base: priority": float,
        "maxwidth": float | str,
        "minwidth": float | str,
        "path": str,
        "shared font": str,
        "shared text color": ProfileColor,
    },
    total=False,
)

StatusBarComponentConfiguration = TypedDict(
    "StatusBarComponentConfiguration",
    {"knobs": StatusBarKnobs, "layout advanced configuration dictionary value": StatusBarAdvancedConfiguration},
)

StatusBarComponent = TypedDict("StatusBarComponent", {"class": str, "configuration": StatusBarComponentConfiguration})

StatusBarLayout = TypedDict(
    "StatusBarLayout",
    {"advanced configuration": StatusBarAdvancedConfiguration, "components": list[StatusBarComponent]},
)

ProfileProperties = TypedDict(
    "ProfileProperties",
    {
        "ASCII Anti Aliased": BoolInt,
        "ASCII Ligatures": BoolInt,
        "AWDS Pane Directory": str,
        "AWDS Pane Option": str,
        "AWDS Tab Directory": str,
        "AWDS Tab Option": str,
        "AWDS Window Directory": str,
        "AWDS Window Option": str,
        "Active Pane Border Color": ProfileColor,
        "Active Pane Border Color (Dark)": ProfileColor,
        "Active Pane Border Color (Light)": ProfileColor,
        "Allow Alternate Mouse Scroll": BoolInt,
        "Allow Change Cursor Blink": BoolInt,
        "Allow Paste Bracketing": BoolInt,
        "Allow Title Reporting": BoolInt,
        "Allow Title Setting": BoolInt,
        "Allow modifyOtherKeys": BoolInt,
        "Ambiguous Double Width": BoolInt,
        "Animate Movement": BoolInt,
        "Animate Movement Only in Interactive Apps": BoolInt,
        "Ansi 0 Color": ProfileColor,
        "Ansi 0 Color (Dark)": ProfileColor,
        "Ansi 0 Color (Light)": ProfileColor,
        "Ansi 1 Color": ProfileColor,
        "Ansi 1 Color (Dark)": ProfileColor,
        "Ansi 1 Color (Light)": ProfileColor,
        "Ansi 2 Color": ProfileColor,
        "Ansi 2 Color (Dark)": ProfileColor,
        "Ansi 2 Color (Light)": ProfileColor,
        "Ansi 3 Color": ProfileColor,
        "Ansi 3 Color (Dark)": ProfileColor,
        "Ansi 3 Color (Light)": ProfileColor,
        "Ansi 4 Color": ProfileColor,
        "Ansi 4 Color (Dark)": ProfileColor,
        "Ansi 4 Color (Light)": ProfileColor,
        "Ansi 5 Color": ProfileColor,
        "Ansi 5 Color (Dark)": ProfileColor,
        "Ansi 5 Color (Light)": ProfileColor,
        "Ansi 6 Color": ProfileColor,
        "Ansi 6 Color (Dark)": ProfileColor,
        "Ansi 6 Color (Light)": ProfileColor,
        "Ansi 7 Color": ProfileColor,
        "Ansi 7 Color (Dark)": ProfileColor,
        "Ansi 7 Color (Light)": ProfileColor,
        "Ansi 8 Color": ProfileColor,
        "Ansi 8 Color (Dark)": ProfileColor,
        "Ansi 8 Color (Light)": ProfileColor,
        "Ansi 9 Color": ProfileColor,
        "Ansi 9 Color (Dark)": ProfileColor,
        "Ansi 9 Color (Light)": ProfileColor,
        "Ansi 10 Color": ProfileColor,
        "Ansi 10 Color (Dark)": ProfileColor,
        "Ansi 10 Color (Light)": ProfileColor,
        "Ansi 11 Color": ProfileColor,
        "Ansi 11 Color (Dark)": ProfileColor,
        "Ansi 11 Color (Light)": ProfileColor,
        "Ansi 12 Color": ProfileColor,
        "Ansi 12 Color (Dark)": ProfileColor,
        "Ansi 12 Color (Light)": ProfileColor,
        "Ansi 13 Color": ProfileColor,
        "Ansi 13 Color (Dark)": ProfileColor,
        "Ansi 13 Color (Light)": ProfileColor,
        "Ansi 14 Color": ProfileColor,
        "Ansi 14 Color (Dark)": ProfileColor,
        "Ansi 14 Color (Light)": ProfileColor,
        "Ansi 15 Color": ProfileColor,
        "Ansi 15 Color (Dark)": ProfileColor,
        "Ansi 15 Color (Light)": ProfileColor,
        "Answerback String": str,
        "Application Keypad Allowed": BoolInt,
        "Archive Directory": str,
        "Archive On Closure": BoolInt,
        "Automatically Enable Alternate Mouse Scroll": BoolInt,
        "Automatically Log": BoolInt,
        "BM Growl": BoolInt,
        "Background Color": ProfileColor,
        "Background Color (Dark)": ProfileColor,
        "Background Color (Light)": ProfileColor,
        "Background Image Folder Interval": int,
        "Background Image Mode": int,
        "Background Image Source Mode": int,
        "Badge Color": ProfileColor,
        "Badge Color (Dark)": ProfileColor,
        "Badge Color (Light)": ProfileColor,
        "Badge Text": str,
        "Bindings": dict[str, Any],
        "Blend": float,
        "Blink Allowed": BoolInt,
        "Blinking Cursor": BoolInt,
        "Blur": BoolInt,
        "Blur Radius": float,
        "Bold Color": ProfileColor,
        "Bold Color (Dark)": ProfileColor,
        "Bold Color (Light)": ProfileColor,
        "Bound Hosts": list[Any],
        "Brighten Bold Text": BoolInt,
        "Brighten Bold Text (Dark)": BoolInt,
        "Brighten Bold Text (Light)": BoolInt,
        "Browser Extension Active IDs": list[str],
        "Browser Extensions Root": str,
        "Browser Zoom": int,
        "Buffer Input by Default": BoolInt,
        "Character Encoding": int,
        "Close Sessions On End": BoolInt,
        "Columns": int,
        "Command": str,
        "Composer Top Offset": int,
        "Cursor Boost": float,
        "Cursor Boost (Dark)": float,
        "Cursor Boost (Light)": float,
        "Cursor Color": ProfileColor,
        "Cursor Color (Dark)": ProfileColor,
        "Cursor Color (Light)": ProfileColor,
        "Cursor Guide Color": ProfileColor,
        "Cursor Guide Color (Dark)": ProfileColor,
        "Cursor Guide Color (Light)": ProfileColor,
        "Cursor Hidden When Unfocused": BoolInt,
        "Cursor Shadow": BoolInt,
        "Cursor Smooth Slide": BoolInt,
        "Cursor Text Color": ProfileColor,
        "Cursor Text Color (Dark)": ProfileColor,
        "Cursor Text Color (Light)": ProfileColor,
        "Cursor Type": int,
        "Custom Command": Literal["Yes", "No"],
        "Custom Directory": str,
        "Custom Icon Path": str,
        "Custom Locale": str,
        "Custom Tab Title": str,
        "Custom Window Title": str,
        "Default Pane Locked": BoolInt,
        "Dev Null Mode": BoolInt,
        "Disable Printing": BoolInt,
        "Disable Smcup Rmcup": BoolInt,
        "Disable Window Resizing": BoolInt,
        "Disable Window Resizing by Unfocused Sessions": BoolInt,
        "Drag to Scroll in Alternate Screen Mode Disabled": BoolInt,
        "Draw Powerline Glyphs": BoolInt,
        "Enable Progress Bars": BoolInt,
        "Enable Triggers in Interactive Apps": BoolInt,
        "Faint Text Alpha": float,
        "Faint Text Alpha (Dark)": float,
        "Faint Text Alpha (Light)": float,
        "Flashing Bell": BoolInt,
        "Foreground Color": ProfileColor,
        "Foreground Color (Dark)": ProfileColor,
        "Foreground Color (Light)": ProfileColor,
        "Function Key": int,
        "Guid": str,
        "Harmonize 256 Colors": BoolInt,
        "Harmonize 256 Colors (Dark)": BoolInt,
        "Harmonize 256 Colors (Light)": BoolInt,
        "Has Hotkey": BoolInt,
        "Height Percentage": float,
        "Height in Points": float,
        "Hide After Opening": BoolInt,
        "Horizontal Spacing": float,
        "HotKey Activated By Modifier": BoolInt,
        "HotKey Alternate Shortcuts": list[Any],
        "HotKey Characters": str,
        "HotKey Characters Ignoring Modifiers": str,
        "HotKey Key Code": int,
        "HotKey Modifier Activation": int,
        "HotKey Modifier Flags": int,
        "HotKey Window Animates": BoolInt,
        "HotKey Window AutoHides": BoolInt,
        "HotKey Window Dock Click Action": int,
        "HotKey Window Floats": BoolInt,
        "HotKey Window Reopens On Activation": BoolInt,
        "IME Cursor Color": ProfileColor,
        "IME Cursor Color (Dark)": ProfileColor,
        "IME Cursor Color (Light)": ProfileColor,
        "Icon": int,
        "Idle Code": int,
        "Idle Period": float,
        "Initial Text": str,
        "Initial URL": str,
        "Initial Use Transparency": BoolInt,
        "Instant Replay": BoolInt,
        "Jobs to Ignore": list[str],
        "Keyboard Map": KeyboardMap,
        "Left Command Key": int,
        "Left Control Key": int,
        "Left Option Key Changeable": BoolInt,
        "Link Color": ProfileColor,
        "Link Color (Dark)": ProfileColor,
        "Link Color (Light)": ProfileColor,
        "Load Shell Integration Automatically": BoolInt,
        "Lock Window Size Automatically": BoolInt,
        "Log Directory": str,
        "Log Filename Format": str,
        "Match Background Color": ProfileColor,
        "Match Background Color (Dark)": ProfileColor,
        "Match Background Color (Light)": ProfileColor,
        "Minimum Contrast": float,
        "Minimum Contrast (Dark)": float,
        "Minimum Contrast (Light)": float,
        "Mouse Reporting": BoolInt,
        "Mouse Reporting allow clicks and drags": BoolInt,
        "Mouse Reporting allow mouse wheel": BoolInt,
        "Movement Keys Scroll Outside Interactive Apps": BoolInt,
        "Name": str,
        "Non Ascii Font": str,
        "Non-ASCII Anti Aliased": BoolInt,
        "Non-ASCII Ligatures": BoolInt,
        "Normal Font": str,
        "Only The Default BG Color Uses Transparency": BoolInt,
        "Open Password Manager Automatically": BoolInt,
        "Open Toolbelt": BoolInt,
        "Option Key Sends": int,
        "Place Prompt at First Column": BoolInt,
        "Plain Text Logging": BoolInt,
        "Prevent Automatic Profile Switching": BoolInt,
        "Prevent Opening in a Tab": BoolInt,
        "Profile Type (Phony)": int,
        "Progress Bar Color Scheme": str,
        "Progress Bar Height": int,
        "Prompt Before Closing 2": int,
        "Prompt Path Click Opens Navigator": BoolInt,
        "Reduce Flicker": BoolInt,
        "Restrict Alternate Mouse Scroll to Vertical": BoolInt,
        "Restrict Mouse Reporting to Alternate Screen Mode": BoolInt,
        "Right Command Key": int,
        "Right Control Key": int,
        "Right Option Key Changeable": BoolInt,
        "Right Option Key Sends": int,
        "Rows": int,
        "Run Command In Login Shell": BoolInt,
        "SSH": dict[str, Any],
        "Screen": int,
        "Scrollback Lines": int,
        "Scrollback With Status Bar": BoolInt,
        "Scrollback in Alternate Screen": BoolInt,
        "Selected Text Color": ProfileColor,
        "Selected Text Color (Dark)": ProfileColor,
        "Selected Text Color (Light)": ProfileColor,
        "Selection Color": ProfileColor,
        "Selection Color (Dark)": ProfileColor,
        "Selection Color (Light)": ProfileColor,
        "Semantic History": SemanticHistory,
        "Send Bell Alert": BoolInt,
        "Send Code When Idle": BoolInt,
        "Send Idle Alert": BoolInt,
        "Send New Output Alert": BoolInt,
        "Send Session Ended Alert": BoolInt,
        "Send Terminal Generated Alerts": BoolInt,
        "Session Close Undo Timeout": float,
        "Session Hotkey": dict[str, Any],
        "Set Local Environment Vars": BoolInt,
        "Shortcut": str,
        "Show Mark Indicators": BoolInt,
        "Show Offscreen Command line": BoolInt,
        "Show Offscreen Command line for Current Command": BoolInt,
        "Show Status Bar": BoolInt,
        "Silence Bell": BoolInt,
        "Smart Cursor Color": BoolInt,
        "Smart Cursor Color (Dark)": BoolInt,
        "Smart Cursor Color (Light)": BoolInt,
        "Smart Selection Actions Use Interpolated Strings": BoolInt,
        "Smart Selection Rules": list[SmartSelectionRule],
        "Snippets Filter": list[str],
        "Space": int,
        "Status Bar Layout": StatusBarLayout,
        "Subtitle": str,
        "Suppress Alerts in Active Session": BoolInt,
        "Tab Color": ProfileColor,
        "Tab Color (Dark)": ProfileColor,
        "Tab Color (Light)": ProfileColor,
        "Tags": list[str],
        "Terminal Type": str,
        "Thin Strokes": int,
        "Timestamps Style": int,
        "Timestamps Visible": BoolInt,
        "Title Components": int,
        "Title Function": list[TitleFunctionEntry],
        "Tmux Newline": BoolInt,
        "Transparency": float,
        "Treat Option as Alt": BoolInt,
        "Triggers": list[Trigger],
        "Triggers Use Interpolated Strings": BoolInt,
        "Underline Color": ProfileColor,
        "Underline Color (Dark)": ProfileColor,
        "Underline Color (Light)": ProfileColor,
        "Unicode Normalization": int,
        "Unicode Version": int,
        "Unlimited Scrollback": BoolInt,
        "Use Active Pane Border": BoolInt,
        "Use Active Pane Border (Dark)": BoolInt,
        "Use Active Pane Border (Light)": BoolInt,
        "Use Bold Font": BoolInt,
        "Use Bright Bold": BoolInt,
        "Use Bright Bold (Dark)": BoolInt,
        "Use Bright Bold (Light)": BoolInt,
        "Use Cursor Guide": BoolInt,
        "Use Cursor Guide (Dark)": BoolInt,
        "Use Cursor Guide (Light)": BoolInt,
        "Use Custom Tab Title": BoolInt,
        "Use Custom Window Title": BoolInt,
        "Use Italic Font": BoolInt,
        "Use Non-ASCII Font": BoolInt,
        "Use Selected Text Color": BoolInt,
        "Use Selected Text Color (Dark)": BoolInt,
        "Use Selected Text Color (Light)": BoolInt,
        "Use Separate Colors for Light and Dark Mode": BoolInt,
        "Use Tab Color": BoolInt,
        "Use Tab Color (Dark)": BoolInt,
        "Use Tab Color (Light)": BoolInt,
        "Use Underline Color": BoolInt,
        "Use Underline Color (Dark)": BoolInt,
        "Use Underline Color (Light)": BoolInt,
        "Use libtickit protocol": BoolInt,
        "Vertical Spacing": float,
        "Visual Bell": BoolInt,
        "Width Percentage": float,
        "Width in Points": float,
        "Window Type": int,
        "Working Directory": str,
    },
    total=False,
)


type ProfilePropertyKey = Literal[
    "ASCII Anti Aliased",
    "ASCII Ligatures",
    "AWDS Pane Directory",
    "AWDS Pane Option",
    "AWDS Tab Directory",
    "AWDS Tab Option",
    "AWDS Window Directory",
    "AWDS Window Option",
    "Active Pane Border Color",
    "Active Pane Border Color (Dark)",
    "Active Pane Border Color (Light)",
    "Allow Alternate Mouse Scroll",
    "Allow Change Cursor Blink",
    "Allow Paste Bracketing",
    "Allow Title Reporting",
    "Allow Title Setting",
    "Allow modifyOtherKeys",
    "Ambiguous Double Width",
    "Animate Movement",
    "Animate Movement Only in Interactive Apps",
    "Ansi 0 Color",
    "Ansi 0 Color (Dark)",
    "Ansi 0 Color (Light)",
    "Ansi 1 Color",
    "Ansi 1 Color (Dark)",
    "Ansi 1 Color (Light)",
    "Ansi 10 Color",
    "Ansi 10 Color (Dark)",
    "Ansi 10 Color (Light)",
    "Ansi 11 Color",
    "Ansi 11 Color (Dark)",
    "Ansi 11 Color (Light)",
    "Ansi 12 Color",
    "Ansi 12 Color (Dark)",
    "Ansi 12 Color (Light)",
    "Ansi 13 Color",
    "Ansi 13 Color (Dark)",
    "Ansi 13 Color (Light)",
    "Ansi 14 Color",
    "Ansi 14 Color (Dark)",
    "Ansi 14 Color (Light)",
    "Ansi 15 Color",
    "Ansi 15 Color (Dark)",
    "Ansi 15 Color (Light)",
    "Ansi 2 Color",
    "Ansi 2 Color (Dark)",
    "Ansi 2 Color (Light)",
    "Ansi 3 Color",
    "Ansi 3 Color (Dark)",
    "Ansi 3 Color (Light)",
    "Ansi 4 Color",
    "Ansi 4 Color (Dark)",
    "Ansi 4 Color (Light)",
    "Ansi 5 Color",
    "Ansi 5 Color (Dark)",
    "Ansi 5 Color (Light)",
    "Ansi 6 Color",
    "Ansi 6 Color (Dark)",
    "Ansi 6 Color (Light)",
    "Ansi 7 Color",
    "Ansi 7 Color (Dark)",
    "Ansi 7 Color (Light)",
    "Ansi 8 Color",
    "Ansi 8 Color (Dark)",
    "Ansi 8 Color (Light)",
    "Ansi 9 Color",
    "Ansi 9 Color (Dark)",
    "Ansi 9 Color (Light)",
    "Answerback String",
    "Application Keypad Allowed",
    "Archive Directory",
    "Archive On Closure",
    "Automatically Enable Alternate Mouse Scroll",
    "Automatically Log",
    "BM Growl",
    "Background Color",
    "Background Color (Dark)",
    "Background Color (Light)",
    "Background Image Folder Interval",
    "Background Image Mode",
    "Background Image Source Mode",
    "Badge Color",
    "Badge Color (Dark)",
    "Badge Color (Light)",
    "Badge Text",
    "Bindings",
    "Blend",
    "Blink Allowed",
    "Blinking Cursor",
    "Blur",
    "Blur Radius",
    "Bold Color",
    "Bold Color (Dark)",
    "Bold Color (Light)",
    "Bound Hosts",
    "Brighten Bold Text",
    "Brighten Bold Text (Dark)",
    "Brighten Bold Text (Light)",
    "Browser Extension Active IDs",
    "Browser Extensions Root",
    "Browser Zoom",
    "Buffer Input by Default",
    "Character Encoding",
    "Close Sessions On End",
    "Columns",
    "Command",
    "Composer Top Offset",
    "Cursor Boost",
    "Cursor Boost (Dark)",
    "Cursor Boost (Light)",
    "Cursor Color",
    "Cursor Color (Dark)",
    "Cursor Color (Light)",
    "Cursor Guide Color",
    "Cursor Guide Color (Dark)",
    "Cursor Guide Color (Light)",
    "Cursor Hidden When Unfocused",
    "Cursor Shadow",
    "Cursor Smooth Slide",
    "Cursor Text Color",
    "Cursor Text Color (Dark)",
    "Cursor Text Color (Light)",
    "Cursor Type",
    "Custom Command",
    "Custom Directory",
    "Custom Icon Path",
    "Custom Locale",
    "Custom Tab Title",
    "Custom Window Title",
    "Default Pane Locked",
    "Dev Null Mode",
    "Disable Printing",
    "Disable Smcup Rmcup",
    "Disable Window Resizing",
    "Disable Window Resizing by Unfocused Sessions",
    "Drag to Scroll in Alternate Screen Mode Disabled",
    "Draw Powerline Glyphs",
    "Enable Progress Bars",
    "Enable Triggers in Interactive Apps",
    "Faint Text Alpha",
    "Faint Text Alpha (Dark)",
    "Faint Text Alpha (Light)",
    "Flashing Bell",
    "Foreground Color",
    "Foreground Color (Dark)",
    "Foreground Color (Light)",
    "Function Key",
    "Guid",
    "Harmonize 256 Colors",
    "Harmonize 256 Colors (Dark)",
    "Harmonize 256 Colors (Light)",
    "Has Hotkey",
    "Height Percentage",
    "Height in Points",
    "Hide After Opening",
    "Horizontal Spacing",
    "HotKey Activated By Modifier",
    "HotKey Alternate Shortcuts",
    "HotKey Characters",
    "HotKey Characters Ignoring Modifiers",
    "HotKey Key Code",
    "HotKey Modifier Activation",
    "HotKey Modifier Flags",
    "HotKey Window Animates",
    "HotKey Window AutoHides",
    "HotKey Window Dock Click Action",
    "HotKey Window Floats",
    "HotKey Window Reopens On Activation",
    "IME Cursor Color",
    "IME Cursor Color (Dark)",
    "IME Cursor Color (Light)",
    "Icon",
    "Idle Code",
    "Idle Period",
    "Initial Text",
    "Initial URL",
    "Initial Use Transparency",
    "Instant Replay",
    "Jobs to Ignore",
    "Keyboard Map",
    "Left Command Key",
    "Left Control Key",
    "Left Option Key Changeable",
    "Link Color",
    "Link Color (Dark)",
    "Link Color (Light)",
    "Load Shell Integration Automatically",
    "Lock Window Size Automatically",
    "Log Directory",
    "Log Filename Format",
    "Match Background Color",
    "Match Background Color (Dark)",
    "Match Background Color (Light)",
    "Minimum Contrast",
    "Minimum Contrast (Dark)",
    "Minimum Contrast (Light)",
    "Mouse Reporting",
    "Mouse Reporting allow clicks and drags",
    "Mouse Reporting allow mouse wheel",
    "Movement Keys Scroll Outside Interactive Apps",
    "Name",
    "Non Ascii Font",
    "Non-ASCII Anti Aliased",
    "Non-ASCII Ligatures",
    "Normal Font",
    "Only The Default BG Color Uses Transparency",
    "Open Password Manager Automatically",
    "Open Toolbelt",
    "Option Key Sends",
    "Place Prompt at First Column",
    "Plain Text Logging",
    "Prevent Automatic Profile Switching",
    "Prevent Opening in a Tab",
    "Profile Type (Phony)",
    "Progress Bar Color Scheme",
    "Progress Bar Height",
    "Prompt Before Closing 2",
    "Prompt Path Click Opens Navigator",
    "Reduce Flicker",
    "Restrict Alternate Mouse Scroll to Vertical",
    "Restrict Mouse Reporting to Alternate Screen Mode",
    "Right Command Key",
    "Right Control Key",
    "Right Option Key Changeable",
    "Right Option Key Sends",
    "Rows",
    "Run Command In Login Shell",
    "SSH",
    "Screen",
    "Scrollback Lines",
    "Scrollback With Status Bar",
    "Scrollback in Alternate Screen",
    "Selected Text Color",
    "Selected Text Color (Dark)",
    "Selected Text Color (Light)",
    "Selection Color",
    "Selection Color (Dark)",
    "Selection Color (Light)",
    "Semantic History",
    "Send Bell Alert",
    "Send Code When Idle",
    "Send Idle Alert",
    "Send New Output Alert",
    "Send Session Ended Alert",
    "Send Terminal Generated Alerts",
    "Session Close Undo Timeout",
    "Session Hotkey",
    "Set Local Environment Vars",
    "Shortcut",
    "Show Mark Indicators",
    "Show Offscreen Command line",
    "Show Offscreen Command line for Current Command",
    "Show Status Bar",
    "Silence Bell",
    "Smart Cursor Color",
    "Smart Cursor Color (Dark)",
    "Smart Cursor Color (Light)",
    "Smart Selection Actions Use Interpolated Strings",
    "Smart Selection Rules",
    "Snippets Filter",
    "Space",
    "Status Bar Layout",
    "Subtitle",
    "Suppress Alerts in Active Session",
    "Tab Color (Light)",
    "Tags",
    "Terminal Type",
    "Thin Strokes",
    "Timestamps Style",
    "Timestamps Visible",
    "Title Components",
    "Title Function",
    "Tmux Newline",
    "Transparency",
    "Treat Option as Alt",
    "Triggers",
    "Triggers Use Interpolated Strings",
    "Unicode Normalization",
    "Unicode Version",
    "Unlimited Scrollback",
    "Use Active Pane Border",
    "Use Active Pane Border (Dark)",
    "Use Active Pane Border (Light)",
    "Use Bold Font",
    "Use Bright Bold",
    "Use Bright Bold (Dark)",
    "Use Bright Bold (Light)",
    "Use Cursor Guide",
    "Use Cursor Guide (Dark)",
    "Use Cursor Guide (Light)",
    "Use Custom Tab Title",
    "Use Custom Window Title",
    "Use Italic Font",
    "Use Non-ASCII Font",
    "Use Selected Text Color",
    "Use Selected Text Color (Dark)",
    "Use Selected Text Color (Light)",
    "Use Separate Colors for Light and Dark Mode",
    "Use Tab Color",
    "Use Tab Color (Dark)",
    "Use Tab Color (Light)",
    "Use Underline Color",
    "Use Underline Color (Dark)",
    "Use Underline Color (Light)",
    "Use libtickit protocol",
    "Vertical Spacing",
    "Visual Bell",
    "Width Percentage",
    "Width in Points",
    "Window Type",
    "Working Directory",
]


class ProfileProperty(Protocol):
    key: ProfilePropertyKey
    json_value: str


class LocalWriteOnlyProfile(profile.LocalWriteOnlyProfile):
    def __init__(self, values: ProfileProperties | None = None):
        super().__init__(values)


class Profile(profile.Profile):
    def __init__(self, session_id: str, connection: Connection, profile_property_list: list[ProfileProperty]):
        super().__init__(session_id, connection, profile_property_list)

    @property
    def all_properties(self) -> ProfileProperties:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Returns the internal property dictionary, typed by iTerm2 key name."""
        return cast(ProfileProperties, super().all_properties)

    @property
    def guid(self) -> str:
        return cast(str, super().guid)

    @property
    def original_guid(self) -> str:
        return cast(str, super().original_guid)

    @staticmethod
    async def async_get(connection: Connection, guids: list[str] | None = None) -> list[Profile]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return cast(list[Profile], await profile.Profile.async_get(connection, guids))

    @staticmethod
    async def async_get_default(connection: Connection) -> Profile:
        return cast(Profile, await profile.Profile.async_get_default(connection))


class PartialProfile(profile.PartialProfile):
    def __init__(self, session_id: str, connection: Connection, profile_property_list: list[ProfileProperty]):
        super().__init__(session_id, connection, profile_property_list)

    @property
    def all_properties(self) -> ProfileProperties:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Returns the internal property dictionary, typed by iTerm2 key name."""
        return cast(ProfileProperties, super().all_properties)

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
