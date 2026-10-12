# M12: Windows packaging and installer

BLT Music Generator is delivered as a per-user Windows installer (`BLT-Music-Generator-<version>-Setup.exe`,
Inno Setup 6) that installs a PyInstaller one-folder application with a self-contained .NET render host.
Nothing else needs to be installed: no Python, no .NET, no Visual Studio, no source checkout, no
environment variables. Voicebanks (and FFmpeg for MP3) are the user's own and are never included.

**Status: the installer is built and verified for internal acceptance only. It must not be published
while the licensing blockers in [dependency-audit.md](dependency-audit.md) are open.** It is unsigned.

## What is installed

```
%LOCALAPPDATA%\Programs\BLT Music Generator\        (per-user default; the user may choose another folder)
  BLT Music Generator.exe        GUI (windowed, starts from the Start menu)
  blt.exe                        command line (console): generate, check, selftest, diagnostics, ...
  _internal\                     Python 3.12 runtime, PySide6/Qt (Core, Gui, Widgets; qwindows, qoffscreen, qico
                                 plugins only), NumPy and its OpenBLAS, the stdlib extension modules
  host\                          the render host: blt-render-host.exe, .NET 8 runtime, OpenUtau.Core 0.1.565,
                                 worldline.dll and the managed dependencies (235 files)
  NOTICES.txt  LICENSE.txt  licenses\      third-party notices and licence texts
```

211.7 MB on disk in 454 files (render host 114.8 MB, Python/Qt/NumPy 86.0 MB, notices 1.3 MB),
73.4 MB as the installer (LZMA2). The program folder is treated as read-only: nothing
writes into it while running (checked by `packaging/smoke.ps1`, which compares the folder before and
after).

Everything that is written lives outside it:

