# Daily Morning Briefing - Windows Task Scheduler Setup
# Run this script as Administrator

$TaskName = "Daily Morning Briefing"
$PythonPath = "C:\Users\AidenKim\AppData\Local\Programs\Python\Python312\python.exe"
$ScriptPath = "C:\claude\secretary\scripts\morning_briefing.py"
$WorkingDir = "C:\claude\secretary"

# Remove existing task if exists
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Removing existing task: $TaskName"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create scheduled task
Write-Host "Creating scheduled task: $TaskName"

# Trigger: Weekdays only at 9:00 AM (주말 제외)
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 9:00AM

# Action: Run Python script
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument $ScriptPath -WorkingDirectory $WorkingDir

# Settings: battery/wake/retry
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

# Register task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Trigger $Trigger `
    -Action $Action `
    -Settings $Settings `
    -Description "매일 아침 9시 /daily 파이프라인 자동 실행 — 3시제 업무 브리핑 + Slack 전송"

Write-Host ""
Write-Host "Task created successfully!"
Write-Host "  Name: $TaskName"
Write-Host "  Schedule: Daily at 9:00 AM"
Write-Host "  Script: $ScriptPath"
Write-Host ""
Write-Host "To run manually: schtasks /run /tn `"$TaskName`""
Write-Host "To check status: schtasks /query /tn `"$TaskName`""
