# M14: implementing the release-compliance decisions

Status: **implemented and verified locally. Every artifact is still NOT FOR RELEASE.** Three blockers remain open
(below). Nothing was uploaded or published, no release was created, and BLT's own code stays Apache-2.0
(`Copyright 2026 Joseph Driedger`).

> **Update (M15, [m15-report.md](m15-report.md)):** the English "plus" dictionary is no longer in the build (excluded, verified by reflection and by a byte search of the whole package), so decision 3 is resolved by exclusion and only two licensing blockers remain; the dictionary figures quoted below were replaced by reproducible ones ([g2p-plus-provenance.md](g2p-plus-provenance.md)); the replacement spline's provenance statement was corrected ([review/worldline-spline-review-packet.md](review/worldline-spline-review-packet.md)).

## The five decisions

| # | Decision | Result | State |
|---|---|---|---|
| 1 | BLT-maintained `worldline.dll` without the GPL `tk::spline` | BLT builds it (`host/native/`, MSVC + CMake + Ninja, `/Brepro`) from the pinned sources with its own natural cubic spline. Link map and DLL contain no `tk::spline` symbol; the 17 exports are the ones OpenUtau.Core calls; spline parity max difference 1.6e-14; all 13 rendered WAVs byte-identical to the stock DLL's (`tests/golden/selftest_audio.json`). Provenance and the author's disclosure: [worldline-provenance.md](worldline-provenance.md) | **Blocker stays open** until an independent source/licensing review is documented |
| 2 | Patched OpenUtau.Core without Voicevox, Vogen data and non-English dictionaries | `host/patch_openutau.py` makes the patch; `host/verify-host.ps1` (reflection, runs in every package build and CI) checks: no Voicevox type in Core or Plugin.Builtin, English dictionaries byte-identical to the pinned source, every other dictionary and all Vogen data empty, CREPE (MIT) model present. Reported revision `a60ca58…+blt-patched`. All host-driven tests pass; audio identical to the stock build | **Resolved by evidence** (no LGPL code remains in the DLL) |
| 3 | English "plus" dictionary | Not removed, not approved. Dependency traced: only Arpasing+ and English CpV use it; the default phonemizer, Arpasing and every other English phonemizer BLT can run use the CMUdict pack. 120,887 of 420,422 entries have no stated source. Options and the draft upstream issue: [g2p-plus-provenance.md](g2p-plus-provenance.md), [upstream-g2p-plus-issue.md](upstream-g2p-plus-issue.md) | **Explicit blocker.** The upstream issue is a draft, **not sent** |
| 4 | Qt/PySide6 materials on the BLT GitHub release | `packaging/compliance.py` assembles `BLT-Music-Generator-<version>-corresponding-source.zip` (70.2 MB): the Qt Project's own `qtbase-everywhere-src-6.11.2.tar.xz` and `pyside-setup-everywhere-src-6.11.2.tar.xz` (SHA-256 recorded; the qtbase MD5 equals Qt's published `md5sums.txt`), BLT's source at HEAD, `WRITTEN-OFFER.txt`, `RELINKING.md`, the LGPL/GPL texts, `MANIFEST.json`. `packaging/replaceability-test.ps1` (run by every build) proves the libraries are separate files that the program loads from disk and that BLT neither pins nor checks. NOTICES.txt now points to the release page and the Qt Project. Output: `research-output/release/compliance/`, not uploaded | **Blocker stays open** until the zip is attached to the release it accompanies and a person reviews the arrangement |
| 5 | Visual C++ runtime, Option A | No Microsoft runtime file is in the package; the build fails if one is (`packaging/runtime_copies.py`). Setup detects Microsoft's runtime (registry, 14.44 or newer), offers a signed download from Microsoft or a `vc_redist.x64.exe` the user brings (offline), checks Microsoft's Authenticode signature before running it, and stops a silent install with a log line. The app re-checks before rendering (`VC_RUNTIME_MISSING`, `blt diagnostics`). NumPy's hash-renamed `msvcp140-<hash>.dll` is created at install as a copy of the PC's own `msvcp140.dll` | **Resolved** for redistribution; dialogs not yet exercised on a PC that lacks the runtime |

### LGPL position for Qt/PySide6 (what was and was not checked)

* LGPL-3.0 section 4(d)(1): use a suitable shared-library mechanism so the user can replace the library. Met: the Qt and PySide6 DLL/PYD
  files are loose files in the one-folder install, loaded at run time; the executables do not contain them.
* Corresponding source of the library as distributed: the Qt Project's archives, byte for byte (unmodified: BLT makes no change to Qt or PySide6).
* Installation information / relinking: `RELINKING.md` (which files, how, how to check). Tested with a *different file* in place of
  `Qt6Widgets.dll`, **not with a Qt build modified by someone else**.
* Written offer: three years, via the project's GitHub issues, in `WRITTEN-OFFER.txt` and NOTICES.txt.
* Not checked and **not legal advice**: whether hosting the archives on BLT's GitHub release (rather than a pointer to Qt alone) is the
  arrangement a lawyer would choose; the owner asked for a person to review it. The release URL in NOTICES.txt does not exist until a release does.

## A defect found on the way (fixed)

M12 pruned `onnxruntime.dll` as "neural renderer only". The English phonemizers' neural g2p fallback (words not in CMUdict) uses it, and the
test PC only worked because Windows ships its own copy in System32; on Windows 10 that fails. The shipped 1.16.3 DLL (MIT, with its
third-party notices) is restored, and `blt-render-host --g2p-check` plus a smoke-test check prove the DLL beside the host is the one loaded.

## Verification run (this PC, 2026-10-13)

| Check | Result |
|---|---|
| ruff, ruff format, mypy (strict, 278 files) | clean |
| `pytest tests/unit` | 2559 passed |
| Full `pytest tests` against the published self-contained host (`BLT_HOST_DIR`, includes the golden-audio test and the real-host synthesis tests) | 2607 passed, 5 skipped (no ALYS voicebank configured; no FFmpeg) |
| Native audio regression | spline parity 864 cases / 830,304 values, max 1.6e-14; 13 of 13 WAV hashes equal the golden set |
| `host/verify-host.ps1` | ok |
| Package build (`packaging/build.ps1`): inventory of all files against `components.json`, 3 blockers | ok |
| Package smoke tests, plain and non-ASCII paths (diagnostics, GUI start, selftest with 13 WAVs, host-copy reuse, g2p fallback, folder unchanged) | passed |
| Replaceability test | passed |
| Installer test: silent install stops without the runtime; no Microsoft runtime file installed; install + smoke on the installed copy; upgrade (99.0.0) keeps user data; uninstall | passed |

## Remaining blockers and gates

1. **`worldline.dll`**: independent source/licensing review of `host/native/patched/natural_spline.h` (92 lines) by someone who has not read `tk::spline`.
2. **English "plus" dictionary**: upstream answer (draft issue ready, awaiting the owner's go-ahead), or empty/CMUdict-only replacement in the patch.
3. **Qt/PySide6**: publish the bundle with a release, then a person reviews the LGPL arrangement.
4. Not licensing but required before release: English voicebank acceptance ([m12-acceptance.md](m12-acceptance.md)), a clean-machine run
   (including the installer's Visual C++ download / file-picker dialogs, which only the silent path has exercised), code signing decision.

Also noted: the source bundle is made from `git archive HEAD`; it must be built from the release commit with a clean tree.
The installer in `research-output/release/artifacts/` is a local build of the working tree (unsigned, NOT FOR RELEASE).
