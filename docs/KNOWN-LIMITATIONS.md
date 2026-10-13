# Known limitations (0.1.0)

Things that are not done, not verified, or deliberately restricted. Nothing here is hidden elsewhere.

## Release status

* **Not cleared for public release.** The licensing audit ([dependency-audit.md](dependency-audit.md)) has three open
  blockers: BLT's own `worldline.dll` build needs an independent source review of its replacement spline
  ([worldline-provenance.md](worldline-provenance.md)); the English "plus" dictionary has additions of unknown origin
  ([g2p-plus-provenance.md](g2p-plus-provenance.md)); and the Qt/PySide6 source bundle has been prepared but not published,
  nor legally reviewed ([m14-compliance-report.md](m14-compliance-report.md)). Builds are for internal testing.
* **Visual C++ Redistributable is a prerequisite.** BLT does not ship Microsoft's runtime. The installer's download and
  file-picker dialogs have not been tried on a PC that really lacks the runtime; only the silent path is tested.
* **Not verified with an English voicebank.** The musical acceptance in [m12-acceptance.md](m12-acceptance.md) has
  not been run; whether English lyrics are intelligible with a given voicebank, how melismas sound, and whether the
  predominant tracks are clear enough are all unknown. Only a generated sine-wave voicebank and a French voicebank
  (technical checks) were used.
* **Not verified on a pristine machine or by users.** The clean-machine check and a usability test with
  non-developers have not been done ([m12-verification.md](m12-verification.md)). Automated tests ran in a stripped
  environment on the development PC.

## Installation and trust

* The installer and executables are **unsigned**: SmartScreen warns, the publisher shows as unverified, and some
  antivirus products may flag PyInstaller programs.
* Windows 10/11 **x64** only. Not tried on ARM64 (x64 emulation).
* Footprint: about 212 MB installed, plus about 115 MB of private working files per user after the first run
  (the singing engine's copy; old versions' copies are removed after a day).
* A user name with non-ASCII characters was only emulated (all folders BLT uses placed under such a path).

## Features

* **Renderer:** WORLDLINE-R only. CLASSIC renders but its audio runs a few tens of milliseconds past the performed length
  and the mix check rejects it (`MIX_STEM_TOO_LONG`, seen with a real voicebank), so it is not offered. The neural renderers (ENUNU, Vogen, DiffSinger, VOICEVOX) are
  not in this build because their native runtime is not included.
* **MP3 needs an FFmpeg you install**; none is bundled. WAV needs nothing.
* **No playback or preview** inside the app yet (tracked separately). You open the output folder and play the files elsewhere.
* One score at a time; no batch mode in the GUI (the command line scripts well).
* Voicebanks are never included or downloaded; you must supply one and respect its licence.
* Display scaling (125 to 200 %) and screen readers were designed for (accessible names, Qt high-DPI) but not
  systematically tested.
* Unusual scores (more than four parts, very long songs, exotic MusicXML) behave as documented in
  [musicxml-support.md](musicxml-support.md); BLT refuses rather than guesses when a score is not ready.
