# BLT Music Generator

Desktop app that generates four-part barbershop learning tracks (Tenor, Lead, Baritone,
Bass) from a MusicXML file exported from MuseScore.

Status: **pre-release (0.1.0), not cleared for public release.** The whole pipeline works: score loading,
readiness checks, quartet MIDI, headless OpenUtau rendering, deterministic mixing into the 13 tracks, a
command line and a GUI, and a per-user Windows installer. Open before any release: licensing blockers in
[docs/dependency-audit.md](docs/dependency-audit.md) and musical acceptance with a real English voicebank
([docs/m12-acceptance.md](docs/m12-acceptance.md)). See [docs/INSTALL.md](docs/INSTALL.md) to install and
[docs/KNOWN-LIMITATIONS.md](docs/KNOWN-LIMITATIONS.md) for what is not done.

## Names: product versus technical identifiers

The product name is **BLT Music Generator**. The technical identifiers are compatibility contracts,
not branding, and keep their established spelling: the Python package `barbershop_tracks`, the
command `barbershop-tracks`, the distribution name, and the schema/ownership identifiers written
into handoff packages (`barbershop-tracks.handoff/1`, `barbershop-tracks.readiness/1`, ...).
Renaming them would break installs and make existing packages unrecognisable to `--overwrite`.

## Requirements

To use the installed app: Windows 10/11 x64 and a voicebank of your own (nothing else; MP3 also needs an FFmpeg
you install). To develop: Windows, Python 3.12, a .NET 8 SDK (render host), Inno Setup 6 (installer).

## Development setup (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Checks

```powershell
python scripts/check_no_audio_in_repo.py
ruff check .
ruff format --check .
mypy
pytest
```

## Run

```powershell
barbershop-tracks --version      # CLI
barbershop-tracks-gui            # GUI (add --smoke-test to open and close immediately)
python -m barbershop_tracks      # GUI
```

## Build the Windows package

```powershell
python -m pip install -r packaging/requirements-build.txt
python -m pip install -e . --no-deps
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/build.ps1
```

See [docs/m12-packaging.md](docs/m12-packaging.md). Nothing is uploaded or published by the build.

## Repository rules

Generated audio, OpenUtau projects, voicebanks, FFmpeg binaries and copyrighted
arrangements are never committed. `scripts/check_no_audio_in_repo.py` enforces this in CI.
