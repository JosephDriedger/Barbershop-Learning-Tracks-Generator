# BLT Music Generator

Desktop app that generates four-part barbershop learning tracks (Tenor, Lead, Baritone,
Bass) from a MusicXML file exported from MuseScore.

Status: **in development.** MusicXML loading, the performed score model, readiness checks
(`check`, `lines`) and the deterministic quartet MIDI handoff (`export`) work from the command line;
OpenUtau interoperability is being researched (M6) and there is no synthesis or mixing yet. See
[docs/architecture.md](docs/architecture.md) and
[docs/openutau-integration.md](docs/openutau-integration.md).

## Names: product versus technical identifiers

The product name is **BLT Music Generator**. The technical identifiers are compatibility contracts,
not branding, and keep their established spelling: the Python package `barbershop_tracks`, the
command `barbershop-tracks`, the distribution name, and the schema/ownership identifiers written
into handoff packages (`barbershop-tracks.handoff/1`, `barbershop-tracks.readiness/1`, ...).
Renaming them would break installs and make existing packages unrecognisable to `--overwrite`.

## Requirements

- Windows, Python 3.12
- FFmpeg installed separately (needed from milestone M5 onward)
- OpenUtau and an English voicebank (needed from milestone M6 onward)

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

## Repository rules

Generated audio, OpenUtau projects, voicebanks, FFmpeg binaries and copyrighted
arrangements are never committed. `scripts/check_no_audio_in_repo.py` enforces this in CI.
