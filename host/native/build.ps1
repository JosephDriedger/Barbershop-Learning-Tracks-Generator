# Build BLT's own worldline.dll (OpenUtau's native resampler) from the pinned sources, without any spline,
# and check it. See docs/worldline-provenance.md.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File host\native\build.ps1 -OpenUtauSrc DIR -Out DIR
#
# Steps: prepare the pinned third-party sources (SHA-256 checked) and BLT's patch; build with MSVC and
# CMake (/Brepro: the same sources give the same bytes); check that neither the link map nor the DLL mentions a
# spline (the GPL tk::spline of the original, or any replacement) and that the exports are the ones
# OpenUtau.Core calls; run the native test of the tension effect (the neutral envelope). Needs the MSVC C++ build
# tools (Visual Studio or its Build Tools), CMake and Ninja (both come with the Visual Studio C++ workload), git,
# Python.
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
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release > configure.log 2>&1 || (type configure.log & exit /b 1)
cmake --build build --target worldline > build.log 2>&1 || (type build.log & exit /b 1)
"@ | Set-Content $script -Encoding ascii
cmd /c $script
if ($LASTEXITCODE -ne 0) { throw "the worldline build failed (see $Work\configure.log and build.log)" }

& $python (Join-Path $PSScriptRoot "verify_dll.py") (Join-Path $build "worldline.dll") (Join-Path $build "worldline.map")
if ($LASTEXITCODE -ne 0) { throw "the built worldline.dll failed its checks" }

# the tension effect: the product's effects.cpp compiled on its own and run over a grid of inputs
$tests = Join-Path $Work "tests"
New-Item -ItemType Directory -Force $tests | Out-Null
Copy-Item (Join-Path $PSScriptRoot "tests\tension_test.cpp") $tests -Force
$wl = Join-Path $Work "worldline-src\cpp"
@"
@echo off
call "$vcvars" >nul 2>&1
cd /d "$tests"
cl /nologo /O2 /EHsc /std:c++17 /DNOMINMAX /I"$wl" /I"$wl\worldline\model" tension_test.cpp "$Work\patched\worldline\model\effects.cpp" /Fe:tension_test.exe > tension.log 2>&1 || (type tension.log & exit /b 1)
"%CD%\tension_test.exe"
"@ | Set-Content (Join-Path $tests "run.bat") -Encoding ascii
cmd /c (Join-Path $tests "run.bat")
if ($LASTEXITCODE -ne 0) { throw "the native tension test failed" }

New-Item -ItemType Directory -Force $Out | Out-Null
Copy-Item (Join-Path $build "worldline.dll") (Join-Path $Out "worldline.dll") -Force
Write-Output "worldline.dll: $(Join-Path $Out 'worldline.dll') sha256 $((Get-FileHash (Join-Path $Out 'worldline.dll') -Algorithm SHA256).Hash.ToLower())"
