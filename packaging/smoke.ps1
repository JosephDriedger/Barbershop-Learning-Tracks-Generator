# Smoke-test a built (or installed) BLT Music Generator folder in a stripped-down environment.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging\smoke.ps1 -App <folder> [-Keep]
#
# Every program runs with an environment that has no Python, no .NET (no DOTNET_ROOT, PATH is only
# the Windows folders), no BLT_* build variables (BLT_HOST_DIR in particular) and no source
# checkout. Two scenarios run: the folder as given with ASCII working folders, and a copy of it under
# a path with spaces and non-ASCII characters (as in a user name such as "Jörg Müller") with the
# data, settings, temp and output folders there too. The checks:
#   * blt --version, and the GUI's own start-up self-check (offscreen Qt);
#   * blt selftest: 13 WAVs and a verified manifest through the bundled host (no BLT_HOST_DIR);
#   * the per-user host runtime copy is created once and a second launch reuses it untouched;
#   * the program folder is not modified by running (no caches, configs or temp files in it).
# This proves the package works without a development environment. It is not a substitute for a
# pristine machine (see docs/m12-verification.md) and says nothing about how real voices sound.
param(
    [Parameter(Mandatory = $true)][string]$App,
    # hash-renamed Microsoft runtime files the package imports; the installer copies this PC's own file under
    # each name, and so does this test (into its private copy of the package, never into $App)
    [string]$RuntimeCopies = "",
    [switch]$Keep
)
$ErrorActionPreference = "Stop"
$App = (Resolve-Path $App).Path
$script:failures = New-Object System.Collections.Generic.List[string]

function Check($ok, $text) {
    if ($ok) { Write-Output "  ok    $text" } else { Write-Output "  FAIL  $text"; $script:failures.Add($text) }
}

# a user-name-like folder with a space and non-ASCII characters, built without literals so the
# script survives any file encoding
$odd = "Jo" + [char]0x00F6 + "rg M" + [char]0x00FC + "ller " + [char]0x65E5 + [char]0x672C
$base = Join-Path $env:TEMP ("blt-smoke-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force $base | Out-Null

function Clean-Environment($profileDir, $data) {
    $windows = $env:SystemRoot
    $table = @{
        SystemRoot = $windows; windir = $windows; SystemDrive = $env:SystemDrive
        ComSpec = "$windows\System32\cmd.exe"; PATHEXT = ".COM;.EXE;.BAT;.CMD"
        PATH = "$windows\System32;$windows"
        TEMP = "$profileDir\Temp"; TMP = "$profileDir\Temp"
        USERPROFILE = $profileDir; APPDATA = "$profileDir\AppData\Roaming"; LOCALAPPDATA = "$profileDir\AppData\Local"
        HOMEDRIVE = $env:SystemDrive; HOMEPATH = "\"; USERNAME = "smoke"; COMPUTERNAME = $env:COMPUTERNAME
        OS = $env:OS; PROCESSOR_ARCHITECTURE = $env:PROCESSOR_ARCHITECTURE; NUMBER_OF_PROCESSORS = $env:NUMBER_OF_PROCESSORS
        BLT_DATA_DIR = $data; BLT_CONFIG = "$profileDir\blt-config.json"
    }
    New-Item -ItemType Directory -Force "$profileDir\Temp", "$profileDir\AppData\Roaming", "$profileDir\AppData\Local" | Out-Null
    return $table
}

function Invoke-Clean {
    param([string]$Exe, [string[]]$Arguments, [hashtable]$Environment, [int]$TimeoutSec = 600)
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Exe
    $info.Arguments = ($Arguments | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join " "
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $info.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $info.CreateNoWindow = $true
    $info.EnvironmentVariables.Clear()
    foreach ($key in $Environment.Keys) { if ($Environment[$key]) { $info.EnvironmentVariables[$key] = [string]$Environment[$key] } }
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $process = [System.Diagnostics.Process]::Start($info)
    $out = $process.StandardOutput.ReadToEndAsync()
    $err = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutSec * 1000)) { $process.Kill(); throw "$Exe did not finish in $TimeoutSec s" }
    $process.WaitForExit()
    return [pscustomobject]@{ ExitCode = $process.ExitCode; Out = $out.Result; Err = $err.Result; Seconds = [math]::Round($watch.Elapsed.TotalSeconds, 1) }
}

function Snapshot($folder) {
    (Get-ChildItem -LiteralPath $folder -Recurse -Force -File | Sort-Object FullName |
        ForEach-Object { "{0}|{1}|{2}" -f $_.FullName, $_.Length, $_.LastWriteTimeUtc.Ticks }) -join "`n"
}

