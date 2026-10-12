# M12: installation verification

Three different things are verified here, and they are kept apart:

1. **Automated smoke tests** (`packaging/smoke.ps1`, `packaging/installer-test.ps1`, run by CI): the
   package and the installer work without a development environment, using a *generated* test voicebank.
   They prove the installation works. They say nothing about how real voices sound or whether the
   application is pleasant to use.
2. **A clean-machine run by a person** (the checklist below): the gate that decides whether it installs
   and runs on a computer that has never seen this project.
3. **Musical acceptance with a real English voicebank** ([m12-acceptance.md](m12-acceptance.md)).

## 1. Automated checks, and what they are run in

Both scripts run every program with a stripped environment: `PATH` is only the Windows folders (no
Python, no .NET, nothing from a development setup), there is no `DOTNET_ROOT`, no `PYTHON*`, no `BLT_*`
build variable (in particular **no `BLT_HOST_DIR`**: the installed program has to find its own host),
temp/profile/data folders are private, and the source checkout is not involved.

| Check | smoke | installer test |
|---|---|---|
| `blt --version` | yes | via smoke |
| GUI executable starts and builds its window (offscreen) | yes | via smoke |
| `blt selftest`: built-in four-part score + generated voicebank -> bundled host -> **13 WAVs**, manifest SHA-256 and frame counts verified | yes | via smoke |
| Second launch reuses the per-user host copy (same directory, same timestamps) instead of reinstalling | yes | via smoke |
| Program folder byte-for-byte unchanged by running | yes | via smoke |
| Same again with spaces and non-ASCII characters (a Japanese/umlaut user-name-like path) in the install path, data path, temp, profile and output | yes | yes (install path) |
| Per-user silent install, no admin; Start-menu shortcut; uninstall entry in HKCU; no desktop icon by default | | yes |
| Launching the Start-menu shortcut opens the real main window | | yes (not in CI: no -NoGui) |
| Upgrade over an existing install: version replaced, stale file removed, user-added file kept, user data kept | | yes |
| Uninstall: program, shortcut, uninstall entry, runtime/scratch/cache removed; **voicebank, generated tracks and preferences kept** | | yes |

Results of the latest local run are in [m12-report.md](m12-report.md). The scripts exit non-zero on any
failure; CI runs the first and (without the real window) the second.

What the "non-ASCII username" test is and is not: Windows takes the real profile folder from the account,
not from environment variables, so a stripped-environment run cannot *become* a user called "Jörg". The test
puts the install, data, config, temp, score and output folders under such a path (every place BLT
writes). It found one real defect: printing a path with characters outside the legacy code page to a
redirected console raised `UnicodeEncodeError` (fixed: output now substitutes instead of crashing, with a test). A
pristine machine with an account that really has a non-ASCII name remains part of the checklist below.

## 2. Clean-machine check

Needed: a Windows 10/11 x64 machine or VM that has never had Python, .NET, Visual Studio or this
repository installed (Windows Sandbox, a fresh VM, or a spare PC). Windows **Home** editions do not have
Windows Sandbox; a VM or another PC is then needed. (The development machine used for this milestone is Home,
so this gate has **not** been run on a pristine machine; see the report.)

Quickest: on a Pro/Enterprise/Education machine with Windows Sandbox enabled,

```powershell
powershell -ExecutionPolicy Bypass -File packaging\clean-machine\start-sandbox.ps1 -Installer <Setup.exe>
```

starts a sandbox (no network) that records which tools are absent, installs per user, runs `blt selftest`
twice and writes `clean-machine-report.txt` to the results folder. On any other clean machine copy the
installer and `packaging\clean-machine\sandbox-run.ps1` into one folder and run
`powershell -ExecutionPolicy Bypass -File sandbox-run.ps1 -In . -Out .\results`.

Then, by hand, on that machine (a person at the keyboard; tick each):

- [ ] The installer shows the SmartScreen warning (expected, unsigned) and installs after More info > Run anyway.
- [ ] Setup runs without asking for administrator rights; the licence page appears.
- [ ] "BLT Music Generator" is in the Start menu (and on the desktop only if chosen); it starts from there.
- [ ] No message about missing Python, .NET, DLLs or a Visual C++ runtime appears.
- [ ] Help > Copy diagnostics: render host is found without any setting; ffmpeg shows "not found" if not installed.
- [ ] Put a voicebank in `Documents\OpenUtau\Singers` (or choose its folder): it appears in the voice list.
- [ ] Open a TTBB MusicXML score exported from MuseScore; assign the four parts; choose a singer.
- [ ] Resolve any lyric issues in the review dialog.
- [ ] Generate: all stages finish; "Open output folder" opens the output; **13 WAV files** and `manifest.json` are there.
- [ ] Spot-listen: files play in a normal player; the four voices are the right parts; lengths match.
- [ ] Close the app and start it again: the previous folders and window size are remembered; a second generation
      starts quickly (no host re-copy).
- [ ] Install the next version over it: it upgrades in place; your voices, tracks and settings are still there.
- [ ] Uninstall from Settings > Apps: the program, shortcut and entry are gone; your voices and tracks remain.
- [ ] Repeat the install/generate with a Windows account whose user name contains a non-ASCII character and a space.
- [ ] MP3: point BLT at an FFmpeg you installed, tick MP3, generate; MP3 files are written.

Record: Windows edition and build, machine type, who ran it, date, and any deviation. A failure is a bug to fix
before release; "could not run" is reported as *not verified*.

## 3. Usability

The smoke tests above are not a usability test. Nobody other than the developer has used the GUI yet; whether
a barbershop singer can get from a score to 13 files without help is unverified. Suggested: have two or three
non-developers do the checklist's generation steps unaided and note where they hesitate.
