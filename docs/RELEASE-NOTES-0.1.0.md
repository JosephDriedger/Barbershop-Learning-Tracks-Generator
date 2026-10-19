# BLT Music Generator 0.1.0

**Pre-release: Windows 10/11 x64, and an experimental macOS build.** Not for public distribution until the open licensing blockers in
[dependency-audit.md](dependency-audit.md) and the acceptance gates in [m12-acceptance.md](m12-acceptance.md)
and [m12-verification.md](m12-verification.md) are cleared; it has not been through the licensing review, the
English-voicebank listening test or a clean-PC install test, and the installer is unsigned (Windows SmartScreen will
warn). The macOS disk images (`...-macos-arm64.dmg` for Apple silicon, `...-macos-x64.dmg` for Intel Macs) are unsigned and not
notarised, so macOS blocks the first start until you open them with right-click > Open ([INSTALL.md](INSTALL.md#installing-on-macos)); they
were built and tested by automated runners only and have not been tried on a real Mac by a person.

## What it does

From a four-part (TTBB) MusicXML score exported from MuseScore, BLT makes 13 learning tracks as WAV (or MP3 with
your FFmpeg): the full quartet and, for Tenor, Lead, Baritone and Bass, a *predominant* track (that part forward),
a *solo* track and a *without* track. The singing is rendered by OpenUtau's engine (release 0.1.565, built
unmodified, run headless by BLT) with a voicebank you provide; the mix is deterministic and described in a
`manifest.json` with checksums.

## In this build

* A per-user Windows installer; no Python, .NET or administrator rights needed. On macOS: a disk image with the app (drag to Applications).
* GUI and command line (`blt.exe`: `generate`, `check`, `lines`, `export`, `selftest`, `diagnostics`).
* Self-check (`blt selftest`) and diagnostics for support.
* BLT's own voices folder, `Documents\BLT Music Generator\Voices`: *Add voice…* (or `barbershop-tracks voices add`) copies a
  voicebank from a `.zip` or a folder into it. OpenUtau is not needed.
* Upgrades in place; uninstall keeps your voicebanks, tracks and settings.

## Not in this build

See [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md): unsigned installer, no bundled FFmpeg or voicebank, two
renderers only, no in-app playback, English-voicebank acceptance outstanding.

## Third-party software

Bundled components and their licences are listed in `NOTICES.txt` (installed beside the program, and in the Start
menu). Qt and PySide6 are used under the LGPL-3.0 as separate replaceable libraries. See the audit for the
unresolved items.

## Credits

Built on [OpenUtau](https://github.com/stakira/OpenUtau) (MIT), the [WORLD vocoder](https://github.com/mmorise/World) by
Masanori Morise, CMUdict (Carnegie Mellon University), [Qt for Python](https://doc.qt.io/qtforpython-6/) (LGPL-3.0),
Python, NumPy and the other components listed in `NOTICES.txt`. The corresponding source of the LGPL components is the
`...-corresponding-source.zip` attached to this release. No voicebank is included. The developer tested with Bennett (ENG) by
[VoCreatures](https://vocreatures.carrd.co) (credit "Bennett from VoCreatures" if you use it; do not redistribute it or use it to
train AI). More in the README.

## Installing and troubleshooting

[INSTALL.md](INSTALL.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Verify the download against `SHA256SUMS.txt`
(`Get-FileHash <file> -Algorithm SHA256`; on a Mac `shasum -a 256 <file>` against `SHA256SUMS-macos-<arch>.txt`).

## Checksums

Filled in by the release process from `SHA256SUMS.txt` (see `release-info.json`); none is published yet.
