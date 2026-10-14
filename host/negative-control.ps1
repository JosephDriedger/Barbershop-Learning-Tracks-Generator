# Prove that the package checks can fail: build the render host from the UNPATCHED pinned OpenUtau (with the Voicevox
# classes, the English "plus" dictionary, Arpasing+, English C+V, the other languages' dictionaries) and run the three
# checks on it. Each of them must REFUSE this host. If one passes it, the check is blind and this script fails.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File host\negative-control.ps1 [-OpenUtauSrc DIR] [-Out DIR]
#
# Needs the pinned OpenUtau checkout (host\build.ps1 fetches it) and a .NET 8 SDK. Nothing is published; the control
# host is built into research-output\host\unpatched-control and is never packaged.
param(
    [string]$OpenUtauSrc = "",
    [string]$Out = ""
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OpenUtauSrc) { $OpenUtauSrc = Join-Path $root "research-output\openutau-src" }
if (-not $Out) { $Out = Join-Path $root "research-output\host\unpatched-control" }
$python = if ($env:BLT_PYTHON) { $env:BLT_PYTHON } elseif (Test-Path (Join-Path $root ".venv\Scripts\python.exe")) { Join-Path $root ".venv\Scripts\python.exe" } else { "python" }
$localSdk = Join-Path $root "research-output\spike\dotnet"
if (-not $env:DOTNET_ROOT -and (Test-Path $localSdk)) { $env:DOTNET_ROOT = $localSdk }
if ($env:DOTNET_ROOT) { $env:PATH = "$env:DOTNET_ROOT;$env:PATH" }
if (-not $env:DOTNET_ROOT) { $env:DOTNET_ROOT = Split-Path (Get-Command dotnet).Source }   # the control host is framework-dependent
$env:DOTNET_CLI_TELEMETRY_OPTOUT = "1"
$env:DOTNET_NOLOGO = "1"
$nuget = Join-Path $root "research-output\spike\nuget"
if (-not $env:NUGET_PACKAGES -and (Test-Path $nuget)) { $env:NUGET_PACKAGES = $nuget }

$OpenUtauSrc = (Resolve-Path $OpenUtauSrc).Path
if (Test-Path $Out) { & $python -c "import shutil,sys; shutil.rmtree(sys.argv[1])" $Out }
New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
Write-Output "building the host from the UNPATCHED $OpenUtauSrc ..."
$build = dotnet build (Join-Path $PSScriptRoot "BltRenderHost\BltRenderHost.csproj") -c Release -o $Out "-p:OpenUtauSrc=$OpenUtauSrc" "-p:OpenUtauCommit=unpatched-control" 2>&1
if ($LASTEXITCODE -ne 0) { $build | Select-Object -Last 30; throw "the control host did not build" }
# the checks read blt-host-build.json; this host has BLT's native library absent on purpose
$info = [ordered]@{ schema = "blt.host-build/1"; worldline = "stock (control)"; worldline_sha256 = ""; g2p_model = "included" }
[System.IO.File]::WriteAllText((Join-Path $Out "blt-host-build.json"), ($info | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))

$failures = New-Object System.Collections.Generic.List[string]
function Expect-Refusal($name, $exe, $arguments, $mustMention) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & $exe @arguments 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    $text = $output -join "`n"
    if ($code -eq 0) { $failures.Add("$name PASSED the unpatched host: it is blind"); return }
    foreach ($needle in $mustMention) {
        if ($text -notmatch [regex]::Escape($needle)) { $failures.Add("$name refused the host but never mentioned '$needle'") }
    }
    Write-Output "ok: $name refused the unpatched host (exit $code)"
}
Expect-Refusal "verify_host_inventory.py" $python @("-I", (Join-Path $root "packaging\verify_host_inventory.py"), $Out) `
    @("ArpasingPlusPhonemizer", "EnglishCpVPhonemizer", "DiffSingerARPAPlusEnglishPhonemizer", "g2p_arpabet_plus", "Voicevox", "BLT removed", "set of types")
Expect-Refusal "verify_absent_data.py" $python @("-I", (Join-Path $root "packaging\verify_absent_data.py"), $Out, "--openutau-src", $OpenUtauSrc) `
    @("g2p-arpabet-plus.zip", "en_cPv.template.yaml")
Expect-Refusal "verify-host.ps1" "powershell" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "verify-host.ps1"), "-HostDir", $Out, "-OpenUtauSrc", $OpenUtauSrc, "-AllowStockWorldline") `
    @("Voicevox", "plus", "contains the name")
if ($failures.Count) {
    $failures | ForEach-Object { Write-Output "FAIL: $_" }
    exit 1
}
Write-Output "negative control passed: all three checks refuse a host that still has the removed engines and data"
