# Measure which tension values the supported render paths pass to worldline's tension effect.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File host\native\trace_tension.ps1 [-HostDir DIR] [-Work DIR]
#
# BLT's worldline build has no tension effect (GetTensionCoefficients returns the neutral envelope), which is only
# equivalent to the original if every supported render asks for tension 0. This builds a THROW-AWAY copy of
# worldline.dll whose GetTensionCoefficients first appends "value fs f0 width" to the file named by the environment
# variable BLT_TENSION_TRACE, runs the whole integration test suite (selftest, host contract tests, full pipeline)
# against a copy of the host that uses it, and reports every distinct tension value seen. The instrumented DLL is
# never part of a package. Needs the work folder of an earlier host\native\build.ps1 run (-Work) and a published host
# (-HostDir); takes about five minutes.
param(
    [string]$HostDir = "",
    [string]$Work = ""
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $HostDir) { $HostDir = Join-Path $root "research-output\release\host" }
if (-not $Work) { $Work = Join-Path $root "research-output\host\native-work" }
$python = if ($env:BLT_PYTHON) { $env:BLT_PYTHON } elseif (Test-Path (Join-Path $root ".venv\Scripts\python.exe")) { Join-Path $root ".venv\Scripts\python.exe" } else { "python" }
$effects = Join-Path $Work "patched\worldline\model\effects.cpp"
if (-not (Test-Path $effects)) { throw "$effects not found: run host\native\build.ps1 first" }

# instrument a copy of the work folder's effects.cpp, never the original
$scratch = Join-Path $env:TEMP ("blt-tension-trace-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force $scratch | Out-Null
$original = [System.IO.File]::ReadAllText($effects)
$needle = "std::vector<double> GetTensionCoefficients(double f0, int fs, int value,"
$at = $original.IndexOf($needle)
if ($at -lt 0) { throw "GetTensionCoefficients not found in $effects" }
$brace = $original.IndexOf("{", $at)
$probe = "`n  { const char* p = std::getenv(`"BLT_TENSION_TRACE`"); if (p) { FILE* f = std::fopen(p, `"a`"); if (f) { std::fprintf(f, `"%d %d %.3f %d\n`", value, fs, f0, width); std::fclose(f); } } }`n"
$instrumented = "#include <cstdio>`n#include <cstdlib>`n" + $original.Substring(0, $brace + 1) + $probe + $original.Substring($brace + 1)
try {
    [System.IO.File]::WriteAllText($effects, $instrumented)
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    $vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1
    $bat = Join-Path $scratch "build.bat"
    "@echo off`r`ncall `"$vs\VC\Auxiliary\Build\vcvars64.bat`" >nul 2>&1`r`ncd /d `"$Work`"`r`ncmake --build build --target worldline > `"$scratch\build.log`" 2>&1 || (type `"$scratch\build.log`" & exit /b 1)" | Set-Content $bat -Encoding ascii
    cmd /c $bat
    if ($LASTEXITCODE -ne 0) { throw "the instrumented build failed" }
    $traceHost = Join-Path $scratch "host"
    Copy-Item $HostDir $traceHost -Recurse
    Copy-Item (Join-Path $Work "build\worldline.dll") (Join-Path $traceHost "worldline.dll") -Force
}
finally {
    [System.IO.File]::WriteAllText($effects, $original)   # leave the work folder as it was
    # rebuild the real DLL in the work folder so that it is not left instrumented
    if ($vs) { $bat2 = Join-Path $scratch "rebuild.bat"; "@echo off`r`ncall `"$vs\VC\Auxiliary\Build\vcvars64.bat`" >nul 2>&1`r`ncd /d `"$Work`"`r`ncmake --build build --target worldline > nul 2>&1" | Set-Content $bat2 -Encoding ascii; cmd /c $bat2 }
}

$traceFile = Join-Path $scratch "trace.txt"
$env:BLT_HOST_DIR = $traceHost
$env:BLT_HOST_SELF_CONTAINED = "1"
$env:BLT_TENSION_TRACE = $traceFile
Push-Location $root
try { & $python -m pytest tests/integration -q -p no:cacheprovider 2>&1 | Select-Object -Last 3 } finally { Pop-Location }
$lines = @(Get-Content $traceFile -ErrorAction SilentlyContinue)
Write-Output "GetTensionCoefficients was called $($lines.Count) times"
$groups = $lines | ForEach-Object { ($_ -split " ")[0] } | Group-Object
foreach ($g in $groups) { Write-Output "  tension value $($g.Name): $($g.Count) calls" }
if ($lines.Count -eq 0) { throw "the trace is empty: the instrumented DLL was not used" }
if (($groups | Where-Object { $_.Name -ne "0" })) { throw "a supported render path asked for a tension other than 0" }
Write-Output "ok: every call asked for tension 0"
cmd /c rmdir /s /q "$scratch" 2>$null | Out-Null
