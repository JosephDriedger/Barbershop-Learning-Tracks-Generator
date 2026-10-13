# M15: final compliance alternatives and release-acceptance preparation

Status: **done and verified locally; every artifact is still NOT FOR RELEASE.** Nothing was posted, signed, uploaded or published. Two licensing
reviews, two person-run acceptance tests and two owner decisions remain open, and the new release gate keeps them open.

> **Update (M16, [m16-report.md](m16-report.md)):** the replacement spline described here was removed instead of reviewed (the tension effect, its only user, is gone from the native build and the binary is proven spline-free), so its gate item is retired and `worldline` is no longer a licensing blocker; the upstream inquiry now also covers the plain pack's `g2p.onnx` and is still **not submitted**.

## What was asked, what was done

| # | Task | Result |
|---|---|---|
| 1 | Prepare the upstream inquiry; do not post | [upstream-g2p-plus-issue.md](upstream-g2p-plus-issue.md): exact repository (**openutau/OpenUtau**, MIT), contributor (**@Cadlaxa**; PR #1038 merged by @stakira; six commits touch the file), the evidence (reproducible numbers), four questions, where and how to post (blank issues are disabled; use the Feature Request form), and what BLT does with each answer. **Not posted.** |
| 2 | Release-safe fallback without the unverified dictionary | Done. The plus pack, the Arpasing+, English C+V and DiffSinger English+ phonemizers, `ArpabetPlusG2p`, its lyrics helper and the 1.2 MB C+V template are removed from the patched sources **and the resource tables**. CMUdict-based English phonemizers are kept and tested end to end. The data is proven absent from the packaged binary (see below) |
| 3 | Independent-review packet for the replacement spline | [review/worldline-spline-review-packet.md](review/worldline-spline-review-packet.md) (+ generated packet folder): mathematical specification, provenance, comparison restrictions, build procedure, tests, known concerns, options. **A finding changed the story, see "Findings".** |
| 4 | Qt/PySide6 packet for human review | [review/qt-pyside6-review-packet.md](review/qt-pyside6-review-packet.md) (+ generated packet folder): versions, licences, notices, source archives with checksums and tag cross-checks, written offer, relinking instructions, replaceability evidence, an LGPL obligation table with the open questions |
| 5 | A release gate that CI cannot override | `compliance/release-gate.json` + `packaging/release_gate.py` + `.github/workflows/release.yml` + `build.ps1 -ForRelease` + CODEOWNERS, documented in [release-gate.md](release-gate.md). Demonstrated: `check --release` exits 1 with 9 open items |
| 6 | Checklists someone else can run | [acceptance/](acceptance/README.md): English voicebank acceptance, clean-machine verification (with and without the Visual C++ runtime), tester kit and results blocks |
| 7 | Installer experience without the Visual C++ runtime | Investigated with the real Setup window. Four defects found and fixed. New `packaging/installer-gui-test.ps1`. One path needs a person (UAC) |
| 8 | All checks | Below |
| 9 | Report | This page |

## Blockers: how each stands

### Resolved by technical evidence

* **English "plus" dictionary (redistribution of data of unknown origin).** Resolved *by exclusion*, not by finding its origin.
  Evidence: `host/verify-host.ps1` (reflection: no plus resource, no `*Plus*`/`EnglishCpV` type, no C+V template, CMUdict pack byte-identical to
  the pinned source) and `packaging/verify_absent_data.py` (searches **every file of the package** for fingerprints of the removed data; positive control: it finds the
  plus pack and the C+V template in the previous host build; on this build "no data of the 10 removed files and the Vogen models"). Unit tests
  prove the scanner finds the data under any file name and refuses a vacuous pass. The plain pack's dictionary is CMUdict 0.7b entry for entry
  (133,852; compared against CMU's original file). Cost: Arpasing+ and English C+V are gone ([KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md)).
* **OpenUtau.Core (Voicevox/LGPL code), onnxruntime, the Microsoft runtime** stay resolved as in M14.

### Need a human review (cannot be closed by tests)

1. **`worldline.dll`: the replacement for GPL `tk::spline`** (gate item `worldline-spline-review`). Technical evidence is strong that the replacement is *correct*
   (matches the mathematical definition on 20,840 values with no GPL code involved; matches `tk::spline` to 1.6e-14 on every input worldline produces; audio byte-identical;
   no `tk::spline` symbol). Whether it is a *derivative* is a legal judgement, and the provenance is not clean (next section).
2. **Qt/PySide6 LGPL arrangement** (`qt-lgpl-review`), and then publication of the source bundle with a release (`qt-source-published`). The packet states
   BLT's reading of LGPL 4(d)(1) and the other obligations and lists what a reviewer must confirm. All 12 Qt/PySide6 files in the package are
   byte-identical to the hashes in the wheels' own RECORD files (unmodified).

### Need external resources

* A tester other than the developer with an **English voicebank** (`english-voicebank-acceptance`).
* A **clean Windows PC/VM**, ideally also one without the Visual C++ runtime and one with a standard (non-admin) account (`clean-machine-verification`): the administrator
  prompt (UAC) and Microsoft's own installer running cannot be driven by a script. The expected message when the runtime vanishes *after* installation is a guess (step B12).
* The owner's **code-signing decision** and **release approval**.
* Optionally an **answer from upstream** about the plus dictionary (only matters if it is ever re-included).

## Findings worth your attention

1. **The spline replacement was not written clean-room.** I (the AI assistant that wrote it, directed by you) printed large parts of `tk::spline`'s `spline.h`, including
   the equation-system set-up and `operator()`, 24 seconds before creating `natural_spline.h`, as the session log shows. M14's wording "written from the maths" understated that,
   and the earlier docs were corrected. The structure differs (second derivatives and Thomas elimination instead of coefficients and a band-matrix solver), but a reviewer
   must judge it, and the packet says so plainly. The review packet therefore offers options, including **a clean-room rewrite by someone who has not seen the original**
   and **removing the interpolation altogether**: BLT never sets tension, so every render feeds the spline all-zero control points and the output is exactly 1.0, which a
   one-line patch would reproduce with no spline code at all. I did not implement that option because it changes upstream behaviour you have not approved.
2. **The byte-identical audio test does not exercise the spline's interpolation** (tension is always 0 in BLT renders). It proves the integration only; the parity and
   specification tests carry the numerical evidence. Stated in the packet.
3. **Qt: four small PySide6/shiboken6 Python modules are frozen into the executables**, so "the libraries are separate files" is true for the DLLs/PYDs but not for those four modules. The
   notices and `RELINKING.md` now say so and explain the rebuild route, and the packet asks the reviewer about it.
4. **The qtbase tag** in M14's notes was the annotated *tag object*; the commit is `ef55f427…`. Both are now recorded, with the pyside-setup tag read from Qt's git server.
5. **Four installer defects found and fixed**: "Cancel setup" did not cancel setup (renamed "Go back (BLT is not installed yet)"); the Microsoft link was cut off with "..." in the dialog;
   cancelling the file chooser produced an unwanted "still not available" box; a failed download showed only Inno's "Internal error: Worker thread terminated..." text.
6. **If the Visual C++ runtime disappears after BLT is installed, BLT cannot start and cannot say why** (the Python launcher fails before BLT's code runs). This is inherent to not
   shipping the runtime; Setup guards the install, and TROUBLESHOOTING says what to do.
7. Earlier figures for the plus dictionary ("299,535 / 120,887") came from an ad-hoc count and were replaced by reproducible ones: 420,420 lines, 258,522 distinct entries,
   45,819 entries for 37,558 words that are not in CMUdict at all.

## Verification (this PC, 2026-10-13, working tree of the commits listed in the log)

| Check | Result |
|---|---|
| ruff, ruff format, mypy (strict, 285 files) | clean |
| Full `pytest tests` against the published self-contained host (unit, real-host synthesis, full pipeline, golden audio, new phonemizer tests) | **2645 passed, 5 skipped** (no ALYS voicebank configured; no FFmpeg) |
| Native: spline vs `tk::spline` (864 cases, 830,304 values) / vs the mathematical definition (360 cases, 20,840 values) / DLL symbol and export check | max diff 1.6e-14 / worst 1.6e-5 of tolerance / "17 exports, no tk::spline symbol" |
| `verify-host.ps1`; `verify_absent_data.py` on the package | ok / "no data of the 10 removed files and the Vogen models" |
| Package build with inventory audit (2 blockers: pyside6, worldline) | ok |
| Package smoke tests (plain and non-ASCII paths) | passed |
| Replaceability test | passed (12 of 12 Qt/PySide6 files identical to their wheel RECORD hashes) |
| Installer test (silent install, missing-runtime refusal, install + smoke, upgrade, uninstall) | passed |
| Installer GUI test (the real Setup window; dialog, offline file route, a file signed by someone else refused, an unsigned download refused, failing download, signature check on four kinds of file) | passed (23 checks) |
| Release gate: `check --release` | **exit 1, 9 open** (as intended) |
| CI | see the commit log; the new steps (absent-data scan, gate status) run there |

Evidence logs: `research-output/release/evidence/` (not committed); review packets: `research-output/release/review/` (not committed); screenshots of the installer dialogs in
`evidence/installer-gui-shots/`.

## Decisions for the owner

1. Approve (or not) sending the upstream inquiry; say whether to add the question about the plain pack's `g2p.onnx` model and whether to post in a second place.
2. For the spline: choose clean-room rewrite, removal of the interpolation, asking the `tk::spline` author, or "reviewer decides on the current file".
3. Find a reviewer for the Qt/PySide6 arrangement; decide whether to keep a second copy of the source bundle elsewhere.
4. Apply the repository settings that make the gate meaningful (branch protection requiring code-owner review of `compliance/`; CODEOWNERS is in place).
5. Arrange a tester, an English voicebank and a clean PC.
