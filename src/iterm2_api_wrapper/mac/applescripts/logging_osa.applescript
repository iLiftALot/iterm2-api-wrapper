-- Logging library for iterm_osa
-- This script should be loaded by other scripts using: load script

property logPath : missing value

on setLogPath(thePath)
    set my logPath to thePath
end setLogPath

on log2file(logmsg, level)
    try
        if level is missing value then
            set level to "DEBUG"
        end if
        set logfilepath to my logPath
        -- Build log message with timestamp
        set currentDate to current date -- Get current date and time
        set y to year of currentDate as string
        set m to text -2 thru -1 of ("0" & (month of currentDate as integer) as string)
        set d to text -2 thru -1 of ("0" & (day of currentDate as integer) as string)
        set h to text -2 thru -1 of ("0" & (hours of currentDate as integer) as string)
        set min to text -2 thru -1 of ("0" & (minutes of currentDate as integer) as string)
        set s to text -2 thru -1 of ("0" & (seconds of currentDate as integer) as string)
        set timestamp to level & " -- [" & y & "-" & m & "-" & d & " " & h & ":" & min & ":" & s & "] -- "
        set logmsg to timestamp & logmsg
        -- Open the log file for writing
        set logfile to open for access logfilepath with write permission
        write logmsg & return to logfile starting at eof -- Append to end of file
        close access logfile
        return true
    on error
        do shell script "echo 'Failed to write to log file'"
        try
            close access logfile
        end try
        return false
    end try
end log2file
