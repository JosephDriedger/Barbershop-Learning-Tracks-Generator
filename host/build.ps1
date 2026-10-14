# Build the BLT render host against the PINNED OpenUtau source.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File host\build.ps1 [-OpenUtauSrc DIR] [-Out DIR] [-Publish] [-SkipNative] [-ExcludeG2pModel]
#
# Pin: OpenUtau release 0.1.565, commit a60ca5830b9064556157245d4bf8f5920d93e5f8. If the source
# directory is missing it is cloned at that tag; either way HEAD must equal the pinned commit or the
# build stops. The host is NOT built from the pinned tree itself but from a copy that host\patch_openutau.py
# changes in a documented way: no Voicevox classes (LGPL-derived), no Vogen data, no non-English
# dictionaries (see docs\m13-compliance.md). The native worldline.dll is BLT's own build
# (host\native\build.ps1: the same sources without any spline) unless -SkipNative, which keeps
# OpenUtau's stock DLL for quick local runs only (never for a package).
# -ExcludeG2pModel builds the variant without the English pack's neural g2p model (g2p.onnx) and without the
# native onnxruntime.dll that exists only to run it (docs/g2p-model-provenance.md); it writes to publish-nog2p.
# Requires a .NET 8 (or newer) SDK: DOTNET_ROOT if set, else the local research SDK if present, else
# `dotnet` on PATH. Output and the OpenUtau checkout live under research-output\ (git-ignored).
param(
    [string]$OpenUtauSrc = "",
    [string]$Out = "",
    # -Publish: the shipped form. Self-contained win-x64 (needs no .NET on the user's PC), then pruned
    # with host\prune.txt. Without it: the framework-dependent development build.
    [switch]$Publish,
    [switch]$SkipNative,
    # the variant of M17: no g2p.onnx (words outside CMUdict get no neural guess), no native onnxruntime.dll
    [switch]$ExcludeG2pModel
)
$ErrorActionPreference = "Stop"
$Tag = "0.1.565"
$Commit = "a60ca5830b9064556157245d4bf8f5920d93e5f8"
# What the host reports as its OpenUtau revision: the pinned commit plus the fact that it was patched.
$BuildCommit = "$Commit+blt-patched"
# The .NET runtime bundled into the self-contained host. Pinned so that a newer SDK cannot silently bundle
# a different runtime than the one packaging/components.json audits (the build fails on a mismatch).
$RuntimeVersion = "8.0.31"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OpenUtauSrc) { $OpenUtauSrc = Join-Path $root "research-output\openutau-src" }
if (-not $Out) {
    $Out = Join-Path $root ("research-output\host\" + $(if ($Publish) { "publish" } else { "build" }) + $(if ($ExcludeG2pModel) { "-nog2p" } else { "" }))
}
$python = if ($env:BLT_PYTHON) { $env:BLT_PYTHON } elseif (Test-Path (Join-Path $root ".venv\Scripts\python.exe")) { Join-Path $root ".venv\Scripts\python.exe" } else { "python" }

if (-not (Test-Path (Join-Path $OpenUtauSrc "OpenUtau.sln"))) {
    git clone --branch $Tag --depth 1 https://github.com/stakira/OpenUtau.git $OpenUtauSrc
    if ($LASTEXITCODE -ne 0) { throw "clone failed" }
}
$OpenUtauSrc = (Resolve-Path $OpenUtauSrc).Path
$head = (git -C $OpenUtauSrc rev-parse HEAD).Trim()
if ($head -ne $Commit) { throw "OpenUtau source is at $head, expected the pinned $Commit" }

$localSdk = Join-Path $root "research-output\spike\dotnet"
if (-not $env:DOTNET_ROOT -and (Test-Path $localSdk)) { $env:DOTNET_ROOT = $localSdk }
if ($env:DOTNET_ROOT) { $env:PATH = "$env:DOTNET_ROOT;$env:PATH" }
$env:DOTNET_CLI_TELEMETRY_OPTOUT = "1"
$env:DOTNET_NOLOGO = "1"
$nuget = Join-Path $root "research-output\spike\nuget"
if (-not $env:NUGET_PACKAGES -and (Test-Path $nuget)) { $env:NUGET_PACKAGES = $nuget }

# the patched copy of the pinned source (the pinned checkout itself is never modified)
$patched = Join-Path $root ("research-output\host\openutau-patched" + $(if ($ExcludeG2pModel) { "-nog2p" } else { "" }))
if (Test-Path $patched) { & $python -c "import shutil,sys; shutil.rmtree(sys.argv[1])" $patched }
New-Item -ItemType Directory -Force (Split-Path $patched) | Out-Null
$patchArgs = @($OpenUtauSrc, $patched)
if ($ExcludeG2pModel) { $patchArgs += "--exclude-g2p-model" }
& $python (Join-Path $PSScriptRoot "patch_openutau.py") @patchArgs
if ($LASTEXITCODE -ne 0) { throw "patching the OpenUtau copy failed" }

New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
$project = Join-Path $PSScriptRoot "BltRenderHost\BltRenderHost.csproj"
if ($Publish) {
    if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
    dotnet publish $project -c Release -r win-x64 --self-contained true -o $Out "-p:OpenUtauSrc=$patched" "-p:OpenUtauCommit=$BuildCommit" -p:DebugType=none -p:DebugSymbols=false "-p:RuntimeFrameworkVersion=$RuntimeVersion" 2>&1 |
        Select-String -Pattern "error|Build succeeded|Elapsed"
    if ($LASTEXITCODE -ne 0) { throw "publish failed" }
    foreach ($line in Get-Content (Join-Path $PSScriptRoot "prune.txt")) {
        $name = $line.Trim()
        if ($name -and -not $name.StartsWith("#")) { Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Out $name) }
    }
    if ($ExcludeG2pModel) {
        # nothing runs a neural model any more: the native runtime (and its third-party notices) is not shipped
        foreach ($name in "onnxruntime.dll", "onnxruntime_providers_shared.dll", "DirectML.dll") {
            Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Out $name)
        }
    }
} else {
    dotnet build $project -c Release -o $Out "-p:OpenUtauSrc=$patched" "-p:OpenUtauCommit=$BuildCommit" 2>&1 |
        Select-String -Pattern "error|warn.*BltRenderHost|Build succeeded|Elapsed"
    if ($LASTEXITCODE -ne 0) { throw "build failed" }
}
if (-not (Test-Path (Join-Path $Out "blt-render-host.exe"))) { throw "no host produced in $Out" }

