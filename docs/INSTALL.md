# Installing and first run

BLT Music Generator turns a four-part (TTBB) MusicXML score from MuseScore into 13 learning tracks:
the full quartet, and for each of Tenor, Lead, Baritone and Bass a *predominant* track (that part
loud, the others quiet), a *solo* track and a *without* track (the other three, so you can sing the
missing part).

> **This is a pre-release build.** It is not code-signed, so Windows will warn about it, and it has not
> yet been tested with an English voicebank. See [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md).

## What you need

* Windows 10 or 11, 64-bit, or macOS 12 or later (Apple silicon or Intel; see [Installing on macOS](#installing-on-macos)).
  The rest of this page describes Windows; the macOS differences are in that section.
* On Windows: No Python and no .NET are needed. BLT does need Microsoft's **Visual C++ Redistributable
  (x64)**, which most PCs already have; if yours does not, Setup offers to download it from Microsoft or to use a copy you
  have (see below). BLT does not contain Microsoft's runtime files itself.
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

**Visual C++ Redistributable.** Setup checks for Microsoft's runtime (version 14.44 or newer) when you press Install. If it is
missing, a window "Microsoft Visual C++ runtime needed" offers three buttons: *Download and install it now* (from
https://aka.ms/vc14/vc_redist.x64.exe), *Install from a vc_redist.x64.exe I have*, and *Go back (BLT is not installed yet)*.
Setup runs the file only if Windows reports that Microsoft signed it; Microsoft's own installer then shows its licence terms and
Windows asks for administrator approval (a standard user needs an administrator's password; BLT itself needs none). After that
Setup carries on installing BLT.
*Without internet:* on a PC that is online, download `vc_redist.x64.exe` from https://aka.ms/vc14/vc_redist.x64.exe (or
https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) and put it on a USB stick **next to**
`BLT-Music-Generator-<version>-Setup.exe`; Setup then uses it without asking where it is. Otherwise choose
*Install from a vc_redist.x64.exe I have* and browse to it. A silent install (`/SILENT`, `/VERYSILENT`) never downloads or installs
anything: it stops (non-zero exit code) and logs what is missing.

Uninstall from Settings > Apps. Your voicebanks, generated tracks and settings are left in place.
Installing a newer version over the old one upgrades it and keeps everything of yours.

## First run

1. Start **BLT Music Generator** from the Start menu.
2. **Voices.** BLT has its own voices folder, `Documents\BLT Music Generator\Voices` (Setup creates it; Updating
   and uninstalling never touch it). Press *Add voice…* in the Voices section and choose a voicebank's `.zip` file or
   its folder: BLT copies it in and lists it. You can also drop voicebank folders into the voices folder yourself
   (*Open* shows it), inside folders of your own such as `English\` or `Japanese\`, and press *Refresh*. On the
   command line: `barbershop-tracks voices add FOLDER-OR-ZIP` and `barbershop-tracks voices list`. Voicebanks you already have, even ones OpenUtau uses, are added the same way (BLT copies them; it
   never needs OpenUtau, and *Browse…* can still point BLT at another folder). OpenUtau itself is not needed.
3. **Score.** Press *Choose score…* (or drop the file on the window).
4. **Parts.** Tell BLT which line of the score is Tenor, Lead, Baritone and Bass (*Suggest voices* fills in
   likely ones from the part names; you confirm them).
5. **Singer.** Choose the voicebank for the parts (the same one for all, or one per part).
6. **Lyrics.** As is usual in barbershop scores, a part with no lyrics of its own sings what the Lead sings (it
   holds the vowel when it moves under a held word). *Review lyrics…* lists those notes as "Follows the Lead" and
   lets you override any of them. Notes the Lead is not singing under (for example a part's own "oom") have no
   words to follow: you decide what they are sung to, and generating stays disabled until you have. The
   window says why. You can switch the convention off in *Advanced…*.
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

## Installing on macOS

> **Experimental.** The macOS build is made and tested by CI on GitHub's Mac runners, but nobody has run it on a real Mac yet,
> and it is neither signed nor notarised (see [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md)). Please report what you see.

1. Download the disk image for your Mac: `BLT-Music-Generator-<version>-macos-arm64.dmg` (Apple silicon: M1 and later) or
   `...-macos-x64.dmg` (Intel). Check it against `SHA256SUMS-macos-<arch>.txt` published with it:
   `shasum -a 256 BLT-Music-Generator-*.dmg`.
2. Open the disk image and drag **BLT Music Generator** onto **Applications**.
3. The app is not signed with an Apple Developer ID, so macOS blocks the first start. Open it once with **right-click
   (Control-click) > Open**, then **Open** in the dialog. On recent macOS releases the dialog has no Open button; then try to start
   the app, open **System Settings > Privacy & Security**, and press **Open Anyway**. If macOS says the app is "damaged", it is the
   download flag on an unsigned app; remove it:
   `xattr -dr com.apple.quarantine "/Applications/BLT Music Generator.app"`.
4. Nothing else is needed: no Python, no .NET, no Rosetta (the app is native to the Mac it was built for). Uninstall by dragging
   the app to the Bin; your voicebanks (`~/Documents/BLT Music Generator/Voices`), tracks and settings
   (`~/Library/Application Support/BarbershopLearningTracks`) are left in place.

The first run is as described above, with these differences: BLT's voices folder is `~/Documents/BLT Music Generator/Voices` (BLT
creates it when it first needs it; *Open* in the Voices section shows it in the Finder); a voicebank inside a pack folder is known by
its path with a slash (`English/Bennett`); for MP3 install FFmpeg yourself (for example `brew install ffmpeg`; BLT also looks in
`/opt/homebrew/bin` and `/usr/local/bin`, which a Finder-started app does not have on its PATH) and choose it with *Choose FFmpeg…* if
BLT does not find it.

The command line program is inside the app:

```
"/Applications/BLT Music Generator.app/Contents/MacOS/blt" selftest
```

It builds a tiny score and a synthetic test voice and generates the 13 files; it prints "selftest passed" when the installation is sound.
`blt diagnostics`, or *Help > Copy diagnostics*, tells you where BLT found everything.

Problems: see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
