# Copy data\ to a second physical disk. The Windows half of backup.sh.
#
# The repo holds the app; this machine holds everything you have done with it.
# Neither operating system's copy of the event log, the trees, the captures or
# the photographs exists anywhere else, so this script is the only thing
# standing between a dead disk and losing all of it.
#
#   .\backup.ps1                   # to the configured destination
#   .\backup.ps1 D:\pgs-backup     # ...or somewhere else, e.g. a plugged-in SSD
#
# Safe to run by hand at any time, and safe to run twice.
#
# Why this is a second script rather than a shared one
# ----------------------------------------------------
# `backup.sh` is not portable and should not be made portable: `rsync`, `df
# --output=source` and `date -Iseconds` have no Windows equivalents worth
# shimming, and a script full of platform branches is one nobody can read the
# refusals out of. What is shared is the *two refusals*, and they are restated
# here in full rather than referred to, because a refusal you have to look up
# is one that gets removed by the next person in a hurry.
#
# **The two backups do not meet.** The Linux side writes /mnt/data/pgs-backup on
# an ext4 disk Windows cannot read, so this one writes somewhere else. That is
# not a divergence to reconcile: both read the same shared data directory, and
# neither ever deletes, so each is a complete copy of the same source. Two
# copies is the point.
[CmdletBinding()]
param([string]$Destination)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Die([string]$message) {
    Write-Host "backup failed: $message" -ForegroundColor Red
    exit 1
}

$data = if ($env:PGS_DATA_DIR) { $env:PGS_DATA_DIR } else { Join-Path $PSScriptRoot 'data' }
if (-not $Destination) {
    $Destination = if ($env:PGS_BACKUP_DIR) { $env:PGS_BACKUP_DIR } else { 'C:\pgs-backup' }
}

if (-not (Test-Path -LiteralPath $data -PathType Container)) {
    Die "no data directory at $data"
}

# The destination usually does not exist yet on a first run, so the comparison
# is made against its nearest existing ancestor — which is the filesystem the
# write would actually land on.
function Anchor([string]$path) {
    # Not [System.IO.Path]::GetFullPath: that resolves against .NET's current
    # directory, which Set-Location does not touch. A relative destination
    # would be anchored against wherever the process happened to start, and
    # the volume check below would then be answering about a different path
    # than the one robocopy writes to — a wrong answer, from the check whose
    # entire job is to be right about that.
    $current = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($path)
    while (-not (Test-Path -LiteralPath $current) -and $current -ne [System.IO.Path]::GetPathRoot($current)) {
        $current = Split-Path -Parent $current
    }
    return $current
}

# The one check that matters: the destination must be on a different device
# than the source. A second copy on one disk is not a backup; it is two files
# that die together.
#
# This is also, and not obviously, the check that catches an unmounted backup
# disk — or on Windows, a drive letter that did not come back after a reboot.
# When F:\ is absent, a path built from it fails outright, but a *stale* path
# under C:\ that used to be the backup would cheerfully "succeed", write the
# backup onto the very disk it exists to protect against, and report nothing
# wrong for months.
#
# Volumes are compared by path root rather than by volume GUID: a drive letter
# maps to exactly one volume, needs no elevation and no optional module. The
# case it gets wrong is a volume mounted into a folder rather than given a
# letter — that shares its parent's root and is refused when it need not be.
# A false refusal is the safe direction, and it is the direction backup.sh
# chooses too.
function VolumeOf([string]$path) {
    return [System.IO.Path]::GetPathRoot((Anchor $path)).ToUpperInvariant()
}

$sourceVolume = VolumeOf $data
$destVolume = VolumeOf $Destination
if ($sourceVolume -eq $destVolume) {
    Die @"
$Destination would land on the same volume as your data ($sourceVolume).
  Almost always this means the backup disk is not mounted, or a drive letter
  moved after a reboot, so the destination is just a folder on the system
  disk. Copying there protects nothing, so this is a refusal rather than a
  warning.
  Check with:  Get-Volume
"@
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null

# Robocopy is parsed by the C runtime, not by PowerShell, and there a path
# ending in a backslash arrives as `"F:\pgs-data\"` — the backslash escapes the
# closing quote and the next argument is swallowed into the path. `F:\` is the
# case that actually happens, because a drive root cannot be written without
# one; it is kept as `F:\.` rather than trimmed away to nothing.
function Unslash([string]$path) {
    $trimmed = $path.TrimEnd('\')
    if ($trimmed -match '^[A-Za-z]:$') { return "$trimmed\." }
    return $trimmed
}

# No /MIR and no /PURGE, deliberately — this is the missing `--delete`.
#
# Everything here is append-only or hand-written, so the local copy shrinking is
# never something to propagate: a truncated log, a tree deleted by a misclick or
# a folder lost to a bad command would all be faithfully mirrored, and the
# backup would destroy the very thing you wanted it for. Without /MIR the
# destination only ever grows, which for a few hundred kilobytes a year is a
# trade worth making.
#
# index.sqlite is excluded: it rebuilds from the log, and copying a database
# while the app may be writing it produces a file that is worse than absent.
# /XF matches by name in every directory, so capture\index.sqlite goes too —
# the same reach as the leading-slash-less rsync exclude on the other side.
$robocopy = @(
    (Unslash $data), (Unslash $Destination),
    '/E',                       # subdirectories, including empty ones
    '/XF', 'index.sqlite',
    '/R:2', '/W:2',             # a locked file must not hang the run for an hour
    '/NFL', '/NDL', '/NJH', '/NP'
)
# PowerShell 7.4 turns a native command's nonzero exit into a terminating
# error by default, and $ErrorActionPreference is 'Stop' above. Left alone
# that combination throws on robocopy's exit code 1 — which means "files were
# copied", the successful case — so the check below would never be reached and
# every working backup would report as a crash. Exit codes are read here, not
# delegated.
if (Test-Path Variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

& robocopy.exe @robocopy | Out-Null
$code = $LASTEXITCODE

# Robocopy does not use 0 for success. Anything below 8 is a completed run —
# 0 nothing to do, 1 files copied, 2 extras present, 4 mismatches — and 8 and
# above are real failures. Treating nonzero as failure would report every
# successful backup as broken.
if ($code -ge 8) {
    Die "robocopy exited $code — see https://learn.microsoft.com/windows-server/administration/windows-commands/robocopy"
}

# A timestamp the app's Settings page — and you — can read to answer "when did
# this last actually work", which is the only question that matters about a
# backup and the one a silent scheduled task never answers. The format matches
# `date -Iseconds` so both operating systems write a stamp the same reader
# parses.
(Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz') | Set-Content -LiteralPath (Join-Path $Destination '.last-backup') -NoNewline

$size = (Get-ChildItem -LiteralPath $Destination -Recurse -File -ErrorAction SilentlyContinue |
    Measure-Object -Property Length -Sum).Sum
if (-not $size) { $size = 0 }
$human = if ($size -ge 1GB) { '{0:N1} GB' -f ($size / 1GB) } elseif ($size -ge 1MB) { '{0:N1} MB' -f ($size / 1MB) } else { '{0:N0} KB' -f ($size / 1KB) }

Write-Host "OK  $data -> $Destination ($human)" -ForegroundColor Green
