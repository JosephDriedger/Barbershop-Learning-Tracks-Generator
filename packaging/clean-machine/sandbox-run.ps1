# Runs INSIDE a fresh Windows Sandbox (or any pristine Windows machine) to check an installer.
#   Sandbox: started by start-sandbox.ps1 (logon command). Other machine: run it by hand from the
#   folder that holds the installer:  powershell -ExecutionPolicy Bypass -File sandbox-run.ps1
# It records what the machine lacks, installs for the current user, runs the built-in self-test and
# writes a report. Launching the program from the Start menu and generating from a real score is
# left to the person at the keyboard (docs/m12-verification.md, checklist).
param(
    [string]$In = "C:\blt-in",
    [string]$Out = "C:\blt-out"
)
$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force $Out | Out-Null
$report = Join-Path $Out "clean-machine-report.txt"
function Log($text) { Write-Output $text; Add-Content -Path $report -Value $text -Encoding utf8 }
Set-Content -Path $report -Value "BLT Music Generator clean-machine check, $(Get-Date -Format s)" -Encoding utf8

Log "-- what this machine does NOT have (all should be 'absent')"
foreach ($tool in "python", "py", "dotnet", "git", "ffmpeg", "devenv", "msbuild") {
    Log ("  {0,-8} {1}" -f $tool, $(if (Get-Command $tool -ErrorAction SilentlyContinue) { "PRESENT (not a clean machine for this check)" } else { "absent" }))
}
foreach ($variable in "DOTNET_ROOT", "PYTHONHOME", "PYTHONPATH", "BLT_HOST_DIR", "BLT_DATA_DIR") {
    Log ("  env {0,-14} {1}" -f $variable, $(if (Test-Path "env:$variable") { "SET" } else { "not set" }))
}
Log "  user name: $env:USERNAME   profile: $env:USERPROFILE"

$setup = Get-ChildItem -Path $In -Filter "BLT-Music-Generator-*-Setup.exe" | Select-Object -First 1
if (-not $setup) { Log "FAIL: no installer in $In"; exit 1 }
Log "-- installing $($setup.Name) for the current user"
$target = Join-Path $env:LOCALAPPDATA "Programs\BLT Music Generator"
$p = Start-Process -FilePath $setup.FullName -Wait -PassThru -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/LOG=$Out\install.log"
Log "  installer exit code: $($p.ExitCode)"
$exe = Join-Path $target "blt.exe"
if (-not (Test-Path $exe)) { Log "FAIL: $exe not found"; exit 1 }

Log "-- version"
& $exe --version 2>&1 | ForEach-Object { Log "  $_" }
Log "-- self-test (built-in score, generated voicebank; first launch installs the host runtime)"
$t = Get-Date
& $exe selftest --keep (Join-Path $Out "selftest") 2>&1 | ForEach-Object { Log "  $_" }
Log "  exit code: $LASTEXITCODE  ($([math]::Round(((Get-Date) - $t).TotalSeconds, 1)) s)"
Log "-- second self-test (the host runtime copy must be reused)"
& $exe selftest 2>&1 | ForEach-Object { Log "  $_" }
Log "  exit code: $LASTEXITCODE"
Log "-- Start menu"
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "BLT Music Generator\BLT Music Generator.lnk"
Log ("  shortcut " + $(if (Test-Path $lnk) { "present: $lnk" } else { "MISSING" }))
Log ""
Log "Now, by hand: open the Start menu, start 'BLT Music Generator', and go through the checklist in"
Log "docs/m12-verification.md (load a score, assign voices, resolve lyrics, generate, open the folder,"
Log "close, relaunch, then uninstall from Settings > Apps)."
