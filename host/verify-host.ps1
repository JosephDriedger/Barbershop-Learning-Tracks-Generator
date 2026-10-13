# Check what the built host really contains (it is a patched build of OpenUtau, so trust nothing).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File host\verify-host.ps1 -HostDir DIR -OpenUtauSrc DIR
#
# Reads OpenUtau.Core.dll and OpenUtau.Plugin.Builtin.dll with reflection (no code of theirs runs) and
# fails unless:
#   * no type of either assembly belongs to the Voicevox classes (derived from the LGPL VOICEVOX engine);
#   * the embedded English dictionaries are byte-identical to the pinned OpenUtau's own (arpabet = CMUdict
#     and arpabet-plus, which stays an open licensing item) and every other g2p pack and every Vogen
#     data file is empty;
#   * the CREPE model is still there (MIT);
#   * worldline.dll is the one recorded in blt-host-build.json (BLT's build, not the stock DLL) unless
#     -AllowStockWorldline (local runs only).
param(
    [Parameter(Mandatory = $true)][string]$HostDir,
    [Parameter(Mandatory = $true)][string]$OpenUtauSrc,
    [switch]$AllowStockWorldline
)
$ErrorActionPreference = "Stop"
$HostDir = (Resolve-Path $HostDir).Path
$OpenUtauSrc = (Resolve-Path $OpenUtauSrc).Path
$problems = New-Object System.Collections.Generic.List[string]

function Load-Types($path) {
    $assembly = [System.Reflection.Assembly]::LoadFile($path)
    try { return @($assembly.GetTypes()) } catch [System.Reflection.ReflectionTypeLoadException] { return @($_.Exception.Types | Where-Object { $_ }) }
}
function Resource-Sizes($path, $resourceFile) {
    $assembly = [System.Reflection.Assembly]::LoadFile($path)
    $stream = $assembly.GetManifestResourceStream($resourceFile)
    if (-not $stream) { return $null }
    $reader = New-Object System.Resources.ResourceReader($stream)
    $result = @{}
    foreach ($entry in $reader.GetEnumerator()) { $result[$entry.Key] = $entry.Value }
    return $result
}
function Sha($bytes) { $sha = [System.Security.Cryptography.SHA256]::Create(); ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace "-", "").ToLower() }

$core = Join-Path $HostDir "OpenUtau.Core.dll"
$builtin = Join-Path $HostDir "OpenUtau.Plugin.Builtin.dll"
foreach ($dll in $core, $builtin) {
    $voicevox = @(Load-Types $dll | Where-Object { $_.FullName -match "Voicevox" })
    if ($voicevox.Count) { $problems.Add("$(Split-Path $dll -Leaf) still has $($voicevox.Count) Voicevox type(s), e.g. $($voicevox[0].FullName)") }
}

$g2p = Resource-Sizes $core "OpenUtau.Core.G2p.Data.Resources.resources"
$pinned = Join-Path $OpenUtauSrc "OpenUtau.Core\G2p\Data"
$english = @{ "g2p-arpabet" = "g2p-arpabet.zip"; "g2p_arpabet_plus" = "g2p-arpabet-plus.zip" }
if (-not $g2p) { $problems.Add("the g2p resources are missing") } else {
    foreach ($key in $g2p.Keys) {
        if ($english.ContainsKey($key)) {
            $expected = Sha ([System.IO.File]::ReadAllBytes((Join-Path $pinned $english[$key])))
            if ((Sha $g2p[$key]) -ne $expected) { $problems.Add("$key differs from the pinned OpenUtau's $($english[$key])") }
        } elseif ($g2p[$key].Length -gt 64) {
            $problems.Add("g2p pack $key is not empty ($($g2p[$key].Length) bytes)")
        }
    }
    foreach ($key in $english.Keys) { if (-not $g2p.ContainsKey($key)) { $problems.Add("English dictionary $key is missing") } }
}
$vogen = Resource-Sizes $core "OpenUtau.Core.Vogen.Data.VogenRes.resources"
if ($vogen) { foreach ($key in $vogen.Keys) { if ($vogen[$key].Length -gt 0) { $problems.Add("Vogen data $key is not empty") } } }
$crepe = Resource-Sizes $core "OpenUtau.Core.Analysis.Crepe.Resources.resources"
if (-not $crepe -or -not $crepe.ContainsKey("tiny")) { $problems.Add("the CREPE model is missing") }

if (-not (Test-Path (Join-Path $HostDir "onnxruntime.dll"))) { $problems.Add("onnxruntime.dll is missing: the English g2p fallback needs it (blt-render-host --g2p-check)") }

$infoPath = Join-Path $HostDir "blt-host-build.json"
if (-not (Test-Path $infoPath)) { $problems.Add("blt-host-build.json is missing") } else {
    $info = Get-Content $infoPath -Raw | ConvertFrom-Json
    $actual = (Get-FileHash (Join-Path $HostDir "worldline.dll") -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $info.worldline_sha256) { $problems.Add("worldline.dll does not match blt-host-build.json") }
    if (-not $AllowStockWorldline -and $info.worldline -notlike "BLT build*") { $problems.Add("worldline.dll is not BLT's own build ($($info.worldline))") }
}

if ($problems.Count) {
    $problems | ForEach-Object { Write-Output "FAIL: $_" }
    exit 1
}
Write-Output "host ok: no Voicevox types, English dictionaries identical to the pinned source, other dictionaries and Vogen data empty, BLT worldline.dll"
