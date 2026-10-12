# Start a Windows Sandbox that installs the built installer and runs the clean-machine check.
#   powershell -ExecutionPolicy Bypass -File packaging\clean-machine\start-sandbox.ps1 -Installer <Setup.exe>
# Needs Windows 10/11 Pro, Enterprise or Education with the "Windows Sandbox" feature enabled
# (not available on Home editions). The report lands in <results>\clean-machine-report.txt.
param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [string]$Results = ""
)
$ErrorActionPreference = "Stop"
$Installer = (Resolve-Path $Installer).Path
if (-not $Results) { $Results = Join-Path (Split-Path $Installer) "clean-machine-results" }
$inDir = Join-Path (Split-Path $Installer) "clean-machine-in"
New-Item -ItemType Directory -Force $inDir, $Results | Out-Null
Copy-Item $Installer $inDir -Force
Copy-Item (Join-Path $PSScriptRoot "sandbox-run.ps1") $inDir -Force
$sandbox = Get-Command WindowsSandbox.exe -ErrorAction SilentlyContinue
if (-not $sandbox) { throw "Windows Sandbox is not available on this machine (needs Pro/Enterprise/Education with the feature enabled)" }
$config = @"
<Configuration>
  <VGpu>Disable</VGpu>
  <Networking>Disable</Networking>
  <MappedFolders>
    <MappedFolder><HostFolder>$inDir</HostFolder><SandboxFolder>C:\blt-in</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>$Results</HostFolder><SandboxFolder>C:\blt-out</SandboxFolder><ReadOnly>false</ReadOnly></MappedFolder>
  </MappedFolders>
  <LogonCommand><Command>powershell -NoProfile -ExecutionPolicy Bypass -File C:\blt-in\sandbox-run.ps1</Command></LogonCommand>
</Configuration>
"@
$file = Join-Path $Results "blt-clean-machine.wsb"
Set-Content $file $config -Encoding utf8
Write-Output "Starting Windows Sandbox with $file"
Start-Process WindowsSandbox.exe -ArgumentList "`"$file`""