function Scenario($name, $appDir, $profileDir, $data) {
    Write-Output ""
    Write-Output "[$name]"
    Write-Output "  app:  $appDir"
    Write-Output "  data: $data"
    $environment = Clean-Environment $profileDir $data
    $exe = Join-Path $appDir "blt.exe"
    $gui = Join-Path $appDir "BLT Music Generator.exe"
    $before = Snapshot $appDir

    $d = Invoke-Clean $exe @("diagnostics") $environment
    $vcLine = (($d.Out -split "`n") | Where-Object { $_ -match "vc runtime" } | Select-Object -First 1)
    Check ($d.ExitCode -eq 0 -and $d.Out -match "vc runtime:\s+Microsoft Visual C\+\+ [0-9.]+ ok") "blt diagnostics sees Microsoft's Visual C++ runtime ($("$vcLine".Trim()))"

    $v = Invoke-Clean $exe @("--version") $environment
    Check ($v.ExitCode -eq 0 -and $v.Out -match "\d+\.\d+") "blt --version prints a version ($($v.Out.Trim()))"

    $guiEnvironment = $environment.Clone()
    $guiEnvironment["QT_QPA_PLATFORM"] = "offscreen"
    $g = Invoke-Clean $gui @("--smoke-test") $guiEnvironment
    Check ($g.ExitCode -eq 0) "the GUI executable starts and builds its main window (exit $($g.ExitCode))"

    $keep = Join-Path $profileDir "selftest-1"
    $first = Invoke-Clean $exe @("selftest", "--keep", $keep) $environment
    Check ($first.ExitCode -eq 0 -and $first.Out -match "selftest passed") "selftest passes through the bundled host, first launch ($($first.Seconds) s)"
    if ($first.ExitCode -ne 0) { Write-Output $first.Out; Write-Output $first.Err }
    $wavs = @(Get-ChildItem -LiteralPath (Join-Path $keep "out") -Recurse -Filter *.wav -ErrorAction SilentlyContinue)
    Check ($wavs.Count -eq 13) "13 WAV files were written ($($wavs.Count))"
    $manifest = Get-ChildItem -LiteralPath $keep -Recurse -Filter manifest.json -ErrorAction SilentlyContinue | Select-Object -First 1
    Check ($null -ne $manifest) "a manifest.json was written"

    $runtime = Join-Path $data "runtime"
    $hosts = @(Get-ChildItem -LiteralPath $runtime -Directory -Filter "host-*" -ErrorAction SilentlyContinue)
    Check ($hosts.Count -eq 1) "one per-user host runtime copy exists under the data folder ($($hosts.Count))"
    $hostExe = Join-Path $hosts[0].FullName "blt-render-host.exe"
    $stamp = (Get-Item -LiteralPath $hostExe).LastWriteTimeUtc.Ticks
    $created = $hosts[0].CreationTimeUtc.Ticks
    $listing = Snapshot $hosts[0].FullName

    $second = Invoke-Clean $exe @("selftest", "--keep", (Join-Path $profileDir "selftest-2")) $environment
    Check ($second.ExitCode -eq 0 -and $second.Out -match "selftest passed") "selftest passes again, second launch ($($second.Seconds) s)"
    $hostsAfter = @(Get-ChildItem -LiteralPath $runtime -Directory -Filter "host-*")
    Check ($hostsAfter.Count -eq 1 -and $hostsAfter[0].CreationTimeUtc.Ticks -eq $created -and (Get-Item -LiteralPath $hostExe).LastWriteTimeUtc.Ticks -eq $stamp) "the second launch reused the host copy instead of reinstalling it"

    # the English phonemizers' neural g2p fallback must run on the onnxruntime.dll shipped beside the host
    # (or, in the variant built without the model, there must be no guess and no onnxruntime at all)
    $g2p = Invoke-Clean $hostExe @("--g2p-check") $environment
    $g2pResult = $null
    foreach ($line in ($g2p.Out -split "`n")) { if ($line.StartsWith("{")) { $g2pResult = $line | ConvertFrom-Json } }
    $buildRecord = Get-Content -LiteralPath (Join-Path (Split-Path $hostExe) "blt-host-build.json") -Raw | ConvertFrom-Json
    Check ($g2pResult -and $g2pResult.g2p_model -eq $buildRecord.g2p_model) "the host's g2p model state ($($g2pResult.g2p_model)) is the one its build record names ($($buildRecord.g2p_model))"
    if ($g2pResult -and $g2pResult.g2p_model -eq "excluded") {
        Check ($g2p.ExitCode -eq 0 -and -not $g2pResult.onnxruntime -and -not $g2pResult.g2p_phonemes -and $g2pResult.g2p_known_phonemes) "no g2p model: a dictionary word is phonemized ($($g2pResult.g2p_known_phonemes)), a word outside it gets no guess, onnxruntime is not loaded"
    } else {
        Check ($g2p.ExitCode -eq 0 -and $g2pResult -and $g2pResult.onnxruntime_beside_host -and $g2pResult.g2p_phonemes) "an English word outside the dictionary is phonemized with the onnxruntime.dll shipped beside the host ($($g2pResult.g2p_phonemes))"
    }
    # what the installed host copy contains: the same phonemizer list and resource count as the shipped host
    $inventory = Invoke-Clean $hostExe @("--inventory") $environment
    $inventoryResult = $null
    foreach ($line in ($inventory.Out -split "`n")) { if ($line.StartsWith("{")) { $inventoryResult = $line | ConvertFrom-Json } }
    $names = @($inventoryResult.phonemizers)
    Check ($inventory.ExitCode -eq 0 -and $names.Count -gt 0 -and -not ($names -match "Plus|CpV|Voicevox")) "the installed host's own inventory lists $($names.Count) phonemizers, none of the removed ones (Arpasing+, English C+V, DiffSinger English+, Voicevox)"

    $after = Snapshot $appDir
    Check ($before -eq $after) "the program folder is unchanged after running (no caches, settings or temp files in it)"
    Check (-not (Test-Path (Join-Path $appDir "host\OpenUtau")) -and -not (Test-Path (Join-Path $appDir "host\Logs"))) "no OpenUtau cache, prefs or logs were created beside the shipped host"
}