| What | Where | Removed on uninstall |
|---|---|---|
| Working copy of the render host (OpenUtau keeps its cache, prefs and logs beside the exe it runs from) | `%LOCALAPPDATA%\BarbershopLearningTracks\runtime\host-<fingerprint>\` | yes (private, rebuilt on demand) |
| Per-job scratch space | `%LOCALAPPDATA%\BarbershopLearningTracks\staging\` | yes |
| Reproducible render cache | `%LOCALAPPDATA%\BarbershopLearningTracks\Cache\` | yes |
| Settings file | `%LOCALAPPDATA%\BarbershopLearningTracks\config.json` (optional) | **no** |
| Window and option preferences | `HKCU\Software\BarbershopLearningTracks\BLT Music Generator` (QSettings) | **no** |
| Voicebanks | wherever the user keeps them (default discovery: `Documents\OpenUtau\Singers`) | **no**, never touched |
| Generated tracks | the output folder the user chooses | **no** |
| Temporary files | `%TEMP%` (staging uses the data folder, not `%TEMP%`) | n/a |

Old host copies from earlier versions are pruned after an upgrade once they have been idle for a day.

## Finding the host without configuration

`resolve_config` looks for the host in this order: command line / `BLT_HOST_DIR` / config file, then
`<folder of the running exe>\host` (the installed layout), then the development build of a source
checkout. An installed BLT therefore needs no `BLT_HOST_DIR`; `blt diagnostics` (and Help, Copy
diagnostics) shows what was found. The first generation copies the host to the per-user runtime
folder (about 4 s); later launches find the copy complete and reuse it untouched (checked by the smoke
test, which compares the copy's timestamps).

## Decision: how the .NET host is published

`dotnet publish -c Release -r win-x64 --self-contained true` of `host/BltRenderHost`, with
`RuntimeFrameworkVersion` pinned to 8.0.31, debug symbols off, then the files listed in
`host/prune.txt` deleted. Chosen over the alternatives:

* **Framework-dependent** would require the user to install the .NET 8 runtime: rejected (the
  requirement is no .NET installation).
* **Single-file** would extract itself to a temp folder or load from memory, and OpenUtau resolves
  native libraries and data relative to the exe; **trimming / Native AOT** would break OpenUtau's
  reflection-heavy phonemizer and plugin loading; **ReadyToRun** adds size for a start-up gain that is
  small next to rendering. None is worth the risk to rendering behaviour; the layout stays a plain
  folder of DLLs.
* **Pruning** removes only what the supported renderer (WORLDLINE-R) never loads: NetMQ and its
  dependencies (LGPL / unlicensed / MPL, OpenUtau's DAW bridge), the native ONNX Runtime (neural renderers),
  other platforms' natives and `createdump.exe`. The host and backend tests and `blt selftest` run
  against the pruned output, so a removal that breaks rendering fails. The Advanced settings list only
  the renderer this host can run and BLT accepts.

Publishes of the pinned source for the same BLT commit are byte-identical (235 of 235 files, checked here with a
different output folder and a fresh restore); across commits only `blt-render-host.dll` and `.exe` differ, because
the SDK embeds the BLT commit id in them. The frozen application is byte-identical between runs as well, except
`_internal\base_library.zip` (zip timestamps): 107 of 108 files with `SOURCE_DATE_EPOCH` set.

## Python application

`packaging/blt.spec` builds two executables from one analysis (PyInstaller 6.22.3, Python 3.12.10):
`BLT Music Generator.exe` (windowed) and `blt.exe` (console), sharing `_internal\`. One-folder, not
one-file, so the Qt and PySide6 libraries stay separate replaceable files (the LGPL requirement) and
start-up does not unpack ~100 MB each time. Unused Qt libraries, plugins and translations are dropped;
`qwindows` (display), `qoffscreen` (the tests and `--smoke-test`) and `qico` (the icon) are kept
deliberately: dropping `qoffscreen` made the GUI crash on start. OpenSSL's `_ssl` and `libssl` are
excluded (BLT makes no network connections). `packaging/make_version_info.py` writes the Windows
version resource; the icon is original artwork drawn by `packaging/make_icon.py`.

## The installer

Inno Setup 6 (`packaging/installer.iss`), built by `packaging/build.ps1`.

* Per user by default: no administrator rights, installs under `%LOCALAPPDATA%\Programs`. The first dialog
  lets the user choose "all users" instead (then it needs elevation; the data above stays per user).
* Start-menu group with the program and a link to the third-party notices; optional desktop shortcut
  (unchecked); optional launch after installing; uninstall entry in Settings > Apps with the icon.
* Shows the Apache-2.0 licence page; `NOTICES.txt` and `licenses\` are installed.
* **Upgrade** with a newer installer replaces the program in place (same `AppId`); `_internal`, `host`
  and `licenses` are cleared first so no file of the old version lingers. Files the user put in the program
  folder, and everything in the table above marked "no", are not touched. Running instances are offered
  for closing.
* **Uninstall** removes the program and the private runtime, scratch and cache folders, and tells the user
  that voicebanks, generated tracks and settings were left (and where they are).

`packaging/installer-test.ps1` runs install, Start-menu launch, smoke test of the installed copy,
upgrade (with markers for user data, a stale file and a user-added file) and uninstall, and checks every
claim above.

## Code signing and SmartScreen

The installer and the executables are **not signed**; no certificate is available to this project. Consequences:

* Windows SmartScreen shows "Windows protected your PC" for a downloaded unsigned installer; the user has to
  choose More info > Run anyway. A fresh signed installer also starts without reputation, but an unsigned
  one never builds any.
* Some antivirus products flag PyInstaller executables heuristically.
* The installer's "publisher" shows as unverified.

Nothing in the installer, docs or release notes claims that it is trusted; the checksum published with a
release is the only integrity statement. `installer.iss` has a `SignTool` hook (`/DSignToolName=...`) so a
certificate can be applied without script changes, and the executables would need signing before packaging.

## Building

Requirements: Python 3.12 with `packaging/requirements-build.txt` (exact versions audited in
`components.json`), a .NET 8 SDK, Inno Setup 6, Git.

```powershell
python -m pip install -r packaging/requirements-build.txt
python -m pip install -e . --no-deps
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build.ps1
```

Steps: host publish (pinned OpenUtau commit `a60ca58…`, cloned if missing and verified) -> PyInstaller ->
host copied in -> `NOTICES.txt`/`licenses\` written from the audited packages -> **every file audited
against `components.json`** (build fails on an unlisted file, a stale entry or version drift) -> smoke
test -> installer -> `SHA256SUMS.txt`, `release-info.json`, `inventory.json`, `RELEASE-STATUS.txt` in
`research-output\release\artifacts`. `-FailOnBlockers` makes open licensing blockers fail the build
(use it for any build meant to ship). Nothing is uploaded.

Reproducibility: inputs are pinned (OpenUtau commit, runtime pack, Python package versions,
PyInstaller, Inno Setup version recorded). The host publish is byte-identical between runs. The
installer itself is not promised to be bit-identical across runs or machines (the Inno Setup stub embeds
timestamps), so the checksum identifies one build, not a recipe; `inventory.json` lists the SHA-256 of
every file inside it, which is what to compare when checking a rebuild.
