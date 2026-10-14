# Check the 13 tracks BLT made, with arithmetic only. It does NOT listen: pitch, words, rhythm and balance are yours.
#
#   powershell -ExecutionPolicy Bypass -File Check-Outputs.ps1 -Folder "C:\path\to\<song>_learning_tracks" [-Report result.txt]
#
# What it proves (and what a listening test then does not have to):
#   * the 13 files and manifest.json are there, with the names BLT promises;
#   * every file is 16-bit mono PCM at 44.1 kHz and ALL have exactly the same length (nothing drifts);
#   * none is silent and none is clipped (flat tops);
#   * the mixes agree with each other, sample by sample, under the gains the manifest records. The full quartet is
#     (gF * all four voices), a solo is (gS * one voice), "Without X" is (gW * the other three), and "X Predominant" is
#     (gP * X + gO * the others). So for every voice X:  Full / gF  =  Solo / gS + Without / gW   and
#     Predominant = gO * (Full / gF) + (gP - gO) * (Solo / gS).  If a voice were misplaced in time, missing from a mix,
#     or in the wrong mix, one of these would fail. They hold to a few quantisation steps of 16-bit audio.
# It reads files and writes nothing (unless you name a -Report file).
param(
    [Parameter(Mandatory = $true)][string]$Folder,
    [string]$Report = ""
)
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @"
using System;
using System.IO;

public static class BltWav {
    public class Info { public int Channels, Rate, Bits, Format; public short[] Samples; }

    public static Info Read(string path) {
        byte[] b = File.ReadAllBytes(path);
        if (b.Length < 44 || b[0] != 'R' || b[1] != 'I' || b[2] != 'F' || b[3] != 'F' || b[8] != 'W' || b[9] != 'A' || b[10] != 'V' || b[11] != 'E')
            throw new Exception("not a RIFF/WAVE file");
        var info = new Info();
        int pos = 12;
        bool haveData = false;
        while (pos + 8 <= b.Length) {
            string id = "" + (char)b[pos] + (char)b[pos + 1] + (char)b[pos + 2] + (char)b[pos + 3];
            int size = BitConverter.ToInt32(b, pos + 4);
            int body = pos + 8;
            if (id == "fmt ") {
                info.Format = BitConverter.ToInt16(b, body);
                info.Channels = BitConverter.ToInt16(b, body + 2);
                info.Rate = BitConverter.ToInt32(b, body + 4);
                info.Bits = BitConverter.ToInt16(b, body + 14);
            } else if (id == "data") {
                int n = Math.Min(size, b.Length - body) / 2;
                info.Samples = new short[n];
                Buffer.BlockCopy(b, body, info.Samples, 0, n * 2);
                haveData = true;
                break;
            }
            pos = body + size + (size & 1);
        }
        if (!haveData) throw new Exception("no audio data");
        return info;
    }

    public static double Peak(short[] s) {
        int peak = 0;
        foreach (short v in s) { int a = v == short.MinValue ? 32768 : Math.Abs((int)v); if (a > peak) peak = a; }
        return peak / 32768.0;
    }

    public static double Rms(short[] s) {
        double sum = 0;
        foreach (short v in s) sum += (double)v * v;
        return Math.Sqrt(sum / Math.Max(1, s.Length)) / 32768.0;
    }

    // largest |a * ka + b * kb - c| in 16-bit steps
    public static double MaxDifference(short[] a, double ka, short[] b, double kb, short[] c) {
        double worst = 0;
        for (int i = 0; i < c.Length; i++) {
            double d = Math.Abs(a[i] * ka + b[i] * kb - c[i]);
            if (d > worst) worst = d;
        }
        return worst;
    }
}
"@

$Folder = (Resolve-Path -LiteralPath $Folder).Path
$lines = New-Object System.Collections.Generic.List[string]
$failures = New-Object System.Collections.Generic.List[string]
function Say($text) { $lines.Add($text); Write-Output $text }
function Check($ok, $text) { if ($ok) { Say "  ok    $text" } else { Say "  FAIL  $text"; $failures.Add($text) } }

