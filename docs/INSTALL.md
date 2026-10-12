# Installing and first run

BLT Music Generator turns a four-part (TTBB) MusicXML score from MuseScore into 13 learning tracks:
the full quartet, and for each of Tenor, Lead, Baritone and Bass a *predominant* track (that part
loud, the others quiet), a *solo* track and a *without* track (the other three, so you can sing the
missing part).

> **This is a pre-release build.** It is not code-signed, so Windows will warn about it, and it has not
> yet been tested with an English voicebank. See [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md).

## What you need

* Windows 10 or 11, 64-bit. Nothing else has to be installed (no Python, no .NET).
* A **singing voicebank** that works with OpenUtau (UTAU-style), for example an English one. BLT does not
  include or download any; you get one from its author and agree to its licence.
* A MusicXML export (`.musicxml`, `.xml` or `.mxl`) of your arrangement from MuseScore, with the lyrics
  typed under every note of the four parts.
* Optional, for MP3 output: **FFmpeg** (a separate free program). WAV output needs nothing.

## Install

1. Run `BLT-Music-Generator-<version>-Setup.exe`.
2. Windows SmartScreen may say "Windows protected your PC", because the installer is not signed. If you
   trust where you got it and its checksum matches the one published with it, choose **More info**, then
   **Run anyway**. (Compare checksums with `Get-FileHash <file> -Algorithm SHA256` in PowerShell.)
3. Accept the defaults. BLT installs for your user only, without administrator rights, and puts
   **BLT Music Generator** in the Start menu. Tick the desktop-shortcut box if you want one.

Uninstall from Settings > Apps. Your voicebanks, generated tracks and settings are left in place.
Installing a newer version over the old one upgrades it and keeps everything of yours.

## First run

1. Start **BLT Music Generator** from the Start menu.
2. **Voices.** Put your voicebank folder(s) in `Documents\OpenUtau\Singers`, or press *Choose folder* in the
   Voices section (*Browse…*) and point at the folder that contains them. Press *Refresh*; they are listed.
3. **Score.** Press *Choose score…* (or drop the file on the window).
4. **Parts.** Tell BLT which line of the score is Tenor, Lead, Baritone and Bass (*Suggest voices* fills in
   likely ones from the part names; you confirm them).
5. **Singer.** Choose the voicebank for the parts (the same one for all, or one per part).
6. **Lyrics.** Where notes have no lyric of their own (a held vowel, or something missing), *Review lyrics…*
   lets you decide what they are sung to; fix or approve them. Generating stays disabled until nothing is
   unresolved, and the window says why.
7. **Output.** Choose an output folder and WAV (or MP3).
8. Press **Generate**. It shows each stage; when it finishes, *Open output folder* shows the 13 files and
   `manifest.json`. The first generation also sets up BLT's private copy of the singing engine, which takes a few
   seconds.

## MP3 (optional)

Install FFmpeg yourself (for example from ffmpeg.org builds), then in the Output section choose
*Choose FFmpeg…* and select `ffmpeg.exe`. BLT does not include FFmpeg because its licence depends on how the
build was made.

## Checking that the installation works

Open Command Prompt or PowerShell in the install folder (or use the Start-menu group) and run:

```
"%LOCALAPPDATA%\Programs\BLT Music Generator\blt.exe" selftest
```

It builds a tiny score and a synthetic test voice and generates the 13 files; it prints "selftest passed" when
the installation is sound. (It proves the program works, not how a real voice sounds.)
`blt.exe diagnostics`, or *Help > Copy diagnostics*, tells you where BLT found everything.

Problems: see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
