"""Runtime re-exports of the untyped PyObjC symbols used by this project.

Type information lives in the sibling ``typings.pyi`` stub, which type
checkers prefer over this module. At runtime these names are the real ObjC
classes, functions, and constants from PyObjC's framework modules.

Keep this file boring on purpose: do not subclass ObjC classes here. A Python
subclass would register a brand-new Objective-C class at runtime instead of
adding type information to the real bridged class.
"""

from typing import Any, cast

import AppKit as _AppKit
import ApplicationServices as _ApplicationServices
import Foundation as _Foundation
import PyObjCTools.AppHelper as _AppHelper


# PyObjC framework modules expose most Objective-C classes/constants lazily via
# module-level ``__getattr__``. Pylance cannot statically see those dynamic
# attributes in this runtime shim, while the sibling ``.pyi`` supplies the real
# consumer-facing types. Cast only the framework modules to ``Any`` so this file
# remains a faithful runtime re-export instead of a wall of false positives.
AppKit = cast(Any, _AppKit)
ApplicationServices = cast(Any, _ApplicationServices)
Foundation = cast(Any, _Foundation)
AppHelper = cast(Any, _AppHelper)

# --- Foundation ---
NSDate = Foundation.NSDate
NSDefaultRunLoopMode = Foundation.NSDefaultRunLoopMode
NSURL = Foundation.NSURL
NSAppleEventDescriptor = Foundation.NSAppleEventDescriptor
NSAppleScript = Foundation.NSAppleScript
NSRunLoop = Foundation.NSRunLoop
NSRunLoopCommonModes = Foundation.NSRunLoopCommonModes
NSPort = Foundation.NSPort
NSTimer = Foundation.NSTimer

# --- PyObjCTools.AppHelper ---
callAfter = AppHelper.callAfter
callLater = AppHelper.callLater
endSheetMethod = AppHelper.endSheetMethod
runConsoleEventLoop = AppHelper.runConsoleEventLoop
runEventLoop = AppHelper.runEventLoop
stopEventLoop = AppHelper.stopEventLoop

# --- AppKit: app launching / app state / files and URLs ---
NSWorkspace = AppKit.NSWorkspace
NSWorkspaceOpenConfiguration = AppKit.NSWorkspaceOpenConfiguration
NSRunningApplication = AppKit.NSRunningApplication

NSApplicationActivateAllWindows = AppKit.NSApplicationActivateAllWindows
NSApplicationActivateIgnoringOtherApps = AppKit.NSApplicationActivateIgnoringOtherApps

NSWorkspaceLaunchDefault = AppKit.NSWorkspaceLaunchDefault
NSWorkspaceLaunchAndPrint = AppKit.NSWorkspaceLaunchAndPrint
NSWorkspaceLaunchWithErrorPresentation = AppKit.NSWorkspaceLaunchWithErrorPresentation
NSWorkspaceLaunchInhibitingBackgroundOnly = AppKit.NSWorkspaceLaunchInhibitingBackgroundOnly
NSWorkspaceLaunchWithoutAddingToRecents = AppKit.NSWorkspaceLaunchWithoutAddingToRecents
NSWorkspaceLaunchWithoutActivation = AppKit.NSWorkspaceLaunchWithoutActivation
NSWorkspaceLaunchAsync = AppKit.NSWorkspaceLaunchAsync
NSWorkspaceLaunchAllowingClassicStartup = AppKit.NSWorkspaceLaunchAllowingClassicStartup
NSWorkspaceLaunchPreferringClassic = AppKit.NSWorkspaceLaunchPreferringClassic
NSWorkspaceLaunchNewInstance = AppKit.NSWorkspaceLaunchNewInstance
NSWorkspaceLaunchAndHide = AppKit.NSWorkspaceLaunchAndHide
NSWorkspaceLaunchAndHideOthers = AppKit.NSWorkspaceLaunchAndHideOthers

# --- ApplicationServices: Accessibility / AX UI automation ---
AXIsProcessTrusted = ApplicationServices.AXIsProcessTrusted
AXIsProcessTrustedWithOptions = ApplicationServices.AXIsProcessTrustedWithOptions
AXUIElementCreateApplication = ApplicationServices.AXUIElementCreateApplication
AXUIElementCreateSystemWide = ApplicationServices.AXUIElementCreateSystemWide
AXUIElementGetPid = ApplicationServices.AXUIElementGetPid
AXUIElementCopyActionNames = ApplicationServices.AXUIElementCopyActionNames
AXUIElementCopyActionDescription = ApplicationServices.AXUIElementCopyActionDescription
AXUIElementCopyAttributeNames = ApplicationServices.AXUIElementCopyAttributeNames
AXUIElementCopyAttributeValue = ApplicationServices.AXUIElementCopyAttributeValue
AXUIElementCopyParameterizedAttributeNames = ApplicationServices.AXUIElementCopyParameterizedAttributeNames
AXUIElementCopyParameterizedAttributeValue = ApplicationServices.AXUIElementCopyParameterizedAttributeValue
AXUIElementIsAttributeSettable = ApplicationServices.AXUIElementIsAttributeSettable
AXUIElementSetAttributeValue = ApplicationServices.AXUIElementSetAttributeValue
AXUIElementPerformAction = ApplicationServices.AXUIElementPerformAction

kAXTrustedCheckOptionPrompt = ApplicationServices.kAXTrustedCheckOptionPrompt