$voices = "Tenor", "Lead", "Baritone", "Bass"
$names = [ordered]@{ "Full" = "01_Full_Quartet.wav" }
$n = 2
foreach ($kind in "Predominant", "Solo", "Without") {
    foreach ($voice in $voices) {
        $label = if ($kind -eq "Without") { "Without_$voice" } else { "${voice}_$kind" }
        $names["$kind $voice"] = ("{0:00}_{1}.wav" -f $n, $label)
        $n++
    }
}
Say "Folder: $Folder"
$manifestPath = Join-Path $Folder "manifest.json"
Check (Test-Path -LiteralPath $manifestPath) "manifest.json is present"
$missing = @($names.Values | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Folder $_)) })
Check ($missing.Count -eq 0) "all 13 files are present$(if ($missing.Count) { ' (missing: ' + ($missing -join ', ') + ')' })"
if ($failures.Count) { Say "`nCannot go on: $($failures.Count) problem(s)."; if ($Report) { $lines | Set-Content -LiteralPath $Report -Encoding utf8 }; exit 1 }

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$gain = $manifest.settings.gain_profile
Say "Gain profile recorded in the manifest: full $($gain.full_quartet), predominant $($gain.predominant_focus)/$($gain.predominant_others), solo $($gain.solo), without $($gain.without_each)"

$audio = @{}
Say "`nEach file:"
foreach ($key in $names.Keys) {
    $file = $names[$key]
    $info = [BltWav]::Read((Join-Path $Folder $file))
    $audio[$key] = $info
    $peak = [BltWav]::Peak($info.Samples)
    $rms = [BltWav]::Rms($info.Samples)
    $seconds = $info.Samples.Length / [double]$info.Rate
    $peakDb = if ($peak -gt 0) { [math]::Round(20 * [math]::Log10($peak), 1) } else { -999 }
    $rmsDb = if ($rms -gt 0) { [math]::Round(20 * [math]::Log10($rms), 1) } else { -999 }
    Say ("  {0,-26} {1,6:N2} s  peak {2,6} dBFS  rms {3,6} dBFS" -f $file, $seconds, $peakDb, $rmsDb)
    Check ($info.Format -eq 1 -and $info.Channels -eq 1 -and $info.Bits -eq 16 -and $info.Rate -eq 44100) "$file is 16-bit mono PCM at 44.1 kHz"
    Check ($peak -gt 0.0001) "$file is not silent"
    Check ($peak -lt 0.999) "$file is not clipped"
}
Say "`nLengths and agreement of the mixes:"
$frames = $audio["Full"].Samples.Length
Check (@($audio.Values | Where-Object { $_.Samples.Length -ne $frames }).Count -eq 0) "all 13 files have exactly the same length ($frames samples)"
Check ($manifest.audio.frames -eq $frames) "the length matches the manifest ($($manifest.audio.frames) samples)"
$tolerance = 12.0   # 16-bit steps; each file is quantised once and the gains scale that error
foreach ($voice in $voices) {
    $full = $audio["Full"].Samples
    $solo = $audio["Solo $voice"].Samples
    $without = $audio["Without $voice"].Samples
    $predominant = $audio["Predominant $voice"].Samples
    # Full / gF  =  Solo / gS + Without / gW   (compare in the scale of Full: multiply by gF)
    $d1 = [BltWav]::MaxDifference($solo, $gain.full_quartet / $gain.solo, $without, $gain.full_quartet / $gain.without_each, $full)
    Check ($d1 -le $tolerance) ("{0}: Solo and Without {0} add up to the Full Quartet (largest difference {1:N1} steps of 16-bit audio)" -f $voice, $d1)
    # Predominant = gO * (Full / gF) + (gP - gO) * (Solo / gS)
    $d2 = [BltWav]::MaxDifference($full, $gain.predominant_others / $gain.full_quartet, $solo, ($gain.predominant_focus - $gain.predominant_others) / $gain.solo, $predominant)
    Check ($d2 -le $tolerance) ("{0}: {0} Predominant is the Full Quartet and the solo mixed as the manifest says (largest difference {1:N1} steps)" -f $voice, $d2)
}
if ($failures.Count) {
    Say "`nRESULT: $($failures.Count) check(s) FAILED:"
    $failures | ForEach-Object { Say "  - $_" }
} else {
    Say "`nRESULT: every arithmetic check passed. Now listen (the checklist's pitch, rhythm, synchronisation and words)."
}
if ($Report) { $lines | Set-Content -LiteralPath $Report -Encoding utf8 }
exit $(if ($failures.Count) { 1 } else { 0 })
