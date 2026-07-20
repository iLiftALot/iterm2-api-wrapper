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

import asyncio
import getpass
import json
import sys
from collections.abc import Sequence
from dataclasses import InitVar, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypedDict, cast, overload
from uuid import NAMESPACE_URL, uuid5

from iterm2 import BadGUIDException, capabilities, profile, rpc

from ..errors import ProfileNotFoundError, SessionNotFoundError
from .it2app import async_get_app


if sys.version_info >= (3, 12):
    from typing import NotRequired
else:
    from typing_extensions import NotRequired


if TYPE_CHECKING:
    from iterm2.api_pb2 import ServerOriginatedMessage

    from .it2connection import Connection


ColorSpace = Literal["sRGB", "Dev", "P3"]
BoolInt = Literal[0, 1]

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

KeyboardMap = dict[str, KeyboardMapEntry]
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

ProfilePropertiesNoIdentifiers = TypedDict(
    "ProfilePropertiesNoIdentifiers",
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
        # "Guid": str,
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
        # "Name": str,
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


class _OptionalProfileIdentity(TypedDict, total=False):
    Name: str
    Guid: str


class ProfileProperties(ProfilePropertiesNoIdentifiers, _OptionalProfileIdentity):
    """A partial profile property mapping.

    Every property, including Name and Guid, is optional. This type is suitable
    for patches, function arguments, partial RPC results, and session-local
    profile updates.
    """


ProfilePropertyKey = Literal[
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
    "Tab Color",
    "Tab Color (Dark)",
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
    "Underline Color",
    "Underline Color (Dark)",
    "Underline Color (Light)",
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

_DynamicProfileDefinitionExtras = TypedDict(
    "_DynamicProfileDefinitionExtras",
    {
        "Dynamic Profile Parent GUID": str,
        "Dynamic Profile Parent Name": str,
        "Rewritable": bool,
    },
    total=False,
)
_DynamicProfileRuntimeExtras = TypedDict(
    "_DynamicProfileRuntimeExtras",
    {
        "Dynamic Profile Filename": str,
        "Is Dynamic Profile": BoolInt,
    },
    total=False,
)

DynamicProfilePropertyKey = Literal[
    "Guid",
    "Name",
    "Rewritable",
    "Dynamic Profile Parent GUID",
    "Dynamic Profile Parent Name",
    "Dynamic Profile Filename",
    "Is Dynamic Profile",
]


class DynamicProfileProperties(ProfileProperties, _DynamicProfileDefinitionExtras):
    """A partial dynamic-profile property mapping.

    Every key is optional. This type is suitable for function parameters,
    patches, and incomplete dynamic-profile data.
    """


class DynamicProfileRuntimeProperties(DynamicProfileProperties, _DynamicProfileRuntimeExtras):
    """Dynamic-profile properties returned by iTerm2 at runtime.

    This includes runtime-only metadata that must not be persisted in a
    DynamicProfiles JSON file.
    """


class DynamicProfileDefinition(ProfilePropertiesNoIdentifiers, _DynamicProfileDefinitionExtras):
    """A complete JSON-writable dynamic-profile definition.

    Name and Guid are the only universally required dynamic-profile fields.
    Every inherited profile property remains optional.
    """

    Name: str
    Guid: str


class DynamicProfilesPayload(TypedDict):
    """The complete wrapper-managed DynamicProfiles JSON document."""

    Profiles: list[DynamicProfileDefinition]


DEFAULT_PARTIAL_PROFILE_PROPERTIES = ("Guid", "Name")


class ProfilePropertyLike(Protocol):
    key: ProfilePropertyKey | str
    json_value: str


@dataclass
class ProfileProperty:
    key: ProfilePropertyKey | str
    json_value: str

    json_auto_convert: InitVar[bool] = True

    def __post_init__(self, json_auto_convert: bool) -> None:
        if json_auto_convert is True:
            self.json_value = json.dumps(self.json_value)


class LocalWriteOnlyProfile(profile.LocalWriteOnlyProfile):
    def __init__(self, values: ProfileProperties | None = None):
        super().__init__(values)


class Profile(profile.Profile):
    _Profile__props: ProfileProperties
    connection: Connection
    session_id: str | None

    def __init__(
        self,
        session_id: str | None,
        connection: Connection,
        profile_properties: ProfileProperties | Sequence[ProfilePropertyLike],
    ) -> None:
        profile_property_list: list[ProfilePropertyLike]

        if isinstance(profile_properties, Sequence):
            profile_property_list = list(profile_properties)
        else:
            profile_property_list = [
                ProfileProperty(key=k, json_value=json.dumps(v), json_auto_convert=False)
                for k, v in profile_properties.items()
            ]

        super().__init__(session_id, connection, profile_property_list)
        self.__props = self._Profile__props

    @property
    def all_properties(self) -> ProfileProperties:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Returns the internal property dictionary, typed by iTerm2 key name."""
        return cast(ProfileProperties, dict(self.__props))

    @property
    def guid(self) -> str:
        value = self._simple_get("Guid")
        if not isinstance(value, str):
            raise BadGUIDException()
        return value

    @property
    def original_guid(self) -> str:
        return self._simple_get("Original Guid") or self.guid

    @staticmethod
    async def all_guids(connection: Connection) -> set[str]:
        profiles = await PartialProfile.async_query(connection, properties=["Guid"])
        return {p.guid for p in profiles}

    @staticmethod
    async def all_names(connection: Connection) -> set[str]:
        profiles = await PartialProfile.async_query(connection, properties=["Name"])
        return {p.name for p in profiles}

    @staticmethod
    async def to_dict(connection: Connection) -> dict[str, Profile]:
        """Returns a dictionary containing profile names as keys with their corresponding :class:`Profile` object."""
        profiles = await Profile.async_get(connection)
        return {p.name: p for p in profiles}

    async def async_local_update(self, properties: ProfileProperties) -> Profile:
        """Apply temporary property overrides to this profile's live session.

        This changes only the session-local copy of the profile. It does not
        modify the underlying shared or dynamic profile definition.

        :raises ValueError: If this is a shared profile rather than a
            session-backed profile.
        :raises SessionNotFoundError: If the original session no longer exists.
        :returns: The session's freshly queried profile after applying the
            overrides.
        """
        session_id = self.session_id
        if session_id is None:
            raise ValueError(
                "async_local_update() requires a session-backed Profile. "
                "Obtain the profile from Session.async_get_profile() before "
                "applying a session-local update."
            )

        app = await async_get_app(self.connection, create_if_needed=True)
        session = app.get_session_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        local_profile = LocalWriteOnlyProfile(properties)
        await session.async_set_profile_properties(local_profile)
        return await session.async_get_profile()

    @staticmethod
    async def async_update(
        connection: Connection,
        profile_name: str,
        *,
        properties: ProfilePropertiesNoIdentifiers | None = None,
        remove_properties: Sequence[ProfilePropertyKey] = (),
    ) -> Profile:
        """Patch an existing wrapper-managed dynamic profile.

        Properties not supplied remain unchanged. Properties named in
        ``remove_properties`` are removed from the explicit dynamic-profile
        definition and therefore inherit from the profile's parent.

        :param connection: The active iTerm2 connection.
        :param profile_name: The original wrapper-managed profile name used to
            derive its deterministic GUID.
        :param properties: Properties to add or replace.
        :param remove_properties: Explicit properties to remove.
        :returns: The freshly queried profile after iTerm2 observes the update.
        """
        dynamic_profile = DynamicProfile(connection, profile_name)
        return await dynamic_profile.async_update(
            properties=properties,
            remove_properties=remove_properties,
        )

    @staticmethod
    async def async_create(
        connection: Connection,
        profile_name: str,
        *,
        parent_profile_name: str | None = None,
        parent_profile_guid: str | None = None,
        properties: ProfilePropertiesNoIdentifiers | None = None,
    ) -> Profile:
        """Creates a new [***dynamic***](https://iterm2.com/documentation-dynamic-profiles.html) iTerm2 profile."""
        if parent_profile_guid is not None:
            dynamic_profile = DynamicProfile(
                connection,
                profile_name,
                parent_profile_guid=parent_profile_guid,
                properties=properties,
            )
        elif parent_profile_name is not None:
            dynamic_profile = DynamicProfile(
                connection,
                profile_name,
                parent_profile_name=parent_profile_name,
                properties=properties,
            )
        else:
            dynamic_profile = DynamicProfile(
                connection,
                profile_name,
                properties=properties,
            )

        return await dynamic_profile.async_create()

    @staticmethod
    async def async_get(connection: Connection, guids: list[str] | None = None) -> list[Profile]:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Fetches all profiles with the specified GUIDs.

        :param guids: The profiles to get, or if `None` then all will be
            returned.

        :returns: A list of :class:`Profile` objects.
        """
        response: ServerOriginatedMessage = await rpc.async_list_profiles(connection, guids, None)
        profiles: list[Profile] = [
            Profile(None, connection, cast(list[ProfilePropertyLike], response_profile.properties))
            for response_profile in response.list_profiles_response.profiles
        ]
        return profiles

    @staticmethod
    async def async_get_default(connection: Connection) -> Profile:
        """Returns the default profile."""
        capabilities.check_supports_get_default_profile(connection)
        result: ServerOriginatedMessage = await rpc.async_get_default_profile(connection)
        guid: str = result.preferences_response.results[0].get_default_profile_result.guid
        profiles = await Profile.async_get(connection, [guid])
        return profiles[0]


class PartialProfile(Profile):
    """
    Represents a profile that has only a subset of fields available for
    reading.
    """

    @staticmethod
    async def async_query(
        connection: Connection,
        guids: list[str] | None = None,
        properties: Sequence[str] | None = DEFAULT_PARTIAL_PROFILE_PROPERTIES,
    ) -> list[PartialProfile]:
        response: ServerOriginatedMessage = await rpc.async_list_profiles(connection, guids, properties)
        return [
            PartialProfile(None, connection, response_profile.properties)
            for response_profile in response.list_profiles_response.profiles
        ]

    async def async_get_full_profile(self) -> Profile:
        if not self.guid:
            raise BadGUIDException()

        response: ServerOriginatedMessage = await rpc.async_list_profiles(self.connection, [self.guid], None)

        if len(response.list_profiles_response.profiles) != 1:
            raise BadGUIDException()

        return Profile(None, self.connection, response.list_profiles_response.profiles[0].properties)

    @staticmethod
    async def async_get_default(
        connection: Connection, properties: Sequence[str] | None = DEFAULT_PARTIAL_PROFILE_PROPERTIES
    ) -> PartialProfile:
        capabilities.check_supports_get_default_profile(connection)
        result: ServerOriginatedMessage = await rpc.async_get_default_profile(connection)
        guid: str = result.preferences_response.results[0].get_default_profile_result.guid
        profiles = await PartialProfile.async_query(connection, [guid], properties)
        return profiles[0]

    async def async_make_default(self) -> None:
        await rpc.async_set_default_profile(self.connection, self.guid)


def process_dynamic_profiles_payload(
    dynamic_profile_path: Path,
    staging_path: Path,
    *,
    payload: DynamicProfilesPayload | None = None,
) -> DynamicProfilesPayload:
    """Read or atomically publish a wrapper-managed dynamic-profile payload.

    When ``payload`` is omitted, read and validate the existing JSON document
    without modifying either file.

    When ``payload`` is supplied, validate it, write the completed JSON to
    ``staging_path``, and atomically replace ``dynamic_profile_path``.

    The validator intentionally enforces the payload envelope and the
    universally required dynamic-profile identity fields. The hundreds of
    optional profile-property value shapes remain governed by the typed input
    contracts.
    """
    path = dynamic_profile_path

    def _validate_dynamic_profiles_payload(
        raw_payload: object,
    ) -> DynamicProfilesPayload:
        if not isinstance(raw_payload, dict):
            raise ValueError(f"Cannot process dynamic profiles because '{path}' must contain a top-level JSON object.")

        raw_profiles = raw_payload.get("Profiles")
        if not isinstance(raw_profiles, list):
            raise ValueError(f"Cannot process dynamic profiles because '{path}' must contain a 'Profiles' array.")

        for index, definition in enumerate(raw_profiles):
            if not isinstance(definition, dict):
                raise ValueError(f"Dynamic profile entry {index} in '{path}' must be a JSON object.")

            if not isinstance(definition.get("Name"), str):
                raise ValueError(f"Dynamic profile entry {index} in '{path}' must contain a string 'Name'.")

            if not isinstance(definition.get("Guid"), str):
                raise ValueError(f"Dynamic profile entry {index} in '{path}' must contain a string 'Guid'.")

        return cast(DynamicProfilesPayload, raw_payload)

    def _extract_dynamic_profiles_payload() -> DynamicProfilesPayload:
        if not path.exists():
            raise ValueError(f"Cannot read a wrapper-managed dynamic-profile payload because '{path}' does not exist.")

        try:
            raw_payload: object = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Cannot process dynamic profiles because '{path}' does not contain valid JSON: {exc}"
            ) from exc

        return _validate_dynamic_profiles_payload(raw_payload)

    def _write_dynamic_profiles_payload(
        validated_payload: DynamicProfilesPayload,
    ) -> DynamicProfilesPayload:
        """Atomically publish a complete wrapper-managed payload."""
        path.parent.mkdir(parents=True, exist_ok=True)
        staging_path.parent.mkdir(parents=True, exist_ok=True)

        staging_path.write_text(
            json.dumps(validated_payload, indent=4) + "\n",
            encoding="utf-8",
        )
        staging_path.replace(path)
        return validated_payload

    if payload is None:
        return _extract_dynamic_profiles_payload()

    validated_payload = _validate_dynamic_profiles_payload(payload)
    return _write_dynamic_profiles_payload(validated_payload)


class DynamicProfile:
    """Creates an iTerm2 dynamic profile."""

    UUID_NAME = "com.{USER}.{NAME}/profile"
    ITERM2_DIRECTORY = Path.home() / "Library" / "Application Support" / "iTerm2"
    DYNAMIC_PROFILES_DIRECTORY = ITERM2_DIRECTORY / "DynamicProfiles"
    DYNAMIC_PROFILE_PATH = DYNAMIC_PROFILES_DIRECTORY / "iterm2-api-wrapper.json"
    # Stage the completed JSON outside the watched DynamicProfiles directory,
    # then atomically move it into place.
    STAGING_PATH = ITERM2_DIRECTORY / ".iterm2-api-wrapper.json.tmp"

    PROFILE_LOAD_TIMEOUT = 5.0
    PROFILE_LOAD_INITIAL_DELAY = 0.05
    PROFILE_LOAD_MAX_DELAY = 0.5

    _PROTECTED_UPDATE_PROPERTIES: frozenset[DynamicProfilePropertyKey] = frozenset(
        {
            "Guid",
            "Name",
            "Rewritable",
            "Dynamic Profile Parent GUID",
            "Dynamic Profile Parent Name",
            "Dynamic Profile Filename",
            "Is Dynamic Profile",
        }
    )

    @overload
    def __init__(
        self,
        connection: Connection,
        profile_name: str,
        *,
        parent_profile_guid: str,
        parent_profile_name: None = ...,
        properties: ProfilePropertiesNoIdentifiers | None = None,
    ) -> None: ...
    @overload
    def __init__(
        self,
        connection: Connection,
        profile_name: str,
        *,
        parent_profile_name: str,
        parent_profile_guid: None = ...,
        properties: ProfilePropertiesNoIdentifiers | None = None,
    ) -> None: ...
    @overload
    def __init__(
        self,
        connection: Connection,
        profile_name: str,
        *,
        parent_profile_name: None = ...,
        parent_profile_guid: None = ...,
        properties: ProfilePropertiesNoIdentifiers | None = None,
    ) -> None: ...
    def __init__(
        self,
        connection: Connection,
        profile_name: str,
        *,
        parent_profile_guid: str | None = None,
        parent_profile_name: str | None = None,
        properties: ProfilePropertiesNoIdentifiers | None = None,
    ) -> None:
        if parent_profile_guid is not None and parent_profile_name is not None:
            raise ValueError("Specify either parent_profile_guid or parent_profile_name, not both.")

        self.__connection = connection
        self.__profile_name = profile_name
        self.__parent_guid = parent_profile_guid
        self.__parent_name = parent_profile_name or "Default"
        self.__requested_properties: ProfilePropertiesNoIdentifiers = {**(properties or {})}
        self.__props: DynamicProfileDefinition = {
            **self.__requested_properties,
            "Name": profile_name,
            "Guid": self.guid,
            "Rewritable": True,
        }

        if self.__parent_guid is not None:
            self.__props["Dynamic Profile Parent GUID"] = self.__parent_guid
        else:
            self.__props["Dynamic Profile Parent Name"] = self.__parent_name

    @property
    def guid(self) -> str:
        """Utilizes UUID5 to provide repeatable GUIDs."""
        user = getpass.getuser()
        name_link_fmt = self.__profile_name.replace(" ", "_").lower()
        uuid_name = self.UUID_NAME.format(USER=user, NAME=name_link_fmt)
        return str(uuid5(NAMESPACE_URL, uuid_name)).upper()

    @property
    def payload(self) -> DynamicProfilesPayload:
        """Manufactures the payload from the current class context."""
        dynamic_profiles: list[DynamicProfileDefinition] = [self.__props]

        if self.DYNAMIC_PROFILE_PATH.exists():
            previous_dynamic_profiles = process_dynamic_profiles_payload(
                self.DYNAMIC_PROFILE_PATH,
                self.STAGING_PATH,
            )
            dynamic_profiles.extend(
                [
                    dynamic_profile
                    for dynamic_profile in previous_dynamic_profiles.get("Profiles", [])
                    if dynamic_profile.get("Guid") != self.guid
                ]
            )

        return {"Profiles": dynamic_profiles}

    async def parent(self) -> Profile:
        """Return the profile that this dynamic profile inherits from."""
        err_msg = (
            f"The specified parent of '{self.__profile_name}' ({self.guid}), '{{target_profile_name}}', "
            "was not found... Known profiles:\n{{profile_data}}"
        )
        profiles = await Profile.async_get(
            self.__connection, [self.__parent_guid] if self.__parent_guid is not None else None
        )

        if self.__parent_guid is not None:
            if profiles:
                return profiles[0]

            raise ProfileNotFoundError(
                msg=err_msg,
                target_profile_name=self.__parent_guid,
                profile_data=(await Profile.to_dict(self.__connection)),
            )

        profile_data = {profile.name: profile for profile in profiles}
        parent_profile = profile_data.get(self.__parent_name)

        if parent_profile is None:
            raise ProfileNotFoundError(
                msg=err_msg,
                target_profile_name=self.__parent_name,
                profile_data=profile_data,
            )

        return parent_profile

    @staticmethod
    async def _parent_for_definition(
        connection: Connection,
        definition: DynamicProfileDefinition,
    ) -> Profile:
        """Resolve the effective parent recorded in a persisted definition.

        Parent resolution must use the definition currently stored on disk rather
        than the constructor arguments on ``self``. ``Profile.async_update()``
        reconstructs ``DynamicProfile`` from the deterministic profile name alone,
        while the persisted definition may inherit from a non-default parent.

        If neither parent selector is present, iTerm2 uses the default profile.
        """
        parent_guid = definition.get("Dynamic Profile Parent GUID")
        parent_name = definition.get("Dynamic Profile Parent Name")

        if parent_guid is not None and not isinstance(parent_guid, str):
            raise ValueError(f"Dynamic profile parent GUID must be a string, not {type(parent_guid).__name__}.")

        if parent_name is not None and not isinstance(parent_name, str):
            raise ValueError(f"Dynamic profile parent name must be a string, not {type(parent_name).__name__}.")

        # iTerm2 gives the GUID selector priority. If it does not resolve and a
        # name selector is also present, it attempts the name selector next.
        if parent_guid:
            profiles = await Profile.async_get(
                connection,
                [parent_guid],
            )
            if profiles:
                return profiles[0]

        if parent_name:
            profile_data = await Profile.to_dict(connection)
            parent_profile = profile_data.get(parent_name)
            if parent_profile is not None:
                return parent_profile

        if parent_guid is None and parent_name is None:
            return await Profile.async_get_default(connection)

        profile_data = await Profile.to_dict(connection)
        raise ProfileNotFoundError(
            target_profile_name=parent_guid or parent_name or "<default>",
            profile_data=profile_data,
        )

    async def async_update(
        self,
        *,
        properties: ProfilePropertiesNoIdentifiers | None = None,
        remove_properties: Sequence[ProfilePropertyKey] = (),
    ) -> Profile:
        """Patch an existing wrapper-managed dynamic profile.

        Properties not mentioned by either argument remain unchanged. Keys in
        ``remove_properties`` are removed from the explicit dynamic-profile
        definition and therefore inherit their values from the profile's parent.

        The profile's Name, Guid, parent selection, Rewritable setting, and
        runtime-only dynamic-profile metadata cannot be changed by this operation.

        :param properties: Ordinary profile properties to add or replace. Dynamic
            profile identity and metadata are intentionally excluded by the type.
        :param remove_properties: Explicit ordinary profile properties to remove.
        :returns: The freshly queried profile after iTerm2 observes the update.
        :raises ProfileNotFoundError: If the deterministic profile GUID is not
            currently registered in iTerm2.
        :raises ValueError: If the profile is not a dynamic profile owned by this
            wrapper, the wrapper JSON does not contain it, protected fields are
            supplied, or a property is both set and removed.
        :raises TimeoutError: If iTerm2 does not expose the requested state before
            the profile-load timeout expires.
        """
        expected_properties: ProfilePropertiesNoIdentifiers = {**(properties or {})}
        expected_keys: set[str] = set(expected_properties)

        removed_properties_set: set[ProfilePropertyKey] = set(remove_properties)
        removed_keys: set[str] = set(removed_properties_set)

        overlapping_keys = sorted(expected_keys & removed_keys)
        if overlapping_keys:
            raise ValueError(
                "Properties cannot be both set and removed in the same update: " + ", ".join(overlapping_keys)
            )

        protected_keys = sorted(self._PROTECTED_UPDATE_PROPERTIES & (expected_keys | removed_keys))
        if protected_keys:
            raise ValueError(
                "Dynamic-profile identity and metadata properties cannot be "
                "updated or removed: " + ", ".join(protected_keys)
            )

        current_guid = self.guid
        current_profiles = await Profile.async_get(
            self.__connection,
            [current_guid],
        )
        if not current_profiles:
            raise ProfileNotFoundError(
                target_profile_name=self.__profile_name,
                profile_data=await Profile.to_dict(self.__connection),
            )

        current_profile = current_profiles[0]
        runtime_properties = cast(
            DynamicProfileRuntimeProperties,
            current_profile.all_properties,
        )
        runtime_source = runtime_properties.get("Dynamic Profile Filename")

        if not isinstance(runtime_source, str):
            raise ValueError(
                f"Profile '{self.__profile_name}' ({current_guid}) is registered in iTerm2 but is not a dynamic profile."
            )

        runtime_source_path = Path(runtime_source).expanduser().resolve()
        managed_source_path = self.DYNAMIC_PROFILE_PATH.expanduser().resolve()
        if runtime_source_path != managed_source_path:
            raise ValueError(
                f"Dynamic profile '{self.__profile_name}' ({current_guid}) is "
                f"managed by '{runtime_source_path}', not by this wrapper's "
                f"'{managed_source_path}'."
            )

        payload = process_dynamic_profiles_payload(
            self.DYNAMIC_PROFILE_PATH,
            self.STAGING_PATH,
        )
        dynamic_profiles = payload["Profiles"]

        target_index = next(
            (
                index
                for index, dynamic_profile in enumerate(dynamic_profiles)
                if dynamic_profile["Guid"] == current_guid
            ),
            None,
        )
        if target_index is None:
            raise ValueError(
                f"Dynamic profile '{self.__profile_name}' ({current_guid}) is "
                f"not present in this wrapper's "
                f"'{self.DYNAMIC_PROFILE_PATH}'."
            )

        current_definition = dynamic_profiles[target_index]

        # Removing a property from a dynamic-profile definition does not normally
        # remove it from Profile.all_properties. iTerm2 merges the parent profile into
        # the dynamic profile before exposing it through ListProfiles. Capture the
        # parent's effective values so convergence polling can verify inheritance.
        inherited_properties: ProfileProperties = {}
        if removed_properties_set:
            parent_profile = await self._parent_for_definition(
                self.__connection,
                current_definition,
            )
            inherited_properties = parent_profile.all_properties

        updated_values: dict[str, Any] = dict(current_definition)

        for key in removed_properties_set:
            updated_values.pop(key, None)

        updated_values.update(expected_properties)

        # DynamicProfileDefinition requires these two keys. The source definition
        # passed boundary validation, and the protected-field checks above prevent
        # callers from removing or replacing them. Reassigning them here makes that
        # invariant explicit at the cast boundary.
        updated_values["Name"] = current_definition["Name"]
        updated_values["Guid"] = current_definition["Guid"]

        updated_definition = cast(
            DynamicProfileDefinition,
            updated_values,
        )

        if updated_definition != current_definition:
            # Replace the entry in place. Order matters when one dynamic profile
            # inherits from another profile in the same DynamicProfiles file.
            dynamic_profiles[target_index] = updated_definition

            process_dynamic_profiles_payload(
                self.DYNAMIC_PROFILE_PATH,
                self.STAGING_PATH,
                payload=payload,
            )

        return await self._wait_for_profile_update(
            self.__connection,
            current_guid,
            self.__profile_name,
            expected_properties=expected_properties,
            removed_properties=removed_properties_set,
            inherited_properties=inherited_properties,
        )

    async def async_create(self) -> Profile:
        """Create or update this wrapper-managed dynamic profile.

        If iTerm2 already exposes the deterministic GUID as a dynamic profile,
        delegate to ``async_update`` so wrapper ownership is validated before the
        existing definition is changed.

        A deterministic-GUID collision with a non-dynamic profile is rejected
        instead of being incorrectly reported as successful.
        """
        current_guid = self.guid
        profiles = await Profile.async_get(
            self.__connection,
            [current_guid],
        )

        if profiles:
            runtime_properties = cast(
                DynamicProfileRuntimeProperties,
                profiles[0].all_properties,
            )

            if bool(runtime_properties.get("Is Dynamic Profile", 0)):
                return await self.async_update(
                    properties=self.__requested_properties,
                )

            raise ValueError(
                f"Cannot create dynamic profile '{self.__profile_name}' "
                f"because its deterministic GUID ({current_guid}) is already "
                "registered to a non-dynamic profile."
            )

        payload = self.payload
        process_dynamic_profiles_payload(
            self.DYNAMIC_PROFILE_PATH,
            self.STAGING_PATH,
            payload=payload,
        )

        return await self._wait_for_profile(
            self.__connection,
            current_guid,
            self.__profile_name,
        )

    @staticmethod
    async def _wait_for_profile(connection: Connection, guid: str, profile_name: str) -> Profile:
        """Wait until iTerm2 registers a newly written dynamic profile."""
        cls = DynamicProfile
        loop = asyncio.get_running_loop()
        deadline = loop.time() + cls.PROFILE_LOAD_TIMEOUT
        delay = cls.PROFILE_LOAD_INITIAL_DELAY

        while True:
            profiles = await Profile.async_get(connection, [guid])
            if profiles:
                return profiles[0]

            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(
                    f"iTerm2 did not register dynamic profile "
                    f"'{profile_name}' (GUID {guid}) within "
                    f"{cls.PROFILE_LOAD_TIMEOUT:.1f} seconds."
                )

            await asyncio.sleep(min(delay, remaining))
            delay = min(delay * 2, cls.PROFILE_LOAD_MAX_DELAY)

    @staticmethod
    async def _wait_for_profile_update(
        connection: Connection,
        guid: str,
        profile_name: str,
        *,
        expected_properties: ProfilePropertiesNoIdentifiers,
        removed_properties: set[ProfilePropertyKey],
        inherited_properties: ProfileProperties,
    ) -> Profile:
        """Wait until iTerm2 exposes the requested dynamic-profile changes.

        Explicitly set properties must equal their requested values.

        Properties removed from the persisted definition must equal their
        effective parent values. If the parent does not expose a removed property,
        the updated dynamic profile must also omit it.
        """
        cls = DynamicProfile
        loop = asyncio.get_running_loop()
        deadline = loop.time() + cls.PROFILE_LOAD_TIMEOUT
        delay = cls.PROFILE_LOAD_INITIAL_DELAY

        expected_values: dict[str, Any] = dict(expected_properties)
        inherited_values: dict[str, Any] = dict(inherited_properties)
        missing = object()

        while True:
            profiles = await Profile.async_get(
                connection,
                [guid],
            )
            if profiles:
                current_profile = profiles[0]
                current_values: dict[str, Any] = dict(current_profile.all_properties)

                expected_values_match = all(
                    current_values.get(key, missing) == value for key, value in expected_values.items()
                )

                removed_values_inherited = all(
                    current_values.get(key, missing) == inherited_values.get(key, missing) for key in removed_properties
                )

                if expected_values_match and removed_values_inherited:
                    return current_profile

            remaining = deadline - loop.time()
            if remaining <= 0:
                expected_summary = (
                    ", ".join(f"{key}={value!r}" for key, value in sorted(expected_values.items())) or "<none>"
                )
                inherited_summary = (
                    ", ".join(
                        (f"{key}={inherited_values[key]!r}" if key in inherited_values else f"{key}=<absent>")
                        for key in sorted(removed_properties)
                    )
                    or "<none>"
                )

                raise TimeoutError(
                    f"iTerm2 did not apply updates to dynamic profile "
                    f"'{profile_name}' (GUID {guid}) within "
                    f"{cls.PROFILE_LOAD_TIMEOUT:.1f} seconds. "
                    f"Expected explicit properties: {expected_summary}. "
                    f"Expected inherited properties: {inherited_summary}."
                )

            await asyncio.sleep(min(delay, remaining))
            delay = min(delay * 2, cls.PROFILE_LOAD_MAX_DELAY)