function Add-RuntimeCopies($appDir) {
    foreach ($name in ($RuntimeCopies -split ";" | Where-Object { $_ })) {
        $target = Join-Path $appDir "_internal/numpy.libs/$name"
        if (-not (Test-Path -LiteralPath $target)) {
            $source = Join-Path $env:SystemRoot ("System32\" + ($name -replace "-[0-9a-f]{32}", ""))
            New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
            Copy-Item -LiteralPath $source -Destination $target
        }
    }
}

try {
    Write-Output "Package: $App"
    $profileA = Join-Path $base "profile"
    $plainApp = Join-Path $base "plain\BLT Music Generator"
    robocopy $App $plainApp /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed" }
    $global:LASTEXITCODE = 0
    Add-RuntimeCopies $plainApp
    Scenario "plain paths" $plainApp $profileA (Join-Path $profileA "BLT data")

    $oddRoot = Join-Path $base $odd
    $oddApp = Join-Path $oddRoot "Program Files\BLT Music Generator"
    robocopy $App $oddApp /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed" }
    $global:LASTEXITCODE = 0
    Add-RuntimeCopies $oddApp
    Scenario "spaces and non-ASCII in every path" $oddApp (Join-Path $oddRoot "Users\$odd") (Join-Path $oddRoot "Users\$odd\AppData\Local\BarbershopLearningTracks")

    # a package whose renamed copy of the PC's MSVCP140 is missing (the installer normally makes it) repairs itself
    $healApp = Join-Path $base "heal\BLT Music Generator"
    robocopy $App $healApp /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed" }
    $global:LASTEXITCODE = 0
    $manifestFile = Join-Path $healApp "_internal/blt-runtime-copies.json"
    Write-Output ""
    Write-Output "[self-repair of the renamed runtime copy]"
    if ($RuntimeCopies -and (Test-Path $manifestFile)) {
        $copies = @((Get-Content $manifestFile -Raw | ConvertFrom-Json).PSObject.Properties.Name)
        $copyPath = Join-Path $healApp ("_internal/" + $copies[0])
        Check ($copies.Count -ge 1 -and -not (Test-Path -LiteralPath $copyPath)) "the renamed copy is absent before the first start"
        $healProfile = Join-Path $base "heal-profile"
        $healed = Invoke-Clean (Join-Path $healApp "blt.exe") @("--version") (Clean-Environment $healProfile (Join-Path $healProfile "data"))
        Check ($healed.ExitCode -eq 0 -and $healed.Out -match "\d+\.\d+") "blt starts without it (NumPy imports)"
        Check (Test-Path -LiteralPath $copyPath) "and has made the copy from the PC's own msvcp140.dll"
    } else {
        Write-Output "  skipped: no renamed runtime copy in this package"
    }
}
finally {
    if (-not $Keep) { cmd /c rmdir /s /q "$base" 2>$null | Out-Null } else { Write-Output "kept: $base" }
}
Write-Output ""
if ($script:failures.Count) {
    Write-Output "SMOKE TEST FAILED ($($script:failures.Count)):"
    $script:failures | ForEach-Object { Write-Output "  - $_" }
    exit 1
}
Write-Output "smoke test passed"
