# Prints facts about this PC that the acceptance results need. Changes nothing.
#
#   powershell -ExecutionPolicy Bypass -File Collect-Environment.ps1 | Tee-Object environment.txt
$ErrorActionPreference = "Continue"
$current = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion"
Write-Output "date:               $(Get-Date -Format s)"
Write-Output "windows:            $($current.ProductName) $($current.DisplayVersion) build $($current.CurrentBuildNumber).$($current.UBR)"
Write-Output "64-bit windows:     $([Environment]::Is64BitOperatingSystem)"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Output "account:            $($identity.Name)   administrator rights in this session: $admin"
$vcKey = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
if (Test-Path $vcKey) {
    $vc = Get-ItemProperty $vcKey
    Write-Output "visual c++ runtime: installed=$($vc.Installed) version $($vc.Major).$($vc.Minor).$($vc.Bld) (BLT needs 14.44.35211 or newer)"
} else {
    Write-Output "visual c++ runtime: NOT installed (registry key absent)"
}
$uninstall = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{7A3B1E52-4C8D-4F6A-9B21-5D0E8C6F3A17}_is1"
if (Test-Path $uninstall) {
    $blt = Get-ItemProperty $uninstall
    Write-Output "BLT installed:      $($blt.DisplayName) $($blt.DisplayVersion) in $($blt.InstallLocation)"
} else {
    Write-Output "BLT installed:      no"
}
try {
    $av = Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop
    Write-Output "antivirus:          $(($av | ForEach-Object { $_.displayName }) -join ', ')"
} catch { Write-Output "antivirus:          (not readable on this edition)" }
$up = Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq "Up" }
Write-Output "network adapters up: $(if ($up) { ($up | ForEach-Object { $_.Name }) -join ', ' } else { 'none' })"
Write-Output "tools that a clean PC should not have:"
foreach ($tool in "python", "py", "dotnet", "git", "ffmpeg", "devenv", "msbuild") {
    Write-Output ("  {0,-8} {1}" -f $tool, $(if (Get-Command $tool -ErrorAction SilentlyContinue) { "present" } else { "absent" }))
}
