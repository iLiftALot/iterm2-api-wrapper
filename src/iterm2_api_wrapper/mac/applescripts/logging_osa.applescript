-- Logging library for iterm_osa
-- This script should be loaded by other scripts using: load script

property logPath : missing value

on setLogPath(thePath)
    set my logPath to thePath
    set logDir to do shell script "dirname " & quoted form of thePath
    do shell script "mkdir -p " & quoted form of logDir
end setLogPath

on log2file(logmsg, level)
    set logfile to missing value

    try
        if level is missing value then
            set level to "DEBUG"
        end if

        if my logPath is missing value then
            error "Log path has not been set. Call setLogPath before log2file."
        end if

        set logfilepath to my logPath

        -- Build log message with timestamp
        set currentDate to current date
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
        write logmsg & return to logfile starting at eof
        close access logfile
        set logfile to missing value

        return true
    on error errMsg number errNum
        try
            if logfile is not missing value then
                close access logfile
            end if
        end try

        do shell script "echo " & quoted form of ("Failed to write to log file: " & errMsg & " (" & errNum & ")")
        return false
    end try
end log2file
