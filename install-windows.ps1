# Install the Personal Growth System as a desktop app on Windows.
#
# Idempotent: safe to re-run after `git pull`, which is how you update.
#
#   powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
#
# This is a second installer, not a port of the first. install-linux.sh spends
# most of its length on WebKitGTK and PyGObject — a system library the venv
# cannot see and a Python-version match that fails confusingly at import time.
# None of that exists here: pywebview renders through WebView2, which ships with
# Windows 11 and installs as a normal redistributable on 10, so the window needs
# no bridging into the virtual environment at all.
#
# What this checkout is NOT: shared with the Linux side. The Linux repo lives on
# btrfs, which Windows cannot read, so this is its own clone with its own .venv
# and its own node_modules — and `git pull` is how work crosses between them.
# Only `data\` is shared, on the exFAT disk. See SYNC.md.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
# npm and pytest both exit nonzero for reasons this script reports itself — a
# failing test is information, not a crash — and PowerShell 7.4 would turn each
# one into a terminating error before the summary line is ever printed.
if (Test-Path Variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}
Set-Location -LiteralPath $PSScriptRoot
$root = $PSScriptRoot

function Say([string]$m) { Write-Host "`n$m" -ForegroundColor White }
function Warn([string]$m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function OK([string]$m) { Write-Host "  OK $m" -ForegroundColor Green }
function Die([string]$m) { Write-Host "`n$m" -ForegroundColor Red; exit 1 }

Say '1/6  System packages'

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $python) {
    Die @"
Python is not on PATH.
     winget install Python.Python.3.13
     (then open a new terminal and re-run this script)
"@
}
$pyVersion = & $python.Source -c 'import sys; print("%d.%d" % sys.version_info[:2])'
if ([version]$pyVersion -lt [version]'3.11') {
    Die "Python $pyVersion is too old; this needs 3.11 or newer."
}
OK "Python $pyVersion"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Die @"
Node is not on PATH.
     winget install OpenJS.NodeJS.LTS
     (then open a new terminal and re-run this script)
"@
}
OK "npm $(& npm --version)"

# pywebview draws into WebView2, the same Chromium-based control Edge uses.
# Windows 11 ships it; Windows 10 may not. Checking the registry rather than
# trying to open a window means the failure is reported here, with the fix,
# instead of as an empty grey frame the first time the app is launched.
$webview2 = @(
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
) | Where-Object { Test-Path $_ }
if ($webview2) {
    OK 'WebView2 runtime present'
} else {
    Warn 'WebView2 runtime not found — the native window will not open.'
    Warn '     winget install Microsoft.EdgeWebView2Runtime'
    Warn '     (the app still works meanwhile: pgs --browser)'
}

Say '2/6  Python environment'
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $python.Source -m venv .venv
}
& $venvPython -m pip install -q --upgrade pip
& $venvPython -m pip install -q -r backend\requirements.txt
OK 'dependencies installed'

Say '3/6  Data'
# The repo holds the app, not your practice, so `data\` is created here rather
# than arriving with the clone. The six researched trees are copied out of
# data\seed\ — once, and only into an empty directory.
#
# Deliberately not a sync, and deliberately not done at startup. A tree you
# deleted in the UI has to stay deleted, and one you have edited must never be
# reverted by re-running this script.
#
# Note this seeds the *local* data\, which on this machine is not the directory
# the app will use — PGS_DATA_DIR points at the shared disk, which the Linux
# side seeded long ago. Left in anyway, because a checkout with no data\ cannot
# be run without the flag, and `pgs` with no arguments should still start.
New-Item -ItemType Directory -Force -Path data\domains, data\log | Out-Null
if (-not (Get-ChildItem -LiteralPath data\domains -ErrorAction SilentlyContinue)) {
    Copy-Item data\seed\*.toml data\domains\
    OK "seeded data\domains\ with $((Get-ChildItem data\seed\*.toml).Count) trees"
} else {
    OK 'data\domains\ already has trees — left untouched'
}

Say '4/6  Frontend'
# frontend\build is gitignored, so a fresh clone or a pull that changed the UI
# leaves nothing to serve until this runs. This is the step that most often
# explains "I pulled and it looks the same".
#
# Both npm calls are checked. `$ErrorActionPreference = 'Stop'` does not reach a
# native command, and this script has already turned off the one setting that
# would have — so an unchecked `npm run build` can fail, print its errors, and
# still be followed by a green OK. That happened: a case-insensitive import
# resolved to the wrong file, the build died, and the installer reported it
# built. The output is held back until it is needed; on success it is warnings.
Push-Location frontend
try {
    if (-not (Test-Path -LiteralPath node_modules)) {
        & npm install --silent
        if ($LASTEXITCODE -ne 0) { Die 'npm install failed; the frontend cannot be built.' }
    }
    $built = & npm run build 2>&1
    if ($LASTEXITCODE -ne 0) {
        $built | ForEach-Object { Write-Host "     $_" }
        Die 'The frontend build failed. Nothing was written to frontend\build, so the app would serve the last build that worked, or nothing at all.'
    }
} finally { Pop-Location }
OK 'built to frontend\build'

Say '5/6  Launcher'
$bin = Join-Path $env:LOCALAPPDATA 'Programs\pgs'
New-Item -ItemType Directory -Force -Path $bin | Out-Null

@"
@echo off
REM Generated by install-windows.ps1 — re-run that script to regenerate.
"$venvPython" "$root\desktop.py" %*
"@ | Set-Content -LiteralPath (Join-Path $bin 'pgs.cmd') -Encoding ASCII
OK "$bin\pgs.cmd"

# pythonw.exe rather than python.exe for the shortcut: launched from the Start
# Menu there is no console to write to, and python.exe would flash one up and
# leave it behind the window for the life of the app.
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut(
    (Join-Path $startMenu 'Personal Growth System.lnk'))
$shortcut.TargetPath = Join-Path $root '.venv\Scripts\pythonw.exe'
$shortcut.Arguments = "`"$root\desktop.py`""
$shortcut.WorkingDirectory = $root
$shortcut.Description = 'Local tech tree for deliberate practice'
$shortcut.Save()
OK "$startMenu\Personal Growth System.lnk"

$onPath = ($env:PATH -split ';') -contains $bin
if (-not $onPath) {
    Warn "$bin is not on PATH. To add it for future terminals:"
    Warn "     [Environment]::SetEnvironmentVariable('PATH', `"`$env:PATH;$bin`", 'User')"
}

Say '6/6  Check'
& $venvPython -m pytest backend\tests -q 2>&1 | Select-Object -Last 1

Write-Host @"

Done. Launch from the Start Menu, or:

  pgs                                     native window, data in .\data
  pgs --data-dir F:\pgs-data              the disk shared with Linux (see SYNC.md)
  pgs --browser                           no window, opens your browser
  pgs --headless --host tailscale         serve to your phone (see MOBILE.md)

Set the shared disk once, so you never launch against the wrong data:

  [Environment]::SetEnvironmentVariable('PGS_DATA_DIR', 'F:\pgs-data', 'User')
"@
