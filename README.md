# BarbershopLearningTracks

Desktop app that generates four-part barbershop learning tracks (Tenor, Lead, Baritone,
Bass) from a MusicXML file exported from MuseScore.

Status: **M1 scaffold.** There is no parsing, synthesis or mixing yet. See
[docs/architecture.md](docs/architecture.md) and
[docs/openutau-integration.md](docs/openutau-integration.md).

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
