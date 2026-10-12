# Install, launch, upgrade and uninstall the built installer, silently, as the current user.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging\installer-test.ps1 `
#       -Installer <Setup.exe> -App <built package folder> [-Interactive:$false]
#
# What it proves (per-user install, no administrator rights):
#   * install into a folder with spaces and non-ASCII characters; Start-menu shortcut, uninstall entry
#     in HKCU, no desktop shortcut unless asked for;
#   * the Start-menu shortcut launches the real GUI (a main window appears) and the installed copy
#     passes packaging\smoke.ps1;
#   * upgrade over the same folder with a newer installer: version replaced, stale program files from
#     the old version removed, files the user added to the program folder and all user data kept;
#   * uninstall removes the program, shortcut and registry entry and this program's private runtime
#     data, and keeps the user's voicebanks, generated tracks and preferences.
# It uses the real per-user folders of whoever runs it (the installer decides them) and removes the
# marker files it creates. It does not replace a run on a clean machine (docs/m12-verification.md).
param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][string]$App,
    [switch]$NoGui
)
$ErrorActionPreference = "Stop"
$Installer = (Resolve-Path $Installer).Path
$App = (Resolve-Path $App).Path
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$failures = New-Object System.Collections.Generic.List[string]
function Check($ok, $text) {
    if ($ok) { Write-Output "  ok    $text" } else { Write-Output "  FAIL  $text"; $failures.Add($text) }
}

