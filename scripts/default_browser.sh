#!/usr/bin/env sh

set -eo pipefail

function default_browser() {
    osascript <<'AS'
use framework "AppKit"
use scripting additions

set wurl to current application's NSURL's URLWithString:"https://www.apple.com"
set appURL to (current application's NSWorkspace's sharedWorkspace())'s URLForApplicationToOpenURL:wurl
set appBundle to current application's NSBundle's bundleWithURL:appURL
return (appBundle's bundleIdentifier()) as text
AS
}

default_browser
