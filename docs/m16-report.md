# M16: remove the unused spline, prepare the external-review and acceptance handoff

Status: **done and verified locally; every artifact is still NOT FOR RELEASE.** Nothing was published, signed or uploaded. **The upstream inquiry was NOT submitted**
(the session's permission system blocked the write to the external repository; details below). One licensing blocker and six sign-offs remain, all of them people's.

## The eight decisions

| # | Decision | Result |
|---|---|---|
| 1 | Submit the upstream inquiry, with questions about the plain pack's `g2p.onnx` | Text finished and stored (`docs/upstream/g2p-inquiry-title.txt`, `g2p-inquiry-body.md`; five questions: provenance, training data, licence, redistribution rights, reproducibility; for the plus pack to @Cadlaxa and for the plain pack's model to @stakira, who added it in `eebdf6cd`). **Not submitted.** `gh issue create` against `openutau/OpenUtau` was denied by the permission system ("external system writes"), and I did not work around it. The command to run is in `docs/upstream-g2p-plus-issue.md`; the record there says "NOT SUBMITTED" |
| 2 | Remove the unused spline functionality; stop if a supported path needs interpolation | **No supported path needs it.** The tension effect, the only user of a spline, is removed (`host/native/effects-no-tension-spline.patch`): `GetTensionCoefficients` returns the neutral envelope. The replacement spline of M13-M15 and its tests are deleted |
| 3 | Confirm the binary contains neither `tk::spline` nor the replacement; update inventory, checks, provenance | `verify_dll.py` fails the build on any mention of "spline", "tk::" or "NaturalCubic" in the link map or the DLL. My separate byte search of the shipped DLL: 0 matches for each, and none of the other host binaries names either. `components.json`, `NOTICES.txt`, the audit tables and `docs/worldline-provenance.md` are updated; the download of the spline library is gone from `prepare.py` |
| 4 | Keep the audio regression tests; add targeted coverage; document what byte-identical output proves | Golden test kept and passing. New: a native test of the effect (7,800 calls, 6.3 million values, all exactly 1.0); `trace_tension.ps1` (62,502 native calls over 58 integration tests on the final build: all tension 0; 45,624 of 45,624 earlier on the build that still had the original path); three host tests (a tension curve is refused, a changed default is refused, a neutral curve renders byte-identically to none). What byte-identical output does and does not prove is in `docs/worldline-provenance.md` section 3 |
| 5 | Complete Qt/PySide6 packet for an independent reviewer; no self-certification | `docs/review/qt-pyside6-review-packet.md` + generated folder and one zip: versions, licences, LGPL obligation table with the open questions, checksums and tag cross-checks, written offer, relinking instructions, replaceability log, wheel metadata and licence files, runtime versions, attribution index, 12 of 12 packaged files identical to their wheels' hashes. BLT states plainly that it has not concluded the arrangement satisfies the LGPL |
| 6 | Concise handoff for an external tester | `docs/acceptance/HANDOFF.md` (six checks: clean install, missing runtime, English singing, upgrade, uninstall, user data kept) + the tester kit assembled by `packaging/tester_kit.ps1`: installer, an upgrade-test installer of the same program (0.1.1), checksums, the instructions, `Collect-Environment.ps1`, `Check-UserData.ps1` |
| 7 | Keep every gate active; do not publish, sign or upload | Done; see "Gate" below |
| 8 | Full checks | Below |

## Problems with the program found and fixed (beyond the decisions)

1. **The same score generated twice gave different bytes.** OpenUtau reuses rendered phrases from a 16-bit cache; a reused phrase differs from a fresh render by one
   least-significant bit (measured: 105,832 of 105,841 samples of a stem). The host now discards cached phrases before it renders (cost: a repeat generation re-renders everything).
   Regression test included.
2. **A race when two BLT processes start together on a fresh install**: one could move the other's just-finished host copy away (`HOST_INSTALL_FAILED`). It showed up as one
   flaky failure of `test_concurrent_first_installs...` in a full run. Fixed, with a deterministic test that fails without the fix.
3. **Naming an engine this version lacks** (Arpasing+, English C+V, DiffSinger English+, removed in M15) ended in the host's cryptic "did not resolve". It is now refused up front with
   what to use instead, in the pipeline, in the GUI's explanation and in the Advanced dialog.
4. **NumPy could not import if its renamed copy of the PC's `msvcp140.dll` was missing** (antivirus, a folder copied without the installer's copy step): a long, unhelpful NumPy error. The program now
   remakes the copy from the PC's own file at start (`frozen_fixups.py`; never writes outside its folder; never raises); the smoke test covers it.
