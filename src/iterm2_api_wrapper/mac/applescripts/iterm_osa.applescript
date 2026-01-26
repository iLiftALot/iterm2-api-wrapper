-- Load logging script from the same directory as this script
on loadLoggingScript()
    set myPath to POSIX path of (path to me)
    set scriptDir to do shell script "dirname " & quoted form of myPath
    set loggingScptPath to scriptDir & "/logging_osa.scpt"
    return load script (POSIX file loggingScptPath)
end loadLoggingScript

-- global logging
-- set logging to loadLoggingScript()

-- -- Set the log path (go up 3 dirs from applescripts to project root, then into logs/)
-- set myPath to POSIX path of (path to me)
-- set projectRoot to do shell script "dirname " & quoted form of myPath & " | xargs dirname | xargs dirname | xargs dirname"
-- logging's setLogPath(projectRoot & "/logs/iterm_osa.log")


-- Returns {defaultProfileGuid, defaultProfileName}.
-- iTerm stores the default profile as "Default Bookmark Guid" in its prefs plist.
-- The corresponding profile name is found by scanning "New Bookmarks" for a matching "Guid".
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
    -- Resolve the actual iTerm “default profile” name via preferences (GUID -> bookmark Name)
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


on run {isHotkey}
    global logging
    set logging to loadLoggingScript()

    -- Set the log path (go up 3 dirs from applescripts to project root, then into logs/)
    set myPath to POSIX path of (path to me)
    set projectRoot to do shell script "dirname " & quoted form of myPath & " | xargs dirname | xargs dirname | xargs dirname"
    logging's setLogPath(projectRoot & "/logs/iterm_osa.log")

    if isHotkey then
        logging's log2file("Revealing hotkey window...", "DEBUG")
        my revealHotkeyWindow(logging)
    else
        logging's log2file("Not a hotkey window invocation; doing nothing.", "DEBUG")
    end if
end run
