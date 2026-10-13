# Drive the real Setup wizard when Microsoft's Visual C++ runtime is "missing", and record what a user sees.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File packaging/installer-gui-test.ps1 `
#       -Installer <Setup.exe> -App <built package folder> [-Screenshots <folder>]
#
# The runtime IS installed on this PC; the installer's test switch /VCRUNTIME=missing makes Setup behave as if it
# were not. Nothing is installed by this test: every scenario ends at the prerequisite dialog or before it, and
# the uninstall entry is compared before and after. It clicks through the wizard with Win32 messages and reads the
# Windows task dialog with UI Automation. What it proves, per scenario:
#   1  the Ready page's Install button stops at a dialog that explains the prerequisite and offers
#      download / local file / go back; "Go back" returns to the wizard and installs nothing;
#   2  a vc_redist.x64.exe next to the installer is found without a file dialog; a file that is signed, but not by
#      Microsoft (python.exe, signed by the PSF), is refused with a message and never started;
#   3  with no file next to the installer, the "I have one" button opens a file chooser; cancelling it returns to the dialog;
#   4  the download button, pointed at a local web server that serves an UNSIGNED file, downloads it and refuses to run it;
#   5  the download button with nothing listening reports the failure, names the Microsoft page and returns to the dialog;
#   6  the signature test Setup uses (the same PowerShell command) accepts a genuine Microsoft file and rejects an
#      unsigned file, a file signed by someone else and a Microsoft file whose bytes were changed.
# NOT covered, because it needs a person to approve the Windows administrator prompt (UAC): the path where a genuine
# Microsoft installer is accepted, started with "runas", and the runtime then re-detected. That is in
# docs/acceptance/clean-machine-verification.md.
param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][string]$App,
    [string]$Screenshots = "",
    [switch]$Trace
)
$ErrorActionPreference = "Stop"
$Installer = (Resolve-Path $Installer).Path
$App = (Resolve-Path $App).Path
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = if ($env:BLT_PYTHON) { $env:BLT_PYTHON } elseif (Test-Path (Join-Path $root ".venv/Scripts/python.exe")) { Join-Path $root ".venv/Scripts/python.exe" } else { "python" }
$failures = New-Object System.Collections.Generic.List[string]
function Check($ok, $text) { if ($ok) { Write-Output "  ok    $text" } else { Write-Output "  FAIL  $text"; $failures.Add($text) } }
function Note($text) { Write-Output "  note  $text" }

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc p, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  public static List<IntPtr> Top() { var r = new List<IntPtr>(); EnumWindows((h, l) => { r.Add(h); return true; }, IntPtr.Zero); return r; }
  public static List<IntPtr> Kids(IntPtr p) { var r = new List<IntPtr>(); EnumChildWindows(p, (h, l) => { r.Add(h); return true; }, IntPtr.Zero); return r; }
  public static string Text(IntPtr h) { var s = new StringBuilder(1024); GetWindowText(h, s, 1024); return s.ToString(); }
  public static string Cls(IntPtr h) { var s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
}
"@
$BM_CLICK = 0x00F5

function Visible-Tops { [W]::Top() | Where-Object { [W]::IsWindowVisible($_) -and [W]::Text($_) } }
function Find-Top($titlePattern) { Visible-Tops | Where-Object { [W]::Text($_) -match $titlePattern } | Select-Object -First 1 }
function Wait-For($script, $seconds = 40) {
    $until = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $until) { $r = & $script; if ($r) { return $r }; Start-Sleep -Milliseconds 400 }
    return $null
}
function Click-Win32($parent, $classPattern, $textPattern) {
    $k = [W]::Kids($parent) | Where-Object { [W]::IsWindowVisible($_) -and ([W]::Cls($_) -match $classPattern) -and ([W]::Text($_) -match $textPattern) } | Select-Object -First 1
    if (-not $k) { return $false }
    [void][W]::PostMessage($k, $BM_CLICK, [IntPtr]::Zero, [IntPtr]::Zero)
    return $true
}
function Shot($hwnd, $name) {
    if (-not $Screenshots) { return }
    New-Item -ItemType Directory -Force $Screenshots | Out-Null
    [void][W]::SetForegroundWindow($hwnd); Start-Sleep -Milliseconds 500
    $r = New-Object W+RECT; [void][W]::GetWindowRect($hwnd, [ref]$r)
    $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
    $g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size); $g.Dispose()
    $bmp.Save((Join-Path $Screenshots "$name.png"), [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
}
function Ui-Buttons($hwnd) {
    $el = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
    @($el.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond))
}
function Ui-Links($hwnd) {
    $el = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "CCCommandLink")
    @($el.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond))
}
# TDM_CLICK_BUTTON (WM_USER + 102): presses a button of a Windows task dialog; Setup maps its three
# custom buttons to Yes (6), No (7) and Cancel (2)
function Task-Click($hwnd, $id) { [void][W]::PostMessage($hwnd, 0x0466, [IntPtr]$id, [IntPtr]::Zero) }
function Ui-Text($hwnd) {
    $el = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Text)
    $ui = (@($el.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)) | ForEach-Object { $_.Current.Name }) -join " | "
    # an ordinary message box keeps its text in Static child windows
    $win32 = ([W]::Kids($hwnd) | Where-Object { [W]::Cls($_) -eq "Static" } | ForEach-Object { [W]::Text($_) } | Where-Object { $_ }) -join " | "
    (($ui, $win32) | Where-Object { $_ }) -join " | "
}
function Ui-Click($hwnd, $namePattern) {
    $b = Ui-Buttons $hwnd | Where-Object { $_.Current.Name -match $namePattern } | Select-Object -First 1
    if (-not $b) { return $false }
    $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    return $true
}
function Message-Box-Text($hwnd) { (Ui-Text $hwnd) }

