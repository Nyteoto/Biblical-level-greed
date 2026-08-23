# Register the two scheduled tasks: serve at logon, back up daily.
#
#   powershell -ExecutionPolicy Bypass -File .\install-windows-tasks.ps1
#   powershell -ExecutionPolicy Bypass -File .\install-windows-tasks.ps1 -Remove
#
# The Windows half of pgs.service.example and pgs-backup.timer.example. Those
# two are `.example` files because a systemd unit cannot compute its own paths
# and every line has to be hand-edited; a script can, so this one is not an
# example and needs nothing filled in.
#
# Run as your own user, not elevated. The app writes the data directory as you,
# so the tasks that start it have to be you as well — a task registered as
# SYSTEM would write files your session then could not open, and would map no
# drive letter for the shared disk.
[CmdletBinding()]
param(
    [switch]$Remove,
    # Where the shared data lives on this side. The Linux path /mnt/ssd/pgs-data
    # is the same directory; only the letter differs.
    [string]$DataDir = $(if ($env:PGS_DATA_DIR) { $env:PGS_DATA_DIR } else { 'E:\pgs-data' })
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$serveTask = 'PGS Server'
$backupTask = 'PGS Backup'

if ($Remove) {
    foreach ($name in $serveTask, $backupTask) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Host "  removed $name" -ForegroundColor Yellow
        }
    }
    exit 0
}

$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) {
    Write-Host "No virtual environment at $pythonw — run install-windows.ps1 first." -ForegroundColor Red
    exit 1
}

# -- the server -------------------------------------------------------------
#
# Loopback only, exactly as the systemd unit does it: `tailscale serve`
# publishes it to the tailnet over HTTPS, so nothing binds a routable address
# and there is no window where the port is open without TLS in front of it.
#
# pythonw.exe rather than python.exe, and a hidden window setting besides: a
# task that starts at logon with a console attached puts a black rectangle on
# the desktop for the life of the session.
$serveAction = New-ScheduledTaskAction -Execute $pythonw `
    -Argument "`"$root\desktop.py`" --headless --port 8787" `
    -WorkingDirectory $root
$serveTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# RestartCount/RestartInterval is the Restart=on-failure of the systemd unit:
# the Tailscale service can take a moment after logon, and a server that gave
# up on its first try is one the phone cannot reach until you notice.
$serveSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $serveTask -Action $serveAction `
    -Trigger $serveTrigger -Settings $serveSettings -Force `
    -Description 'Personal Growth System — serves on loopback for `tailscale serve`. See MOBILE.md' | Out-Null
Write-Host "  registered $serveTask" -ForegroundColor Green

# -- the backup -------------------------------------------------------------
#
# StartWhenAvailable is the Persistent=true of the systemd timer, and it is the
# setting that matters most here: a machine that was booted into the *other*
# operating system when the run was due would otherwise skip it silently and
# never catch up, which on a dual-boot machine is most days.
$backupAction = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$root\backup.ps1`"" `
    -WorkingDirectory $root
$backupTrigger = New-ScheduledTaskTrigger -Daily -At 3am
$backupTrigger.RandomDelay = 'PT15M'   # spread it, rather than firing with everything else
$backupSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $backupTask -Action $backupAction `
    -Trigger $backupTrigger -Settings $backupSettings -Force `
    -Description 'Daily backup of Personal Growth System data. See SYNC.md' | Out-Null
Write-Host "  registered $backupTask" -ForegroundColor Green

Write-Host @"

Both tasks run as $env:USERNAME, at logon and daily respectively.

  Get-ScheduledTask 'PGS *'                     are they registered
  Get-ScheduledTaskInfo 'PGS Backup'            when did the backup last run
  Start-ScheduledTask -TaskName 'PGS Backup'    run one now
  .\install-windows-tasks.ps1 -Remove           take both out again

The server task serves 127.0.0.1:8787 and nothing else. To reach it from the
phone, put Tailscale in front of it — see MOBILE.md:

  tailscale serve --bg --https=443 http://127.0.0.1:8787

Data directory for this side: $DataDir
"@
