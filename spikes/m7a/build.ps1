# M7a spike: build the throwaway render host into the git-ignored research-output directory.
# Requires the local .NET 8 SDK and the pinned OpenUtau checkout under research-output\spike\
# (see spikes\m7a\README.md). Not part of CI.
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$spike = Join-Path $root "research-output\spike"
$env:DOTNET_ROOT = Join-Path $spike "dotnet"
$env:PATH = "$env:DOTNET_ROOT;$env:PATH"
$env:DOTNET_CLI_TELEMETRY_OPTOUT = "1"
$env:DOTNET_NOLOGO = "1"
$env:NUGET_PACKAGES = Join-Path $spike "nuget"
Push-Location (Join-Path $PSScriptRoot "renderhost")
try {
    dotnet build -c Release -o (Join-Path $spike "host-build") 2>&1 | Select-String -Pattern "error|Build succeeded|Elapsed"
} finally { Pop-Location }
# use the per-user data directory (singers installed for OpenUtau) rather than "portable" mode
Set-Content (Join-Path $spike "host-build\installed.txt") "m7a spike: use the per-user data directory"