5. A project that asks for tension is refused loudly instead of being rendered without it. Stale statements about the neural renderers and the removed engines were corrected.
   (M15's four installer-dialog fixes stand.)

Not fixable: if the Visual C++ runtime vanishes after installation, BLT cannot start and cannot say why (documented, and a step in the clean-machine checklist).

## Gate

* `worldline-spline-review` is **retired (`required: false`)**, because the code it covered no longer exists. This weakens nothing that remains: `check --release` now **requires the build
  to record `worldline_spline_free`** (written by the native build after `verify_dll.py`). If you would rather keep a human sign-off that the removal is clean, set `required` back to `true`.
* Open after this milestone (`release_gate.py check --release`: exit 1, "8 open"): `qt-lgpl-review`, `qt-source-published`, `english-voicebank-acceptance`, `clean-machine-verification`,
  `code-signing-decision`, `owner-release-approval`, plus the component audit (pyside6) and the package check (blockers listed in the build).

## Remaining source-level licensing concerns (for counsel and the owner)

1. **The earlier replacement spline is in the public git history** (M13-M15 commits). If it is a derivative of `tk::spline`, that is a distribution of GPL-derived text under Apache-2.0
   regardless of the binary. Not rewritten (destructive, unapproved); options in `docs/review/worldline-spline-review-packet.md`.
2. **Qt/PySide6 under the LGPL-3.0**: unreviewed; the source bundle is prepared, not published. Open questions: whether a copy installed in BLT's own folder counts as "already present on the
   user's system" (4(d)(1)); whether hosting the sources on the same GitHub release satisfies the source obligation for the required period; four small PySide6 Python modules are frozen into the executables.
3. **The plain English pack's `g2p.onnx` and `phones.txt` (shipped) have no stated training data or licence**; the English "plus" pack's origin is unknown (excluded). Both questions are in the
   unsent upstream inquiry.
4. **BLT's own code was largely written by an AI coding assistant under the owner's direction**, and the copyright notice names the owner. Whether and how such code is protected, and the risk that generated code
   reproduces text it has seen (the spline case is the one we know about), is a question for counsel; no one has examined the rest of the code for it.
5. World's PLATINUM files carry only "All Rights Reserved" inside World's BSD-3-Clause archive (low). The binaries are unsigned (SmartScreen).

## External sign-offs still required

Qt/PySide6 licensing review; publishing the source bundle with a release (URL as evidence); an English-voicebank listening test by someone other than the developer; a clean-machine test
including a PC without the Visual C++ runtime (the administrator prompt and Microsoft's own installer cannot be driven by a script); the code-signing decision; the owner's release approval.
Optional but advisable: submit the upstream inquiry.

## Verification (this PC, 2026-10-13, built from a clean committed tree)

| Check | Result |
|---|---|
| ruff, ruff format, mypy (strict, 285 files) | clean |
| Unit tests | 2611 passed |
| Full `pytest tests` against the published self-contained host (unit, real-host synthesis, full pipeline, golden audio, new tension / reproducibility / phonemizer tests) | **2669 passed, 5 skipped** (no ALYS voicebank configured; no FFmpeg) |
| Native: spline-free check of link map and DLL; native tension test | "17 exports, no spline in the link map or the DLL"; 7,800 calls / 6,299,280 values / 0 failures |
| `trace_tension.ps1` on the final build | 62,502 calls, every one tension 0 |
| `verify-host.ps1`; `verify_absent_data.py` | ok; "no data of the 10 removed files and the Vogen models" |
| Package build, inventory audit (1 blocker: pyside6), smoke tests incl. the new self-repair check, replaceability test | passed |
| Installer test (silent install, missing-runtime refusal, upgrade, uninstall) | passed |
| Installer GUI test (the real Setup window, 23 checks) | passed |
| Release gate `check --release` | exit 1 (closed), as intended |
| CI on `56d5db3` | `render-host` and `package` passed first time. **`checks` aborted once** ("Fatal Python error: Aborted" inside `MainWindow.changeEvent` while the `rig` fixture of `test_a_second_click_cannot_start_a_second_generation` waited for the window; 27 earlier GUI tests of that file had passed) and **passed on re-run**. I could not reproduce it: 20 local runs of the whole GUI test folder were clean. Cause unknown; treated as an intermittent Qt-on-CI abort, not as a fix to make. If it recurs it needs a closer look (the window re-checks its folders whenever it is activated) |

Evidence logs are in `research-output/release/evidence/`, the review packets in `research-output/release/review/` and the tester kit in `research-output/release/tester-kit/` (none committed).
