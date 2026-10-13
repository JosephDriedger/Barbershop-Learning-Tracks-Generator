# Marker files for the "my own data survives upgrade and uninstall" check of the acceptance test.
#
#   powershell -ExecutionPolicy Bypass -File Check-UserData.ps1 -Mode Create    (before upgrading or uninstalling)
#   powershell -ExecutionPolicy Bypass -File Check-UserData.ps1 -Mode Verify    (after each upgrade / uninstall / reinstall)
#   powershell -ExecutionPolicy Bypass -File Check-UserData.ps1 -Mode Clean     (when you are finished)
#
# It creates small files whose names say "tester marker" in the places BLT keeps *your* data, and a setting in the
# registry. It touches nothing else. Verify tells you, for each one, whether it is still there and unchanged.
param([Parameter(Mandatory = $true)][ValidateSet("Create", "Verify", "Clean")][string]$Mode)
$ErrorActionPreference = "Stop"
$data = Join-Path $env:LOCALAPPDATA "BarbershopLearningTracks"
$documents = [Environment]::GetFolderPath("MyDocuments")
$prefsKey = "HKCU:\Software\BarbershopLearningTracks\BLT Music Generator"
$ledger = Join-Path $env:LOCALAPPDATA "blt-tester-markers.json"
$files = [ordered]@{
    "a voicebank in BLT's own voices folder"   = Join-Path $data "singers\tester-marker-voice\marker.txt"
    "generated tracks in BLT's output folder"  = Join-Path $data "outputs\tester-marker-song\marker.txt"
    "a voicebank in Documents\OpenUtau\Singers" = Join-Path $documents "OpenUtau\Singers\tester-marker-voice\marker.txt"
}
$settingName = "tester-marker"

function Sha($path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower() }

switch ($Mode) {
    "Create" {
        $record = @{}
        foreach ($name in $files.Keys) {
            $path = $files[$name]
            New-Item -ItemType Directory -Force (Split-Path $path) | Out-Null
            Set-Content -LiteralPath $path -Value ("tester marker " + [guid]::NewGuid()) -Encoding ascii
            $record[$name] = @{ path = $path; sha256 = (Sha $path) }
            Write-Output "created  $name`n         $path"
        }
        New-Item -Force $prefsKey | Out-Null
        $value = [guid]::NewGuid().ToString()
        Set-ItemProperty $prefsKey -Name $settingName -Value $value
        $record["a setting in BLT's preferences (registry)"] = @{ path = "$prefsKey : $settingName"; value = $value }
        $record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ledger -Encoding utf8
        Write-Output "`nnow upgrade / uninstall / reinstall, then run this script with -Mode Verify"
    }
    "Verify" {
        if (-not (Test-Path $ledger)) { throw "no markers recorded: run -Mode Create first" }
        $record = Get-Content -LiteralPath $ledger -Raw | ConvertFrom-Json
        $bad = 0
        foreach ($name in @($record.PSObject.Properties.Name)) {
            $entry = $record.$name
            if ($entry.sha256) {
                $ok = (Test-Path -LiteralPath $entry.path) -and ((Sha $entry.path) -eq $entry.sha256)
            } else {
                $current = (Get-ItemProperty $prefsKey -ErrorAction SilentlyContinue).$settingName
                $ok = ($current -eq $entry.value)
            }
            Write-Output ("{0,-8} {1}" -f $(if ($ok) { "KEPT" } else { "LOST" }), $name)
            if (-not $ok) { $bad++ }
        }
        if ($bad) { Write-Output "`n$bad of your things are gone: write down which step removed them"; exit 1 }
        Write-Output "`nall of your data is still there"
    }
    "Clean" {
        foreach ($path in $files.Values) { Remove-Item -LiteralPath (Split-Path $path) -Recurse -Force -ErrorAction SilentlyContinue }
        Remove-ItemProperty $prefsKey -Name $settingName -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $ledger -Force -ErrorAction SilentlyContinue
        Write-Output "markers removed"
    }
}