kAXErrorSuccess = ApplicationServices.kAXErrorSuccess
kAXErrorFailure = ApplicationServices.kAXErrorFailure
kAXErrorIllegalArgument = ApplicationServices.kAXErrorIllegalArgument
kAXErrorInvalidUIElement = ApplicationServices.kAXErrorInvalidUIElement
kAXErrorInvalidUIElementObserver = ApplicationServices.kAXErrorInvalidUIElementObserver
kAXErrorCannotComplete = ApplicationServices.kAXErrorCannotComplete
kAXErrorAttributeUnsupported = ApplicationServices.kAXErrorAttributeUnsupported
kAXErrorActionUnsupported = ApplicationServices.kAXErrorActionUnsupported
kAXErrorNotificationUnsupported = ApplicationServices.kAXErrorNotificationUnsupported
kAXErrorNotImplemented = ApplicationServices.kAXErrorNotImplemented
kAXErrorNotificationAlreadyRegistered = ApplicationServices.kAXErrorNotificationAlreadyRegistered
kAXErrorNotificationNotRegistered = ApplicationServices.kAXErrorNotificationNotRegistered
kAXErrorAPIDisabled = ApplicationServices.kAXErrorAPIDisabled
kAXErrorNoValue = ApplicationServices.kAXErrorNoValue
kAXErrorParameterizedAttributeUnsupported = ApplicationServices.kAXErrorParameterizedAttributeUnsupported

kAXChildrenAttribute = ApplicationServices.kAXChildrenAttribute
kAXCloseButtonAttribute = ApplicationServices.kAXCloseButtonAttribute
kAXColumnsAttribute = ApplicationServices.kAXColumnsAttribute
kAXContentsAttribute = ApplicationServices.kAXContentsAttribute
kAXDescriptionAttribute = ApplicationServices.kAXDescriptionAttribute
kAXEnabledAttribute = ApplicationServices.kAXEnabledAttribute
kAXFocusedApplicationAttribute = ApplicationServices.kAXFocusedApplicationAttribute
kAXFocusedUIElementAttribute = ApplicationServices.kAXFocusedUIElementAttribute
kAXFocusedWindowAttribute = ApplicationServices.kAXFocusedWindowAttribute
kAXFullScreenButtonAttribute = ApplicationServices.kAXFullScreenButtonAttribute
kAXIdentifierAttribute = ApplicationServices.kAXIdentifierAttribute
kAXMainWindowAttribute = ApplicationServices.kAXMainWindowAttribute
kAXMenuBarAttribute = ApplicationServices.kAXMenuBarAttribute
kAXMinimizeButtonAttribute = ApplicationServices.kAXMinimizeButtonAttribute
kAXParentAttribute = ApplicationServices.kAXParentAttribute
kAXPositionAttribute = ApplicationServices.kAXPositionAttribute
kAXRoleAttribute = ApplicationServices.kAXRoleAttribute
kAXRoleDescriptionAttribute = ApplicationServices.kAXRoleDescriptionAttribute
kAXRowsAttribute = ApplicationServices.kAXRowsAttribute
kAXSelectedAttribute = ApplicationServices.kAXSelectedAttribute
kAXSelectedChildrenAttribute = ApplicationServices.kAXSelectedChildrenAttribute
kAXSizeAttribute = ApplicationServices.kAXSizeAttribute
kAXSubroleAttribute = ApplicationServices.kAXSubroleAttribute
kAXTabsAttribute = ApplicationServices.kAXTabsAttribute
kAXTitleAttribute = ApplicationServices.kAXTitleAttribute
kAXValueAttribute = ApplicationServices.kAXValueAttribute
kAXVisibleChildrenAttribute = ApplicationServices.kAXVisibleChildrenAttribute
kAXWindowAttribute = ApplicationServices.kAXWindowAttribute
kAXWindowsAttribute = ApplicationServices.kAXWindowsAttribute

kAXApplicationRole = ApplicationServices.kAXApplicationRole
kAXButtonRole = ApplicationServices.kAXButtonRole
kAXCheckBoxRole = ApplicationServices.kAXCheckBoxRole
kAXColumnRole = ApplicationServices.kAXColumnRole
kAXGroupRole = ApplicationServices.kAXGroupRole
kAXListRole = ApplicationServices.kAXListRole
kAXMenuBarRole = ApplicationServices.kAXMenuBarRole
kAXMenuBarItemRole = ApplicationServices.kAXMenuBarItemRole
kAXMenuItemRole = ApplicationServices.kAXMenuItemRole
kAXPopUpButtonRole = ApplicationServices.kAXPopUpButtonRole
kAXRadioButtonRole = ApplicationServices.kAXRadioButtonRole
kAXRowRole = ApplicationServices.kAXRowRole
kAXScrollAreaRole = ApplicationServices.kAXScrollAreaRole
kAXScrollBarRole = ApplicationServices.kAXScrollBarRole
kAXSheetRole = ApplicationServices.kAXSheetRole
kAXStaticTextRole = ApplicationServices.kAXStaticTextRole
kAXSystemWideRole = ApplicationServices.kAXSystemWideRole
kAXTableRole = ApplicationServices.kAXTableRole
kAXTextFieldRole = ApplicationServices.kAXTextFieldRole
kAXWindowRole = ApplicationServices.kAXWindowRole

kAXConfirmAction = ApplicationServices.kAXConfirmAction
kAXDecrementAction = ApplicationServices.kAXDecrementAction
kAXIncrementAction = ApplicationServices.kAXIncrementAction
kAXPressAction = ApplicationServices.kAXPressAction
kAXRaiseAction = ApplicationServices.kAXRaiseAction
kAXShowMenuAction = ApplicationServices.kAXShowMenuAction
