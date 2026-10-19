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

To use the installed app: Windows 10/11 x64, **or macOS 12 or later (Apple silicon or Intel; experimental, see below)**,
and a voicebank of your own (nothing else; MP3 also needs an FFmpeg you install). To develop: Python 3.12 and a .NET 8 SDK
(render host), on Windows plus Inno Setup 6 (installer) and the Visual Studio C++ build tools, on macOS plus the Xcode
command line tools and CMake.

**macOS status.** The macOS app is built and tested by CI on GitHub's Apple-silicon and Intel runners (checks, the render host
with a generated test voicebank, the packaged app in a stripped environment). It is **unsigned and not notarised**, and no
person has yet run it on a real Mac: see [docs/KNOWN-LIMITATIONS.md](docs/KNOWN-LIMITATIONS.md).

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

## Development setup and checks (macOS)

```bash
python3.12 -m venv .venv && . .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
host/build.sh                     # the render host (pinned OpenUtau, BLT's own libworldline.dylib via clang and CMake)
python host/verify_host.py research-output/host/build research-output/openutau-src
pytest -m integration tests/integration     # real host, generated test voicebank (MP3 tests need ffmpeg)
```

## Build the macOS app

```bash
python -m pip install -r packaging/requirements-build-macos.txt
python -m pip install -e . --no-deps
python packaging/build_macos.py
```

Builds `BLT Music Generator.app` and an unsigned `BLT-Music-Generator-<version>-macos-<arch>.dmg` for the kind of Mac it runs on
(arm64 or x64) under `research-output/release-macos`, audits every file in the app against the component tables, and smoke-tests
the app. Signing and notarisation are off unless `--sign-identity` / `--notarize` are given; the project has never used them.

## Credits

BLT is a front end for work done by others. The full list of bundled components and their licences is
`NOTICES.txt` (installed beside the program and in the Start menu; how it is made and checked is in
[docs/dependency-audit.md](docs/dependency-audit.md)). In particular:

* **[OpenUtau](https://github.com/stakira/OpenUtau)** (MIT, by its contributors) is the singing engine. BLT's render
  host is built from OpenUtau 0.1.565 with a small, documented set of patches that remove parts BLT cannot
  redistribute ([docs/openutau-integration.md](docs/openutau-integration.md)). Its native resampler `worldline`
  builds on the **[WORLD vocoder](https://github.com/mmorise/World)** by Masanori Morise (BSD-3-Clause) and other
  libraries named in the notices.
* **CMUdict** (Carnegie Mellon University) is the English pronunciation dictionary, embedded in OpenUtau.
* **[Qt](https://www.qt.io/) and [Qt for Python (PySide6)](https://doc.qt.io/qtforpython-6/)** (The Qt Company,
  LGPL-3.0) draw the window; they stay separate, replaceable libraries.
* **Python**, **NumPy**, **mido**, **defusedxml**, **platformdirs**, **PyInstaller** and the **.NET** runtime,
  with the NAudio, Concentus, Newtonsoft.Json, YamlDotNet and other libraries listed in the notices.
* **[Inno Setup](https://jrsoftware.org/isinfo.php)** builds the installer; it is not part of what is installed.
* Scores can be prepared with **MuseScore**, and recognised from PDF with **Audiveris**; MP3 output uses
  **FFmpeg**. These are programs you install yourself; BLT ships none of them.

**Voices.** BLT includes no voicebank. The voice the developer tested with is **Bennett (ENG)** by
**[VoCreatures](https://vocreatures.carrd.co)**: if you use Bennett, the terms ask you to credit him as
"Bennett from VoCreatures" with a link to VoCreatures, not to redistribute the voicebank and not to use its audio to
train AI models. Respect the licence of whichever voicebank you use and credit its author in what you publish.

## Repository rules

Generated audio, OpenUtau projects, voicebanks, FFmpeg binaries and copyrighted
arrangements are never committed. `scripts/check_no_audio_in_repo.py` enforces this in CI.