$appId = "{7A3B1E52-4C8D-4F6A-9B21-5D0E8C6F3A17}_is1"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$appId"
$prefsKey = "HKCU:\Software\BarbershopLearningTracks\BLT Music Generator"
$data = Join-Path $env:LOCALAPPDATA "BarbershopLearningTracks"
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "BLT Music Generator"
$desktopLink = Join-Path ([Environment]::GetFolderPath("DesktopDirectory")) "BLT Music Generator.lnk"
$odd = "Jo" + [char]0x00F6 + "rg M" + [char]0x00FC + "ller " + [char]0x65E5 + [char]0x672C
$base = Join-Path $env:TEMP ("blt-installtest-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$target = Join-Path $base "$odd\Programs\BLT Music Generator"
New-Item -ItemType Directory -Force $base | Out-Null
$dataExisted = Test-Path $data
$prefsExisted = Test-Path $prefsKey
$marker = "blt-installer-test-marker.txt"

if ((Test-Path $uninstallKey) -or (Test-Path $startMenu)) { throw "BLT Music Generator is already installed for this user; uninstall it first so this test cannot disturb it" }

function Install($setup, $extra = @()) {
    $log = Join-Path $base ("install-" + (Split-Path $setup -Leaf) + ".log")
    $process = Start-Process -FilePath $setup -Wait -PassThru -ArgumentList (@("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/DIR=`"$target`"", "/LOG=`"$log`"") + $extra)
    return $process.ExitCode
}

try {
    Write-Output "Installer: $Installer"
    Write-Output "Target:    $target"

    Write-Output ""
    Write-Output "[install]"
    Check ((Install $Installer) -eq 0) "silent per-user install exits 0"
    $exe = Join-Path $target "BLT Music Generator.exe"
    Check (Test-Path -LiteralPath $exe) "the program is installed"
    Check (Test-Path -LiteralPath (Join-Path $target "host\blt-render-host.exe")) "the render host is installed beside it"
    Check ((Test-Path -LiteralPath (Join-Path $target "NOTICES.txt")) -and (Test-Path -LiteralPath (Join-Path $target "LICENSE.txt"))) "NOTICES.txt and LICENSE.txt are installed"
    $entry = Get-ItemProperty $uninstallKey -ErrorAction SilentlyContinue
    Check ($entry -and $entry.DisplayName -eq "BLT Music Generator" -and $entry.DisplayVersion) "a per-user uninstall entry exists ($($entry.DisplayVersion))"
    $link = Join-Path $startMenu "BLT Music Generator.lnk"
    Check (Test-Path -LiteralPath $link) "the Start-menu shortcut exists"
    Check (-not (Test-Path $desktopLink)) "no desktop shortcut by default"
    $shell = New-Object -ComObject WScript.Shell
    # WScript.Shell reports the target in the ANSI code page, so compare only the part that survives it
    Check ($shell.CreateShortcut($link).TargetPath.EndsWith("\Programs\BLT Music Generator\BLT Music Generator.exe")) "the shortcut points at the installed program"

    if (-not $NoGui) {
        $before = @(Get-Process -Name "BLT Music Generator" -ErrorAction SilentlyContinue | ForEach-Object Id)
        Start-Process -FilePath $link
        $window = $null
        for ($i = 0; $i -lt 40 -and -not $window; $i++) {
            Start-Sleep -Milliseconds 500
            $window = Get-Process -Name "BLT Music Generator" -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
        }
        Check ($null -ne $window) "launching the Start-menu shortcut opens the main window ($($window.MainWindowTitle))"
        if ($window) { [void]$window.CloseMainWindow(); Start-Sleep -Seconds 2; if (-not $window.HasExited) { $window.Kill() } }
    }

    Write-Output ""
    Write-Output "[smoke test of the installed copy]"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "smoke.ps1") -App $target
    Check ($LASTEXITCODE -eq 0) "packaged smoke test passes on the installed copy"

    Write-Output ""
    Write-Output "[user data and program-folder edits survive an upgrade]"
    $singers = Join-Path $data "singers\installer-test-voice"
    $outputs = Join-Path $data "outputs\installer-test-song"
    New-Item -ItemType Directory -Force $singers, $outputs | Out-Null
    Set-Content (Join-Path $singers $marker) "a user's voicebank" ; Set-Content (Join-Path $outputs $marker) "generated tracks"
    New-Item -Force $prefsKey | Out-Null; Set-ItemProperty $prefsKey -Name "installer-test" -Value "keep"
    New-Item -ItemType Directory -Force (Join-Path $data "runtime\host-installer-test"), (Join-Path $data "staging\job"), (Join-Path $data "Cache") | Out-Null
    Set-Content (Join-Path $target "_internal\stale-from-old-version.dll") "stale"
    Set-Content (Join-Path $target "my-own-notes.txt") "user file in the program folder"

    $upgrade = Join-Path $base "upgrade\BLT-Music-Generator-99.0.0-Setup.exe"
    $iscc = @($env:BLT_ISCC, "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $iscc) { throw "ISCC not found: needed to build the newer installer for the upgrade test" }
    & $iscc /Qp /DAppVersion=99.0.0 "/DSourceDir=$App" "/DOutputDir=$(Join-Path $base 'upgrade')" (Join-Path $root "packaging\installer.iss") | Out-Null
    Check (Test-Path $upgrade) "a newer installer (99.0.0) was built for the upgrade test"
    Check ((Install $upgrade) -eq 0) "silent upgrade over the existing installation exits 0"
    Check ((Get-ItemProperty $uninstallKey).DisplayVersion -eq "99.0.0") "the version was replaced in place (one uninstall entry, now 99.0.0)"
    Check (-not (Test-Path (Join-Path $target "_internal\stale-from-old-version.dll"))) "program files that the new version no longer ships were removed"
    Check (Test-Path (Join-Path $target "my-own-notes.txt")) "a file the user added to the program folder was kept"
    Check ((Test-Path (Join-Path $singers $marker)) -and (Test-Path (Join-Path $outputs $marker))) "voicebanks and generated tracks were untouched"
    Check (Test-Path (Join-Path $target "BLT Music Generator.exe")) "the upgraded program is present"

    Write-Output ""
    Write-Output "[uninstall]"
    $uninstaller = Get-ChildItem -LiteralPath $target -Filter "unins*.exe" | Select-Object -First 1
    $removal = Start-Process -FilePath $uninstaller.FullName -Wait -PassThru -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
    Check ($removal.ExitCode -eq 0) "silent uninstall exits 0"
    Start-Sleep -Seconds 2
    Check (-not (Test-Path (Join-Path $target "BLT Music Generator.exe"))) "the program was removed"
    Check (-not (Test-Path (Join-Path $target "_internal")) -and -not (Test-Path (Join-Path $target "host"))) "program-owned folders were removed"
    Check (-not (Test-Path $uninstallKey)) "the uninstall entry was removed"
    Check (-not (Test-Path $startMenu)) "the Start-menu shortcut was removed"
    Check (-not (Test-Path (Join-Path $data "runtime"))) "this program's private host runtime copies were removed"
    Check (-not (Test-Path (Join-Path $data "staging")) -and -not (Test-Path (Join-Path $data "Cache"))) "scratch and cache folders were removed"
    Check ((Test-Path (Join-Path $singers $marker)) -and (Test-Path (Join-Path $outputs $marker))) "voicebanks and generated tracks were kept"
    Check ((Get-ItemProperty $prefsKey -ErrorAction SilentlyContinue)."installer-test" -eq "keep") "preferences (HKCU settings) were kept"
}
finally {
    # restore this machine: remove only what this test created
    Remove-Item -LiteralPath (Join-Path $data "singers\installer-test-voice") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $data "outputs\installer-test-song") -Recurse -Force -ErrorAction SilentlyContinue
    if (-not $dataExisted) { Remove-Item -LiteralPath $data -Recurse -Force -ErrorAction SilentlyContinue }
    if ($prefsExisted) { Remove-ItemProperty $prefsKey -Name "installer-test" -ErrorAction SilentlyContinue } else { Remove-Item (Split-Path $prefsKey) -Recurse -Force -ErrorAction SilentlyContinue }
    $leftover = Get-ChildItem -LiteralPath $target -ErrorAction SilentlyContinue
    if ($leftover) { Write-Output "  note: the program folder still holds: $($leftover.Name -join ', ')" }
    cmd /c rmdir /s /q "$base" 2>$null | Out-Null
}
Write-Output ""
if ($failures.Count) {
    Write-Output "INSTALLER TEST FAILED ($($failures.Count)):"
    $failures | ForEach-Object { Write-Output "  - $_" }
    exit 1
}
Write-Output "installer test passed"