# BLT's own worldline.dll replaces OpenUtau's prebuilt one (which contains GPL code)
$native = "stock (OpenUtau's prebuilt DLL: contains GPL tk::spline; not for packages)"
if (-not $SkipNative) {
    $nativeOut = Join-Path $root "research-output\host\native-out"
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "native\build.ps1") -OpenUtauSrc $OpenUtauSrc -Out $nativeOut
    if ($LASTEXITCODE -ne 0) { throw "the native worldline build failed" }
    Copy-Item (Join-Path $nativeOut "worldline.dll") (Join-Path $Out "worldline.dll") -Force
    $native = "BLT build without any spline"
}
$info = [ordered]@{
    schema = "blt.host-build/1"
    openutau = [ordered]@{ tag = $Tag; commit = $Commit; patched = $true; patch_script = "host/patch_openutau.py" }
    worldline = $native
    worldline_spline_free = ($native -like "BLT build*")   # native\verify_dll.py passed: no spline in the link map or the DLL
    worldline_sha256 = (Get-FileHash (Join-Path $Out "worldline.dll") -Algorithm SHA256).Hash.ToLower()
    dotnet_runtime = $RuntimeVersion
    g2p_model = $(if ($ExcludeG2pModel) { "excluded" } else { "included" })   # the English pack's g2p.onnx (docs/g2p-model-provenance.md)
}
[System.IO.File]::WriteAllText((Join-Path $Out "blt-host-build.json"), ($info | ConvertTo-Json -Depth 4), (New-Object System.Text.UTF8Encoding($false)))
Write-Output "host: $(Join-Path $Out 'blt-render-host.exe')"
