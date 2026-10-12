# BLT Music Generator 0.1.0 (draft release notes, not released)

**Pre-release. Not for public distribution** until the open licensing blockers in
[dependency-audit.md](dependency-audit.md) and the acceptance gates in [m12-acceptance.md](m12-acceptance.md)
and [m12-verification.md](m12-verification.md) are cleared.

## What it does

From a four-part (TTBB) MusicXML score exported from MuseScore, BLT makes 13 learning tracks as WAV (or MP3 with
your FFmpeg): the full quartet and, for Tenor, Lead, Baritone and Bass, a *predominant* track (that part forward),
a *solo* track and a *without* track. The singing is rendered by OpenUtau's engine (release 0.1.565, built
unmodified, run headless by BLT) with a voicebank you provide; the mix is deterministic and described in a
`manifest.json` with checksums.

## In this build

* A per-user Windows installer; no Python, .NET or administrator rights needed.
* GUI and command line (`blt.exe`: `generate`, `check`, `lines`, `export`, `selftest`, `diagnostics`).
* Self-check (`blt selftest`) and diagnostics for support.
* Upgrades in place; uninstall keeps your voicebanks, tracks and settings.

## Not in this build

See [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md): unsigned installer, no bundled FFmpeg or voicebank, two
renderers only, no in-app playback, English-voicebank acceptance outstanding.

## Third-party software

Bundled components and their licences are listed in `NOTICES.txt` (installed beside the program, and in the Start
menu). Qt and PySide6 are used under the LGPL-3.0 as separate replaceable libraries. See the audit for the
unresolved items.

## Installing and troubleshooting

[INSTALL.md](INSTALL.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Verify the download against `SHA256SUMS.txt`
(`Get-FileHash <file> -Algorithm SHA256`).

## Checksums

Filled in by the release process from `SHA256SUMS.txt` (see `release-info.json`); none is published yet.
