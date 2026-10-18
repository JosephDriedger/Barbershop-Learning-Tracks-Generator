# Prove that the Qt libraries in a built package are separate, replaceable files (LGPL-3.0 section 4(d)(1)).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging/replaceability-test.ps1 -App <folder>
#
# On a private copy of the package folder:
#   1. the GUI starts (offscreen Qt, --smoke-test): the baseline;
#   2. Qt6Widgets.dll is deleted: the GUI must fail, which shows the file is really loaded from disk and
#      is not merged into the executable;
#   3. Qt6Widgets.dll is put back as a *different* file (the original with bytes appended; Windows ignores
#      trailing data in a DLL): the GUI must start again, which shows BLT neither checks nor pins the file.
# That is the mechanism the LGPL asks for. It does not show that a Qt build somebody modified works; the
# package builds only ever contain the unmodified Qt of the PySide6 wheel.
param(
    [Parameter(Mandatory = $true)][string]$App,
    # hash-renamed Microsoft runtime files the package imports (the installer creates them from this PC's own copy)
    [string]$RuntimeCopies = ""
)
$ErrorActionPreference = "Stop"
$App = (Resolve-Path $App).Path
$base = Join-Path $env:TEMP ("blt-relink-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$copy = Join-Path $base "app"
$failures = New-Object System.Collections.Generic.List[string]
function Check($ok, $text) { if ($ok) { Write-Output "  ok    $text" } else { Write-Output "  FAIL  $text"; $failures.Add($text) } }

function Start-Gui {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = Join-Path $copy "BLT Music Generator.exe"
    $info.Arguments = "--smoke-test"
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.EnvironmentVariables["QT_QPA_PLATFORM"] = "offscreen"
    $info.EnvironmentVariables["BLT_DATA_DIR"] = Join-Path $base "data"
    $info.EnvironmentVariables["BLT_CONFIG"] = Join-Path $base "config.json"
    $process = [System.Diagnostics.Process]::Start($info)
    $null = $process.StandardOutput.ReadToEndAsync()
    $null = $process.StandardError.ReadToEndAsync()
    # a windowed exe that cannot load Qt shows a modal error box instead of exiting; treat waiting as failure
    if (-not $process.WaitForExit(45000)) { $process.Kill(); return -1 }
    $process.WaitForExit()
    return $process.ExitCode
}

try {
    robocopy $App $copy /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed" }
    $global:LASTEXITCODE = 0
    foreach ($name in ($RuntimeCopies -split ";" | Where-Object { $_ })) {
        $target = Join-Path $copy "_internal/numpy.libs/$name"
        if (-not (Test-Path -LiteralPath $target)) {
            New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
            Copy-Item -LiteralPath (Join-Path $env:SystemRoot ("System32/" + ($name -replace "-[0-9a-f]{32}", ""))) -Destination $target
        }
    }
    $widgets = Get-ChildItem -LiteralPath $copy -Recurse -Filter "Qt6Widgets.dll" | Select-Object -First 1
    if (-not $widgets) { throw "Qt6Widgets.dll is not a separate file in the package: the LGPL replacement mechanism is missing" }
    Write-Output "Package: $App"
    Write-Output "Library: $($widgets.FullName.Substring($copy.Length + 1))"

    Check ((Start-Gui) -eq 0) "baseline: the GUI starts with the original library"

    $original = $widgets.FullName + ".original"
    Move-Item -LiteralPath $widgets.FullName -Destination $original
    Check ((Start-Gui) -ne 0) "with Qt6Widgets.dll removed the GUI cannot start (the library is loaded from this file)"

    Copy-Item -LiteralPath $original -Destination $widgets.FullName
    $stream = [System.IO.File]::Open($widgets.FullName, [System.IO.FileMode]::Append)
    $stream.Write([byte[]](0x42, 0x4C, 0x54, 0x0A), 0, 4)   # "BLT\n": a different file with the same contents
    $stream.Close()
    $different = (Get-FileHash -LiteralPath $widgets.FullName).Hash -ne (Get-FileHash -LiteralPath $original).Hash
    Check $different "the replacement file differs from the original"
    Check ((Start-Gui) -eq 0) "the GUI starts with the replaced library (no pinning or integrity check in BLT)"
}
finally {
    # Removing the scratch copy is housekeeping: the GUI just closed may hold a file for a moment, so try a
    # few times, and never let a leftover temp folder fail the test (the checks above are the test)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    foreach ($attempt in 1..5) {
        cmd /c rmdir /s /q "$base" 2>&1 | Out-Null
        if (-not (Test-Path -LiteralPath $base)) { break }
        Start-Sleep -Seconds 2
    }
    $ErrorActionPreference = $previous
}
if ($failures.Count) {
    Write-Output "REPLACEABILITY TEST FAILED ($($failures.Count))"
    exit 1
}
Write-Output "replaceability test passed"
