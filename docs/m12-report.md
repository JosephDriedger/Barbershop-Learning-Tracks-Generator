# M12 completion report: Windows packaging, licensing, installation verification

Status at the end of M12: **an installable, tested, unsigned Windows installer exists; it must not be released.**
Five licensing blockers are open, English-voicebank acceptance has not been run, and the installer has not been
tried on a pristine machine. Nothing was published or uploaded.

(Numbers below are from the final local build, commit `2dbdcd6` as recorded in `release-info.json`.)

## 1. Packaged layout

See [m12-packaging.md](m12-packaging.md). One-folder PyInstaller application (`BLT Music Generator.exe` GUI,
`blt.exe` CLI, `_internal\`), the self-contained .NET render host in `host\`, `NOTICES.txt`, `LICENSE.txt` and
`licenses\`. 211.7 MB on disk in 454 files (render host 114.8 MB, Python/Qt/NumPy 86.0 MB, notices 1.3 MB). Writable data lives outside the program folder (per-user
`%LOCALAPPDATA%\BarbershopLearningTracks`, registry preferences); a run leaves the program folder unchanged
(checked byte-for-byte).

## 2. Installer technology and size

Inno Setup 6, per-user by default (no administrator rights), Start-menu group, optional desktop shortcut, in-place
upgrade, uninstall that keeps user data. 77.0 MB (77,010,196 bytes), LZMA2. Unsigned.

## 3. How the .NET host is published

`dotnet publish -r win-x64 --self-contained`, runtime pinned to 8.0.31, no single-file/trimming/AOT/ReadyToRun,
debug symbols off, then pruned (`host/prune.txt`: NetMQ + dependencies, native ONNX Runtime, foreign-platform
natives, createdump). No .NET installation is needed. Reasons and rejected alternatives in
[m12-packaging.md](m12-packaging.md). Publishes of the same BLT commit were byte-identical (235/235 files).

## 4. Licensing audit and blockers

Complete inventory of every file in the package (`packaging/components.json`, enforced per file by
`packaging/inventory.py`), generated tables in [dependency-audit.md](dependency-audit.md), distributable
`NOTICES.txt` + `licenses\`. FFmpeg is not bundled; no voicebank is bundled.

Open blockers (the build marks every artifact "NOT FOR RELEASE" while any remains):

1. **`worldline.dll`**: compiles GPL-2.0 `tk::spline` and `libpyin`, which has no licence. Needs upstream permission,
   a rebuild without them, or GPL-2.0 compliance.
2. **`OpenUtau.Core.dll`**: Voicevox classes are "partially based on" the LGPL-3.0 VOICEVOX engine (handling drafted,
   needs confirmation); embedded g2p and Vogen data have no licence statement.
3. **PySide6/Qt LGPL-3.0 statement**: drafted in `NOTICES.txt`, needs human review (or a commercial licence).
4. **Visual C++ runtime files** shipped app-local: redistribution terms not reviewed.
5. **BLT's own copyright holder** is not named in `LICENSE`.

Resolved with evidence during the audit: Qt third-party attributions, OpenBLAS/GCC runtime (NumPy wheel inventory),
Universal C Runtime (no longer shipped), Plugin.Builtin notices, SimpleEnunu/Deque/Merlin notices.

## 5. Clean-machine results

* **Automated, stripped environment (PATH = Windows folders only, no DOTNET/PYTHON/BLT variables, no
  `BLT_HOST_DIR`)**: 20 of 20 checks passed in two scenarios (plain paths; spaces and non-ASCII characters in the install path, data, temp, profile and output folders): `blt --version`; GUI executable starts and builds its window; `blt selftest` through the bundled host writes 13 WAVs with a verified manifest (first launch about 3 to 4 s, which includes copying the host); the second launch reuses the host copy (same directory and timestamps, about 1.1 s); the program folder is byte-for-byte unchanged by running.
* **Installer test (per-user silent install, Start-menu launch, installed-copy smoke test, upgrade, uninstall)**:
  46 of 46 checks passed on this machine as the current user, installing into a folder with spaces and non-ASCII characters: silent per-user install without administrator rights; uninstall entry in HKCU; Start-menu shortcut present and pointing at the program; no desktop shortcut by default; **launching the Start-menu shortcut opened the real main window**; the smoke test passed on the installed copy; upgrade to a newer installer (99.0.0) in place; a stale file of the old version removed; a file the user added to the program folder kept; user voicebank and output markers untouched; uninstall removed program, shortcut, registry entry and the private runtime/scratch/cache folders and kept voicebank, tracks and preferences.
* **Pristine machine / Windows Sandbox: NOT RUN.** The development PC is Windows 11 Home, which has no Windows
  Sandbox, and no VM was available. The kit (`packaging/clean-machine/`) and checklist
  ([m12-verification.md](m12-verification.md)) are ready for someone with a clean machine. A real non-ASCII user
  account was not created either; non-ASCII/space paths were exercised in every folder BLT uses, which found and fixed one
  real defect (console output crash).
* **CI**: a hosted `windows-latest` runner builds the package from pinned inputs, audits it, smoke-tests it, runs the
  host tests against the pruned self-contained host, and installs/upgrades/uninstalls it. All three jobs (`checks`, `render-host`, `package`) were green on `2dbdcd6`.
  (A hosted runner has Python and .NET installed system-wide; the stripped environment is what excludes them.)

## 6. Real English voicebank

**Not verified.** No English voicebank is available on the development machine and none was downloaded. The
protocol and the record template are in [m12-acceptance.md](m12-acceptance.md). Supplementary technical result with the
only real voicebank present (ALYS DB002 FRA, French, user-installed): the packaged `blt.exe`, run from a stripped environment with no `BLT_HOST_DIR`,
rendered a four-part test score (every note sung to "la") through the bundled host and produced 13 WAV files
(9.6 s each, 44.1 kHz mono) whose SHA-256 values match the manifest and none of which is silent, in about 10 s.
`blt diagnostics` found the bundled host "next to the application" and listed the voicebank as one voice. This is not English intelligibility evidence.

## 7. Install, upgrade and uninstall behaviour

Verified by `installer-test.ps1`: installs per user to `%LOCALAPPDATA%\Programs\BLT Music Generator` (or a chosen folder) without elevation; upgrades in place and clears only program-owned folders (`_internal`, `host`, `licenses`) first; uninstalls the program and this program's private runtime, scratch and cache folders; never removes voicebanks, generated tracks, `config.json` or the registry preferences; tells the user where those are. Old host copies from earlier versions are pruned after a day idle. Details and the SmartScreen/code-signing position: [m12-packaging.md](m12-packaging.md).

## 8. Release artifacts and checksums

Built by `packaging/build.ps1` into `research-output\release\artifacts` (git-ignored; nothing uploaded):

```
28f9671d597d2b0054e02b47b0297f82c2f3c0fe24d9a67357f8cfa177e57c81 *BLT-Music-Generator-0.1.0-Setup.exe
a7a5bd00d932d881f4e8ab7c125cc6e88534b99e7381be463ecb3ed0d457691e *NOTICES.txt
e9cec4f9b2f83e7c10b95852d1cff5cea97adb49a808ff2498e3506688f2da84 *inventory.json
```

plus `release-info.json` (version, commit, OpenUtau commit, runtime, tool versions, blockers, `signed: false`), `RELEASE-STATUS.txt` ("NOT FOR RELEASE: 5 open licensing blocker(s) ...") and `inventory.json` (SHA-256 of all 454 files). The installer is not bit-for-bit reproducible, so this checksum identifies one build; compare `inventory.json` when checking a rebuild. The docs for users are [INSTALL.md](INSTALL.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md) and the draft [RELEASE-NOTES-1.0.0.md](RELEASE-NOTES-1.0.0.md).

## 9. Outstanding risks

* **Licensing** (section 4): `worldline.dll` is the serious one; the OpenUtau.Core LGPL/data questions and the Qt LGPL statement need a person or upstream's answer; the app-local VC++ runtime and BLT's own copyright holder need decisions.
* **Musical quality unknown**: no English voicebank test; intelligibility, melismas and predominant clarity are unverified.
* **No pristine-machine run, no real non-ASCII account, no user test** (the machine is Windows 11 Home).
* **Unsigned**: SmartScreen warnings and possible antivirus false positives; users must verify checksums.
* **Only two renderers**; MP3 depends on a user-installed FFmpeg; no in-app playback.
* **A real defect only a real voicebank showed**: multi-pitch voicebanks (such as ALYS) were listed as one voice per pitch folder in the GUI; fixed (a folder with a character file is now one voicebank) and tested. Other voicebank layouts will surface more such issues during the English acceptance run.
* **Leftovers by design**: `config.json` and the registry preferences remain after uninstall (so does everything the user owns); the 115 MB host copy is removed.

## 10. Release-readiness recommendation

**Not ready for a public release.** Suitable for internal acceptance testing now. To release: clear the five
blockers in section 4, run the clean-machine checklist and the English acceptance protocol, sign the
installer (or accept and document SmartScreen warnings), then build with `-FailOnBlockers` and publish
deliberately. No release has been published, and nothing has been uploaded to GitHub Releases or any other
service.

## M12g refinements done

Diagnostics (`blt diagnostics`, Help > Copy diagnostics), Help > Third-party notices, the Advanced renderer list
limited to what the shipped host can run, first-run window size fitted to scaled screens, the failed/cancelled
step marked in the progress list, host-copy pruning after upgrades, and the install/first-run/troubleshooting/limits docs.
Existing from M11: plain-language explanations for missing FFmpeg and missing voices. **Not done** (kept out of
scope): track playback or preview in the app, a first-run wizard, a usability test with real users.
