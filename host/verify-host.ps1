# Check what the built host really contains (it is a patched build of OpenUtau, so trust nothing).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File host\verify-host.ps1 -HostDir DIR -OpenUtauSrc DIR
#
# Reads OpenUtau.Core.dll and OpenUtau.Plugin.Builtin.dll with reflection (no code of theirs runs) and
# fails unless:
#   * no type of either assembly belongs to the Voicevox classes (derived from the LGPL VOICEVOX engine);
#   * the embedded English dictionary (dict.txt, phones.txt) is byte-identical to the pinned OpenUtau's
#     g2p-arpabet (= CMUdict 0.07) and its neural model (g2p.onnx) is either identical to the pinned one
#     or, in the model-free build (the default; the research build is made with -IncludeG2pModel), absent (blt-host-build.json says which); the English "plus" dictionary (unverified origin) and everything that only serves it
#     (Arpasing+, English C+V and their template) are absent, and every other g2p pack and every Vogen
#     data file is empty;
#   (packaging/verify_absent_data.py is the byte-level companion: it searches for the removed data itself)
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
function Zip-Members($bytes) {
    Add-Type -AssemblyName System.IO.Compression
    $archive = New-Object System.IO.Compression.ZipArchive((New-Object System.IO.MemoryStream(,$bytes)))
    $members = @{}
    foreach ($entry in $archive.Entries) {
        $copy = New-Object System.IO.MemoryStream
        $stream = $entry.Open(); $stream.CopyTo($copy); $stream.Dispose()
        $members[$entry.FullName] = Sha ($copy.ToArray())
    }
    return $members
}
function Sha($bytes) { $sha = [System.Security.Cryptography.SHA256]::Create(); ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace "-", "").ToLower() }

$core = Join-Path $HostDir "OpenUtau.Core.dll"
$builtin = Join-Path $HostDir "OpenUtau.Plugin.Builtin.dll"
# Windows PowerShell 5.1 cannot load .NET 8 assemblies for reflection, so the type checks below can see nothing there;
# the names of the removed classes are also searched as bytes in the assemblies' metadata, which needs no loading.
$latin1 = [System.Text.Encoding]::GetEncoding(28591)
foreach ($dll in $core, $builtin) {
    $text = $latin1.GetString([System.IO.File]::ReadAllBytes($dll))
    $named = [regex]::Match($text, "Voicevox[A-Za-z_]|ArpabetPlus|ArpasingPlus|EnglishCpV|ARPAPlus")
    if ($named.Success) { $problems.Add("$(Split-Path $dll -Leaf) contains the name $($named.Value): the removed Voicevox classes or the English plus code are in the build") }
}
foreach ($dll in $core, $builtin) {
    $voicevox = @(Load-Types $dll | Where-Object { $_.FullName -match "Voicevox" })
    if ($voicevox.Count) { $problems.Add("$(Split-Path $dll -Leaf) still has $($voicevox.Count) Voicevox type(s), e.g. $($voicevox[0].FullName)") }
}

$infoPath = Join-Path $HostDir "blt-host-build.json"
$g2pModel = "included"
if (Test-Path $infoPath) { $recordedModel = (Get-Content $infoPath -Raw | ConvertFrom-Json).g2p_model; if ($recordedModel) { $g2pModel = $recordedModel } }
$g2p = Resource-Sizes $core "OpenUtau.Core.G2p.Data.Resources.resources"
$pinned = Join-Path $OpenUtauSrc "OpenUtau.Core\G2p\Data"
$english = @{ "g2p-arpabet" = "g2p-arpabet.zip" }
if (-not $g2p) { $problems.Add("the g2p resources are missing") } else {
    foreach ($key in $g2p.Keys) {
        if ($english.ContainsKey($key)) {
            $reference = Zip-Members ([System.IO.File]::ReadAllBytes((Join-Path $pinned $english[$key])))
            $built = Zip-Members $g2p[$key]
            foreach ($member in "dict.txt", "phones.txt") {
                if ($built[$member] -ne $reference[$member]) { $problems.Add("$key/$member differs from the pinned OpenUtau's $($english[$key])") }
            }
            if ($g2pModel -eq "excluded") {
                if ($built.ContainsKey("g2p.onnx")) { $problems.Add("$key still has g2p.onnx, but this host was built without the model (blt-host-build.json)") }
            } elseif ($built["g2p.onnx"] -ne $reference["g2p.onnx"]) {
                $problems.Add("$key/g2p.onnx differs from the pinned OpenUtau's")
            }
            $extra = @($built.Keys | Where-Object { $_ -notin "dict.txt", "phones.txt", "g2p.onnx" })
            if ($extra.Count) { $problems.Add("$key has unexpected members: $($extra -join ', ')") }
        } elseif ($key -match "plus") {
            $problems.Add("the English 'plus' dictionary ($key) is in the build: its origin is unverified (docs/g2p-plus-provenance.md)")
        } elseif ($g2p[$key].Length -gt 64) {
            $problems.Add("g2p pack $key is not empty ($($g2p[$key].Length) bytes)")
        }
    }
    foreach ($key in $english.Keys) { if (-not $g2p.ContainsKey($key)) { $problems.Add("English dictionary $key is missing") } }
}
# the phonemizers that only exist for the plus dictionary and the English C+V template are not offered
foreach ($dll in $core, $builtin) {
    $plus = @(Load-Types $dll | Where-Object { $_.FullName -match "ArpabetPlus|ArpasingPlus|EnglishCpV|ARPAPlus" })
    if ($plus.Count) { $problems.Add("$(Split-Path $dll -Leaf) still has $($plus[0].FullName) (needs the unverified English 'plus' data)") }
}
$builtinData = Resource-Sizes $builtin "OpenUtau.Plugin.Builtin.Data.Resources.resources"
if ($builtinData -and $builtinData.ContainsKey("en_cPv_template")) { $problems.Add("the English C+V template is in the build (omitted with the plus dictionary)") }
$vogen = Resource-Sizes $core "OpenUtau.Core.Vogen.Data.VogenRes.resources"
if ($vogen) { foreach ($key in $vogen.Keys) { if ($vogen[$key].Length -gt 0) { $problems.Add("Vogen data $key is not empty") } } }
$crepe = Resource-Sizes $core "OpenUtau.Core.Analysis.Crepe.Resources.resources"
if (-not $crepe -or -not $crepe.ContainsKey("tiny")) { $problems.Add("the CREPE model is missing") }

# published host: beside the exe; a plain `dotnet build` (CI's dev host) keeps it under runtimes/win-x64/native
$hasRuntime = (Test-Path (Join-Path $HostDir "onnxruntime.dll")) -or (Test-Path (Join-Path $HostDir "runtimes/win-x64/native/onnxruntime.dll"))
if ($g2pModel -eq "excluded") {
    if ($hasRuntime -and (Test-Path (Join-Path $HostDir "onnxruntime.dll"))) { $problems.Add("onnxruntime.dll is shipped although the host has no g2p model to run on it") }
} elseif (-not $hasRuntime) { $problems.Add("onnxruntime.dll is missing: the English g2p fallback needs it (blt-render-host --g2p-check)") }

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
Write-Output "host ok (g2p model $g2pModel): no Voicevox types, CMUdict pack identical to the pinned source, no English plus dictionary or Arpasing+/English C+V, other dictionaries and Vogen data empty, BLT worldline.dll"