$DialogTitle = "Visual C\+\+ Redistributable"
$testStart = Get-Date
function Stop-Setup {
    # the outer Setup program, Inno's extracted Setup.tmp (started by this test) and any Microsoft installer it started
    Get-Process | Where-Object {
        ($_.ProcessName -like "BLT-Music-Generator*") -or ($_.ProcessName -like "vc_redist*") -or
        ((($_.ProcessName -eq "Setup") -or ($_.ProcessName -eq "Setup.tmp")) -and ($_.StartTime -ge $testStart))
    } | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
}
# a message box or task dialog of Setup (window title "Setup") whose text matches
function Dump-Tops {
    foreach ($h in Visible-Tops) { Write-Host ("    TOP class=" + [W]::Cls($h) + " '" + [W]::Text($h) + "' ui=" + ($(if ([W]::Cls($h) -eq "#32770") { Ui-Text $h } else { "" }))) }
}
function Find-Msg($textPattern) {
    Visible-Tops | Where-Object { ([W]::Cls($_) -eq "#32770") -and ([W]::Text($_) -eq "Setup") -and ((Ui-Text $_) -match $textPattern) } | Select-Object -First 1
}

# click through the wizard until the prerequisite dialog is up
function Reach-Dialog($setupPath, $dir) {
    Stop-Setup
    [void](Start-Process -FilePath $setupPath -ArgumentList @("/VCRUNTIME=missing", "/CURRENTUSER", "/DIR=`"$dir`"", "/NORESTART"))
    $until = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $until) {
        $dialog = Find-Msg $DialogTitle
        if ($dialog) { return $dialog }
        $wiz = Visible-Tops | Where-Object { [W]::Cls($_) -eq "TWizardForm" } | Select-Object -First 1
        if ($wiz) {
            $heading = ([W]::Kids($wiz) | Where-Object { [W]::IsWindowVisible($_) -and [W]::Cls($_) -eq "TNewStaticText" } | Select-Object -First 1)
            $title = if ($heading) { [W]::Text($heading) } else { "" }
            if ($Trace) { Write-Host "    wizard page: '$title'" }
            if ($title -eq "License Agreement") { [void](Click-Win32 $wiz "TNewRadioButton" "accept the agreement") }
            if (-not (Click-Win32 $wiz "TNewButton" "^&Install")) { [void](Click-Win32 $wiz "TNewButton" "^&Next") }
        }
        Start-Sleep -Seconds 1
    }
    return $null
}
function Uninstall-Entry { Test-Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{7A3B1E52-4C8D-4F6A-9B21-5D0E8C6F3A17}_is1" }

$base = Join-Path $env:TEMP ("blt-guitest-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force $base | Out-Null
$target = Join-Path $base "install-target"
$entryBefore = Uninstall-Entry
$SetupName = Split-Path $Installer -Leaf
$server = $null
try {
    # ---------------------------------------------------------------- scenario 1: the dialog
    Write-Output "[1 the prerequisite dialog]"
    $dir1 = Join-Path $base "s1"; New-Item -ItemType Directory -Force $dir1 | Out-Null
    Copy-Item $Installer (Join-Path $dir1 $SetupName)
    $d = Reach-Dialog (Join-Path $dir1 $SetupName) $target
    Check ([bool]$d) "Install on the Ready page stops at a dialog about the Microsoft Visual C++ Redistributable"
    if ($d) {
        Shot $d "1-dialog"
        $text = Ui-Text $d
        $buttons = (Ui-Links $d | ForEach-Object { $_.Current.Name }) -join " | "
        Note "text: $text"
        Note "buttons: $buttons"
        Check ($text -match "Visual C\+\+ Redistributable" -and $text -match "not part of this installer") "the text names Microsoft's Visual C++ Redistributable and says it is not part of the installer"
        Check ($text -match "Without internet" -and $text -match "aka.ms/vc14/vc_redist.x64.exe") "the text explains the offline route and gives the short download address in full"
        Check ($buttons -match "Download and install it now" -and $buttons -match "Install from a vc_redist.x64.exe I have" -and $buttons -match "Go back") "three choices are offered: download, local file, go back"
        Check (-not (Test-Path (Join-Path $target "BLT Music Generator.exe"))) "nothing is installed while the dialog is open"
        Task-Click $d 2
        Start-Sleep -Seconds 2
        $wizard = Visible-Tops | Where-Object { [W]::Cls($_) -eq "TWizardForm" } | Select-Object -First 1
        $dialogAgain = Find-Msg $DialogTitle
        Note ("after 'Go back': the wizard is " + $(if ($wizard) { "still open" } else { "closed" }) + ", the dialog is " + $(if ($dialogAgain) { "open again" } else { "closed" }))
        if ($wizard) { Shot $wizard "1-after-cancel" }
        Check (-not (Test-Path (Join-Path $target "BLT Music Generator.exe")) -and ((Uninstall-Entry) -eq $entryBefore)) "after 'Go back' nothing was installed and no uninstall entry was created"
    }

    # ---------------------------------------------------------------- scenario 2: a file next to the installer
    Write-Output "[2 a vc_redist.x64.exe next to the installer]"
    $dir2 = Join-Path $base "s2"; New-Item -ItemType Directory -Force $dir2 | Out-Null
    Copy-Item $Installer (Join-Path $dir2 $SetupName)
    Copy-Item $python (Join-Path $dir2 "vc_redist.x64.exe")   # genuinely signed (by the Python Software Foundation), not by Microsoft
    $d = Reach-Dialog (Join-Path $dir2 $SetupName) $target
    Check ([bool]$d) "dialog reached"
    if ($d) {
        Task-Click $d 7
        $refusal = Wait-For { Find-Msg "not signed by Microsoft" } 25
        if ((-not $refusal) -and $Trace) { Dump-Tops }
        Check ([bool]$refusal) "no file chooser opened (the file beside the installer was used) and a signed-by-someone-else file is refused: 'is not signed by Microsoft, so it will not be run'"
        if ($refusal) {
            Note ("refusal: " + (Ui-Text $refusal))
            Shot $refusal "2-refused"
            [void](Click-Win32 $refusal "Button" "^OK")
        }
        Check (-not (Get-Process -Name "vc_redist*" -ErrorAction SilentlyContinue)) "the refused file was never started"
        $back = Wait-For { Find-Msg $DialogTitle } 15
        Check ([bool]$back) "and returns to the prerequisite dialog"
        if ($back) { Task-Click $back 2 }
    }

    # ---------------------------------------------------------------- scenario 3: no file: a file chooser
    Write-Output "[3 no file next to the installer]"
    $d = Reach-Dialog (Join-Path $dir1 $SetupName) $target
    if ($d) {
        Task-Click $d 7
        $chooser = Wait-For { Find-Top "Choose vc_redist" } 20
        Check ([bool]$chooser) "a file chooser titled 'Choose vc_redist.x64.exe' opens"
        if ($chooser) {
            Shot $chooser "3-chooser"
            [void](Click-Win32 $chooser "Button" "^Cancel|^&Cancel")
            $back = Wait-For { Find-Msg $DialogTitle } 15
            Check ([bool]$back) "cancelling the chooser returns straight to the prerequisite dialog (no extra message)"
            if ($back) { Task-Click $back 2 }
        }
    } else { Check $false "dialog reached" }

    # ---------------------------------------------------------------- variants with another download address
    $iscc = @($env:BLT_ISCC, "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $iscc) { throw "ISCC not found: needed for the download scenarios" }
    $renamed = @(& $python (Join-Path $root "packaging/runtime_copies.py") $App)
    function Build-Variant($url, $name) {
        $outDir = Join-Path $base $name
        $defs = @("/DAppVersion=0.1.0", "/DSourceDir=$App", "/DOutputDir=$outDir", "/DVcRedistUrlOverride=$url")
        if ($renamed.Count -eq 1) { $defs += "/DNumpyMsvcp=$($renamed[0])" }
        & $iscc /Qp @defs (Join-Path $root "packaging/installer.iss") | Out-Null
        return (Join-Path $outDir "BLT-Music-Generator-0.1.0-Setup.exe")
    }

    # ---------------------------------------------------------------- scenario 4: download of an unsigned file
    Write-Output "[4 download from a local server that serves an unsigned file]"
    $served = Join-Path $base "served"; New-Item -ItemType Directory -Force $served | Out-Null
    Copy-Item $Installer (Join-Path $served "vc_redist.x64.exe")   # BLT's own installer: unsigned
    $port = 18000 + (Get-Random -Maximum 1000)
    $server = Start-Process -FilePath $python -ArgumentList @("-m", "http.server", "$port", "--bind", "127.0.0.1", "--directory", "`"$served`"") -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
    $variant = Build-Variant "http://127.0.0.1:$port/vc_redist.x64.exe" "v-download"
    $d = Reach-Dialog $variant $target
    if ($d) {
        Task-Click $d 6
        $refusal = Wait-For { Find-Msg "not signed by Microsoft" } 40
        Check ([bool]$refusal) "the downloaded unsigned file is refused: 'is not signed by Microsoft, so it will not be run'"
        if ($refusal) { Shot $refusal "4-refused"; [void](Click-Win32 $refusal "Button" "^OK") }
        Check (-not (Get-Process -Name "vc_redist*" -ErrorAction SilentlyContinue)) "the downloaded file was never started"
        $back = Wait-For { Find-Msg $DialogTitle } 15
        Check ([bool]$back) "Setup returns to the prerequisite dialog"
        if ($back) { Task-Click $back 2 }
    } else { Check $false "dialog reached" }
    if ($server) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue; $server = $null }

    # ---------------------------------------------------------------- scenario 5: download fails
    Write-Output "[5 the download fails (nothing is listening)]"
    $variant = Build-Variant "http://127.0.0.1:9/vc_redist.x64.exe" "v-fail"
    $d = Reach-Dialog $variant $target
    if ($d) {
        Task-Click $d 6
        $failure = Wait-For { Find-Msg "download from Microsoft did not work" } 60
        Check ([bool]$failure) "the failure is reported: 'The download from Microsoft did not work'"
        if ($failure) {
            $t = Ui-Text $failure
            Note "message: $t"
            Shot $failure "5-download-failed"
            Check ($t -match "learn.microsoft.com") "the message names Microsoft's page to download from by hand"
            [void](Click-Win32 $failure "Button" "^OK")
        }
        $back = Wait-For { Find-Msg $DialogTitle } 15
        Check ([bool]$back) "Setup returns to the prerequisite dialog"
        if ($back) { Task-Click $back 2 }
    } else { Check $false "dialog reached" }
}
finally {
    if ($server) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
    Stop-Setup
}

# ---------------------------------------------------------------- scenario 6: the signature test itself
Write-Output "[6 the signature check Setup runs]"
function Is-MicrosoftSigned($file) {
    $escaped = $file -replace "'", "''"
    $command = "`$s = Get-AuthenticodeSignature -LiteralPath '$escaped'; if (`$s.Status -eq 'Valid' -and `$s.SignerCertificate.Subject -match 'O=Microsoft Corporation') { exit 0 } else { exit 1 }"
    $p = Start-Process powershell.exe -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "`"$($command -replace '"', '\"')`"") -Wait -PassThru -WindowStyle Hidden
    return ($p.ExitCode -eq 0)
}
$microsoft = Get-ChildItem "$env:ProgramData\Microsoft\VisualStudio\Packages" -Recurse -Filter "VC_redist.x64.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $microsoft) { $microsoft = Get-Item (Join-Path $env:SystemRoot "System32\notepad.exe") }
Note "genuine Microsoft file used for the positive case: $($microsoft.FullName)"
Check (Is-MicrosoftSigned $microsoft.FullName) "a genuine Microsoft-signed file is accepted"
Check (-not (Is-MicrosoftSigned $Installer)) "an unsigned file (BLT's own installer) is rejected"
Check (-not (Is-MicrosoftSigned $python)) "a validly signed file from another publisher (python.exe) is rejected"
$tampered = Join-Path $base "tampered.exe"
Copy-Item $microsoft.FullName $tampered
$s = [System.IO.File]::Open($tampered, [System.IO.FileMode]::Append); $s.Write([byte[]](1, 2, 3, 4), 0, 4); $s.Close()
Check (-not (Is-MicrosoftSigned $tampered)) "a Microsoft file whose bytes were changed after signing is rejected"

cmd /c rmdir /s /q "$base" 2>$null | Out-Null
Check ((Uninstall-Entry) -eq $entryBefore) "no uninstall entry was created or removed by this test"
if ($failures.Count) {
    Write-Output "INSTALLER GUI TEST FAILED ($($failures.Count))"
    $failures | ForEach-Object { Write-Output "  - $_" }
    exit 1
}
Write-Output "installer GUI test passed"
