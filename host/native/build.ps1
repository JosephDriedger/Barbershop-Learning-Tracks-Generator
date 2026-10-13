# Build BLT's own worldline.dll (OpenUtau's native resampler) from the pinned sources, without the GPL
# tk::spline, and check it. See docs/worldline-provenance.md.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File host\native\build.ps1 -OpenUtauSrc DIR -Out DIR
#
# Steps: prepare the pinned third-party sources (SHA-256 checked) and BLT's patch; build with MSVC and
# CMake (/Brepro: the same sources give the same bytes); check the link map has no tk::spline symbol and
# the exports are the ones OpenUtau.Core calls; run the spline parity test against the original
# tk::spline (compiled only inside this test, never shipped). Needs the MSVC C++ build tools (Visual Studio
# or its Build Tools), CMake and Ninja (both come with the Visual Studio C++ workload), git, Python.
param(
    [Parameter(Mandatory = $true)][string]$OpenUtauSrc,
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$Work = ""
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $Work) { $Work = Join-Path $root "research-output\host\native-work" }
$python = if ($env:BLT_PYTHON) { $env:BLT_PYTHON } elseif (Test-Path (Join-Path $root ".venv\Scripts\python.exe")) { Join-Path $root ".venv\Scripts\python.exe" } else { "python" }

$vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) { throw "vswhere.exe not found: install Visual Studio or the Build Tools with the C++ workload" }
$vs = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
if (-not $vs) { throw "no Visual Studio with the MSVC x64 tools found" }
$vcvars = Join-Path $vs "VC\Auxiliary\Build\vcvars64.bat"

if (Test-Path $Work) { & $python -c "import shutil,sys; shutil.rmtree(sys.argv[1])" $Work }
& $python (Join-Path $PSScriptRoot "prepare.py") $Work --openutau-src $OpenUtauSrc
if ($LASTEXITCODE -ne 0) { throw "prepare.py failed" }

$build = Join-Path $Work "build"
$script = Join-Path $Work "build.bat"
@"
@echo off
call "$vcvars" >nul 2>&1
cd /d "$Work"
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPATCH_SPLINE=ON > configure.log 2>&1 || (type configure.log & exit /b 1)
cmake --build build --target worldline > build.log 2>&1 || (type build.log & exit /b 1)
"@ | Set-Content $script -Encoding ascii
cmd /c $script
if ($LASTEXITCODE -ne 0) { throw "the worldline build failed (see $Work\configure.log and build.log)" }

& $python (Join-Path $PSScriptRoot "verify_dll.py") (Join-Path $build "worldline.dll") (Join-Path $build "worldline.map")
if ($LASTEXITCODE -ne 0) { throw "the built worldline.dll failed its checks" }

# parity of the replacement spline against the original, in a throw-away harness
$parity = Join-Path $Work "parity"
New-Item -ItemType Directory -Force $parity | Out-Null
Copy-Item (Join-Path $PSScriptRoot "parity\main.cpp") $parity -Force
$wl = Join-Path $Work "worldline-src\cpp"
@"
@echo off
call "$vcvars" >nul 2>&1
cd /d "$parity"
cl /nologo /O2 /EHsc /std:c++17 /DNOMINMAX /I"$wl" /I"$wl\worldline\model" /I"$Work\wl\spline\src" main.cpp "$wl\worldline\model\effects.cpp" /Fe:original.exe > a.log 2>&1 || (type a.log & exit /b 1)
cl /nologo /O2 /EHsc /std:c++17 /DNOMINMAX /I"$wl" /I"$wl\worldline\model" /I"$Work\patched" main.cpp "$Work\patched\worldline\model\effects.cpp" /Fe:blt.exe > b.log 2>&1 || (type b.log & exit /b 1)
"%CD%\original.exe" > original.txt
"%CD%\blt.exe" > blt.txt
"@ | Set-Content (Join-Path $parity "run.bat") -Encoding ascii
cmd /c (Join-Path $parity "run.bat")
if ($LASTEXITCODE -ne 0) { throw "the parity harness failed to build or run" }
& $python (Join-Path $PSScriptRoot "parity\compare.py") (Join-Path $parity "original.txt") (Join-Path $parity "blt.txt")
if ($LASTEXITCODE -ne 0) { throw "the replacement spline differs from tk::spline beyond rounding" }

New-Item -ItemType Directory -Force $Out | Out-Null
Copy-Item (Join-Path $build "worldline.dll") (Join-Path $Out "worldline.dll") -Force
Write-Output "worldline.dll: $(Join-Path $Out 'worldline.dll') sha256 $((Get-FileHash (Join-Path $Out 'worldline.dll') -Algorithm SHA256).Hash.ToLower())"
