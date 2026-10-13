# Build the Windows package and installer of BLT Music Generator.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build.ps1 [options]
#
# Steps: publish the self-contained render host (pinned OpenUtau) -> PyInstaller one-folder app ->
# copy the host beside it -> write NOTICES.txt / licenses\ -> audit every file against
# packaging\components.json -> smoke-test the package -> Inno Setup installer -> SHA-256 and release
# metadata. Everything is written under -OutDir (default research-output\release, git-ignored).
# Nothing is uploaded or published anywhere.
#
# Needs: the Python environment from packaging\requirements-build.txt (BLT_PYTHON, .venv, or python on
# PATH), a .NET 8 SDK (host\build.ps1 finds it), Inno Setup 6 for the installer (BLT_ISCC, PATH, or
# its default install folder).
#
# Options:
#   -OpenUtauSrc DIR   the pinned OpenUtau checkout (default: host\build.ps1's, cloned on demand)
#   -OutDir DIR        output root
#   -SkipHost          reuse the host published by an earlier run
#   -NoSmoke           skip the packaged-app smoke tests
#   -NoInstaller       stop after the package folder (no Inno Setup needed)
#   -FailOnBlockers    exit non-zero when the licence audit has open release blockers
param(
    [string]$OpenUtauSrc = "",
    [string]$OutDir = "",
    [switch]$SkipHost,
    [switch]$NoSmoke,
    [switch]$NoInstaller,
    [switch]$FailOnBlockers
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root   # never run from inside the output folders: that locks them against rebuilds
if (-not $OutDir) { $OutDir = Join-Path $root "research-output\release" }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path
$work = Join-Path $OutDir "work"
$hostOut = Join-Path $OutDir "host"
$distRoot = Join-Path $OutDir "app"
$artifacts = Join-Path $OutDir "artifacts"
$app = Join-Path $distRoot "BLT Music Generator"

function Step($text) { Write-Output ""; Write-Output "== $text" }
function Run {
    param([string]$Exe, [string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"   # PyInstaller and others log to stderr; only the exit code matters
    try { & $Exe @Arguments } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed with exit code $LASTEXITCODE" }
}

$version = (Select-String -Path (Join-Path $root "src\barbershop_tracks\__init__.py") -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$python = if ($env:BLT_PYTHON) { $env:BLT_PYTHON } elseif (Test-Path (Join-Path $root ".venv\Scripts\python.exe")) { Join-Path $root ".venv\Scripts\python.exe" } else { "python" }
$commit = (git -C $root rev-parse HEAD).Trim()
$dirty = [bool](git -C $root status --porcelain --untracked-files=no)   # tracked files only
$env:SOURCE_DATE_EPOCH = (git -C $root log -1 --format=%ct).Trim()   # PyInstaller honours it for its archives
$localNuget = Join-Path $root "research-output\spike\nuget"
if (-not $env:NUGET_PACKAGES -and (Test-Path $localNuget)) { $env:NUGET_PACKAGES = $localNuget }
$nuget = if ($env:NUGET_PACKAGES) { $env:NUGET_PACKAGES } else { Join-Path $HOME ".nuget\packages" }
Write-Output "BLT Music Generator $version, commit $commit$(if ($dirty) { ' (working tree has uncommitted changes)' })"

# 1. the render host --------------------------------------------------------------------------
if (-not $SkipHost) {
    Step "Publishing the self-contained render host"
    $hostArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "host\build.ps1"), "-Publish", "-Out", $hostOut)
    if ($OpenUtauSrc) { $hostArgs += @("-OpenUtauSrc", $OpenUtauSrc) }
    Run "powershell" $hostArgs
}
if (-not (Test-Path (Join-Path $hostOut "blt-render-host.exe"))) { throw "no published host in $hostOut (run without -SkipHost)" }
Step "Verifying what the host contains"
$pinnedSource = if ($OpenUtauSrc) { $OpenUtauSrc } else { Join-Path $root "research-output\openutau-src" }
Run "powershell" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "host\verify-host.ps1"), "-HostDir", $hostOut, "-OpenUtauSrc", $pinnedSource)

# 2. the Python application ----------------------------------------------------------------------
Step "Freezing the application with PyInstaller"
Run $python @("packaging\make_version_info.py")
if (Test-Path $distRoot) { Run $python @("-c", "import shutil,sys; shutil.rmtree(sys.argv[1])", $distRoot) }
Run $python @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $distRoot, "--workpath", $work, "packaging\blt.spec")

# 3. the host beside it -----------------------------------------------------------------------------
Step "Adding the render host"
robocopy $hostOut (Join-Path $app "host") /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
$global:LASTEXITCODE = 0

# 3b. the Microsoft runtime is required of the user's PC, never shipped ---------------------------------
Step "Checking that no Microsoft runtime files are in the package"
$hashedCopies = @(& $python "packaging/runtime_copies.py" $app)
if ($LASTEXITCODE -ne 0) { throw "runtime_copies.py failed" }
Run $python (@("packaging/runtime_copies.py", $app, "--check") + $hashedCopies)
$vcRequired = (& $python -c "from barbershop_tracks.core.runtime.vcruntime import REQUIRED; print(*REQUIRED)").Trim().Split(" ")
Write-Output "requires Microsoft Visual C++ runtime $($vcRequired -join '.') or newer; renamed imports satisfied at install: $($hashedCopies -join ', ')"

