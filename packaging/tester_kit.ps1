# Assemble the kit that goes to an external acceptance tester (nothing is uploaded or sent).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging\tester_kit.ps1 [-Artifacts DIR] [-App DIR] [-Out DIR]
#
# The kit holds the installer under test, a second installer of the SAME program with the next version number (so that
# the upgrade path can be tested), checksums, the instructions (docs\acceptance) and two helper scripts. The installers
# stay NOT FOR RELEASE; give the checksums to the tester in a message of their own, not only in the kit.
param(
    [string]$Artifacts = "",
    [string]$App = "",
    [string]$Out = ""
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$release = Join-Path $root "research-output\release"
if (-not $Artifacts) { $Artifacts = Join-Path $release "artifacts" }
if (-not $App) { $App = Join-Path $release "app\BLT Music Generator" }
if (-not $Out) { $Out = Join-Path $release "tester-kit" }
$python = if ($env:BLT_PYTHON) { $env:BLT_PYTHON } elseif (Test-Path (Join-Path $root ".venv\Scripts\python.exe")) { Join-Path $root ".venv\Scripts\python.exe" } else { "python" }

$installer = Get-ChildItem $Artifacts -Filter "BLT-Music-Generator-*-Setup.exe" | Select-Object -First 1
if (-not $installer) { throw "no installer in $Artifacts (run packaging\build.ps1 first)" }
$version = $installer.Name -replace "^BLT-Music-Generator-", "" -replace "-Setup\.exe$", ""
$parts = $version.Split(".")
$next = "$($parts[0]).$($parts[1]).$([int]$parts[2] + 1)"

if (Test-Path $Out) { & $python -c "import shutil,sys; shutil.rmtree(sys.argv[1])" $Out }
New-Item -ItemType Directory -Force $Out | Out-Null
Copy-Item $installer.FullName $Out

# the same payload under the next version number
$iscc = @($env:BLT_ISCC, "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found (BLT_ISCC)" }
$renamed = @(& $python (Join-Path $root "packaging\runtime_copies.py") $App)
$required = (& $python -c "from barbershop_tracks.core.runtime.vcruntime import REQUIRED; print(*REQUIRED)").Trim().Split(" ")
$defines = @("/Qp", "/DAppVersion=$next", "/DSourceDir=$App", "/DOutputDir=$Out", "/DVcMajor=$($required[0])", "/DVcMinor=$($required[1])", "/DVcBuild=$($required[2])")
if ($renamed.Count -eq 1) { $defines += "/DNumpyMsvcp=$($renamed[0])" }
& $iscc @defines (Join-Path $root "packaging\installer.iss") | Out-Null
if ($LASTEXITCODE -ne 0) { throw "the upgrade-test installer could not be built" }

foreach ($script in "Collect-Environment.ps1", "Check-UserData.ps1", "Check-Outputs.ps1") { Copy-Item (Join-Path $root "packaging\tester-kit\$script") $Out }
foreach ($doc in "HANDOFF.md", "english-voicebank-acceptance.md", "clean-machine-verification.md") { Copy-Item (Join-Path $root "docs\acceptance\$doc") $Out }
# the three English scores of the pronunciation test (known / unknown / respelled words) and the list of their words
$scores = Join-Path $Out "scores"
New-Item -ItemType Directory -Force $scores | Out-Null
Get-ChildItem (Join-Path $root "docs\acceptance\fixtures") -File | ForEach-Object { Copy-Item $_.FullName $scores }
@"
BLT Music Generator: release-candidate tester kit. NOT FOR RELEASE: do not share.
Start with HANDOFF.md. Check the installers' SHA-256 against the numbers in the developer's message
(Get-FileHash <file> -Algorithm SHA256) before running anything.
BLT-Music-Generator-$next-Setup.exe is the same program with a higher version number, for the upgrade check only.
This build has NO pronunciation model: a word that the English dictionary lacks stops generation and is named (scores\
holds a score with such words, the same score with them respelled, and sample pronunciations for it: BLT lets a person
say how such a word is sung without changing the score). Check-Outputs.ps1 checks the 13 tracks with arithmetic;
the listening is yours.
"@ | Set-Content (Join-Path $Out "README.txt") -Encoding ascii
$sums = Get-ChildItem $Out -Filter "*-Setup.exe" | Sort-Object Name | ForEach-Object { "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()) *$($_.Name)" }
Set-Content (Join-Path $Out "SHA256SUMS.txt") $sums -Encoding ascii
Write-Output "tester kit: $Out"
$sums | ForEach-Object { Write-Output "  $_" }
Write-Output "send these checksums in a message of their own; nothing was uploaded or sent"
