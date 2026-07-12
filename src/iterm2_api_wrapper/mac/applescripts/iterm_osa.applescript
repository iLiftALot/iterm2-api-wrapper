-- Load logging script relative to the passed-in script directory
on loadLoggingScript(scriptDir)
	set loggingScptPath to scriptDir & "/logging_osa.scpt"
	return load script (POSIX file loggingScptPath)
end loadLoggingScript


-- Returns {defaultProfileGuid, defaultProfileName}.
on itermDefaultProfileInfo()
	set defaultGuid to missing value
	set defaultName to missing value
	try
		tell application "System Events"
			set prefsFilePath to ((path to preferences folder from user domain) as text) & "com.googlecode.iterm2.plist"
			set prefsPlist to property list file prefsFilePath
			set defaultGuid to value of property list item "Default Bookmark Guid" of prefsPlist
			set bookmarksItem to property list item "New Bookmarks" of prefsPlist
			repeat with b in property list items of bookmarksItem
				try
					if (value of property list item "Guid" of b) is defaultGuid then
						set defaultName to value of property list item "Name" of b
						exit repeat
					end if
				end try
			end repeat
		end tell
	end try
	return {defaultGuid, defaultName}
end itermDefaultProfileInfo


on getiTermDefaultProfileName(logging)
	set {targetProfileGuid, targetProfile} to my itermDefaultProfileInfo()
	if targetProfile is missing value then set targetProfile to "Default"
	if targetProfileGuid is missing value then
		logging's log2file("Default profile GUID: (missing)", "WARN")
	else
		logging's log2file("Default profile GUID: " & targetProfileGuid, "DEBUG")
	end if
	logging's log2file("Default profile name: " & targetProfile, "DEBUG")
	return targetProfile
end getiTermDefaultProfileName


-- Tool 1: Reveal hotkey window
on revealHotkeyWindow(logging)
	tell application "iTerm"
		logging's log2file("Starting iTerm script", "DEBUG")
		activate

		tell current window
			reveal hotkey window
		end tell

		logging's log2file("Finished iTerm script", "DEBUG")
	end tell
end revealHotkeyWindow


-- Expecting 2 arguments from osascript:
-- argv item 1: The string "true" or "false"
-- argv item 2: The absolute POSIX path to the directory containing this script
on run argv
	global logging

	-- 1. Parse and cast parameters safely
	set isHotkeyStr to item 1 of argv
	set scriptDir to item 2 of argv

	set isHotkey to (isHotkeyStr is "true")

	-- 2. Dynamically load logging using the passed script path
	set logging to loadLoggingScript(scriptDir)

	-- 3. Resolve project root based on the reliable directory parameter
    set projectRoot to do shell script "cd " & quoted form of scriptDir & " && cd ../../../../ && pwd"
    do shell script "mkdir -p " & quoted form of (projectRoot & "/logs")
    logging's setLogPath(projectRoot & "/logs/iterm_osa.log")

	-- 4. Execute Logic
	if isHotkey then
		logging's log2file("Revealing hotkey window...", "DEBUG")
		my revealHotkeyWindow(logging)
	else
		logging's log2file("Not a hotkey window invocation; doing nothing.", "DEBUG")
	end if
end run
