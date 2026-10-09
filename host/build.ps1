# Build the BLT render host against the PINNED OpenUtau source.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File host\build.ps1 [-OpenUtauSrc DIR] [-Out DIR]
#
# Pin: OpenUtau release 0.1.565, commit a60ca5830b9064556157245d4bf8f5920d93e5f8. If the source
# directory is missing it is cloned at that tag; either way HEAD must equal the pinned commit or the
# build stops. Requires a .NET 8 (or newer) SDK: DOTNET_ROOT if set, else the local research SDK if
# present, else `dotnet` on PATH. Output and the OpenUtau checkout live under research-output\ (git-ignored).
param(
    [string]$OpenUtauSrc = "",
    [string]$Out = ""
)
$ErrorActionPreference = "Stop"
$Tag = "0.1.565"
$Commit = "a60ca5830b9064556157245d4bf8f5920d93e5f8"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $OpenUtauSrc) { $OpenUtauSrc = Join-Path $root "research-output\openutau-src" }
if (-not $Out) { $Out = Join-Path $root "research-output\host\build" }

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

New-Item -ItemType Directory -Force $Out | Out-Null
$Out = (Resolve-Path $Out).Path
$project = Join-Path $PSScriptRoot "BltRenderHost\BltRenderHost.csproj"
dotnet build $project -c Release -o $Out "-p:OpenUtauSrc=$OpenUtauSrc" "-p:OpenUtauCommit=$Commit" 2>&1 |
    Select-String -Pattern "error|warn.*BltRenderHost|Build succeeded|Elapsed"
if ($LASTEXITCODE -ne 0) { throw "build failed" }
if (-not (Test-Path (Join-Path $Out "blt-render-host.exe"))) { throw "no host produced in $Out" }
Write-Output "host: $(Join-Path $Out 'blt-render-host.exe')"
