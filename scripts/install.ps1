# Iravi File Sync Agent — Windows Task Scheduler setup
# Run this script as Administrator once on the FUSIL server.
# Re-running it is safe: it replaces the existing task if one is already registered.

$TaskName   = "IraviFileSyncAgent"
$WorkingDir = "D:\Iravi InHouse\Software\FileSyncAgent"

$Action = New-ScheduledTaskAction `
    -Execute        "python" `
    -Argument       "src\main.py --force" `
    -WorkingDirectory $WorkingDir

# Daily at 22:00 (10:00 PM local time).
# --force bypasses the schedule-window guard in main.py (window is 7-9:30 PM).
$Trigger = New-ScheduledTaskTrigger -Daily -At "22:00"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit  (New-TimeSpan -Hours 2) `
    -MultipleInstances   IgnoreNew `
    -StartWhenAvailable

# Remove existing task silently before re-registering
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# RunLevel Highest = elevated; no -User/-Password = runs in the current user's
# interactive session (required — pywinauto needs a visible desktop to drive FUSIL).
Register-ScheduledTask `
    -TaskName    $TaskName `
    -Action      $Action `
    -Trigger     $Trigger `
    -Settings    $Settings `
    -RunLevel    Highest `
    -Description "Iravi Agro Life LLP — nightly FUSIL export and S3 upload"

Write-Host ""
Write-Host "Task registered: '$TaskName' — runs daily at 22:00 (10:00 PM)"
Write-Host ""
Write-Host "Verify with:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Select-Object TaskName, State"
Write-Host ""
Write-Host "Run manually now with:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