# 4. notices and the audit ------------------------------------------------------------------------
Step "Writing NOTICES.txt and licenses"
$noticeArgs = @("packaging\notices.py", "bundle", "--out", $app, "--nuget", $nuget)
if ($OpenUtauSrc) { $noticeArgs += @("--openutau-src", $OpenUtauSrc) }
Run $python $noticeArgs

Step "Auditing every file of the package against packaging\components.json"
New-Item -ItemType Directory -Force $artifacts | Out-Null
$components = Get-Content (Join-Path $root "packaging\components.json") -Raw | ConvertFrom-Json
$runtimeVersion = (($components.components | Where-Object { $_.id -eq "dotnet-runtime" }).version -split " ")[0]
$runtimePack = Join-Path $nuget "microsoft.netcore.app.runtime.win-x64\$runtimeVersion\runtimes\win-x64"
$inventoryArgs = @("packaging\inventory.py", $app, "--runtime-pack", $runtimePack, "--deps-json", (Join-Path $hostOut "blt-render-host.deps.json"), "--out", (Join-Path $artifacts "inventory.json"))
if ($FailOnBlockers) { $inventoryArgs += "--fail-on-blockers" }
Run $python $inventoryArgs
$blockers = @($components.components | Where-Object { $_.status -eq "blocker" } | ForEach-Object { $_.id })

# 5. smoke tests of the package --------------------------------------------------------------------
if (-not $NoSmoke) {
    Step "Smoke-testing the package"
    Run "powershell" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "packaging\smoke.ps1"), "-App", $app, "-RuntimeCopies", ($hashedCopies -join ";"))
    Step "Checking that the Qt libraries are replaceable (LGPL)"
    Run "powershell" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "packaging/replaceability-test.ps1"), "-App", $app, "-RuntimeCopies", ($hashedCopies -join ";"))
}

# 5b. the Qt/PySide6 corresponding-source bundle (prepared only; attaching it to the GitHub release is manual) ----
Step "Preparing the corresponding-source bundle (not uploaded)"
Run $python @("packaging/compliance.py", "--out", (Join-Path $OutDir "compliance"), "--version", $version)

# 6. the installer ----------------------------------------------------------------------------------------
$installer = $null
if (-not $NoInstaller) {
    Step "Building the installer"
    $iscc = @($env:BLT_ISCC, (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source,
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $iscc) { throw "Inno Setup 6 not found (install it, or set BLT_ISCC; or use -NoInstaller)" }
    $isccArgs = @("/Qp", "/DAppVersion=$version", "/DSourceDir=$app", "/DOutputDir=$artifacts", "/DVcMajor=$($vcRequired[0])", "/DVcMinor=$($vcRequired[1])", "/DVcBuild=$($vcRequired[2])")
    if ($hashedCopies.Count -eq 1) { $isccArgs += "/DNumpyMsvcp=$($hashedCopies[0])" } elseif ($hashedCopies.Count -gt 1) { throw "the installer handles one renamed runtime copy, found $($hashedCopies.Count)" }
    Run $iscc ($isccArgs + (Join-Path $root "packaging\installer.iss"))
    $installer = Join-Path $artifacts "BLT-Music-Generator-$version-Setup.exe"
    if (-not (Test-Path $installer)) { throw "installer was not produced" }
}

# 7. checksums and release metadata --------------------------------------------------------------------
Step "Checksums and metadata"
Copy-Item (Join-Path $app "NOTICES.txt") (Join-Path $artifacts "NOTICES.txt") -Force
$status = if ($blockers.Count) { "NOT FOR RELEASE: $($blockers.Count) open licensing blocker(s): $($blockers -join ', '). See docs/dependency-audit.md." } else { "No open licensing blockers recorded." }
$utf8 = New-Object System.Text.UTF8Encoding($false)   # no byte-order mark
[System.IO.File]::WriteAllText((Join-Path $artifacts "RELEASE-STATUS.txt"), $status, $utf8)
$sums = @()
foreach ($file in @($installer, (Join-Path $artifacts "NOTICES.txt"), (Join-Path $artifacts "inventory.json")) | Where-Object { $_ }) {
    $sums += "$((Get-FileHash $file -Algorithm SHA256).Hash.ToLower()) *$(Split-Path $file -Leaf)"
}
Set-Content (Join-Path $artifacts "SHA256SUMS.txt") $sums -Encoding ascii
$info = [ordered]@{
    product = "BLT Music Generator"; version = $version; commit = $commit; uncommitted_changes = $dirty
    openutau = "0.1.565 a60ca5830b9064556157245d4bf8f5920d93e5f8"; dotnet_runtime = $runtimeVersion
    python = (& $python --version); pyinstaller = ((& $python -m pip show pyinstaller | Select-String "^Version").ToString() -replace "Version: ", "")
    installer = if ($installer) { Split-Path $installer -Leaf } else { $null }
    installer_bytes = if ($installer) { (Get-Item $installer).Length } else { $null }
    signed = $false; release_blockers = $blockers; status = $status
}
[System.IO.File]::WriteAllText((Join-Path $artifacts "release-info.json"), ($info | ConvertTo-Json), $utf8)
Get-Content (Join-Path $artifacts "SHA256SUMS.txt")
Write-Output ""
Write-Output $status
Write-Output "Package:   $app"
if ($installer) { Write-Output "Installer: $installer ($([math]::Round((Get-Item $installer).Length / 1MB, 1)) MB, unsigned)" }
