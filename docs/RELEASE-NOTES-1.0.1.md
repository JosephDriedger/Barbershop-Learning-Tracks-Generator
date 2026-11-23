# BLT Music Generator 1.0.1 (DiffSinger edition)

**Internal research build: Windows 10/11 x64, unsigned, NOT for distribution.** The installer, `BLT-Music-Generator-1.0.1-Setup.exe`, has the
ordinary file name and title (it is built with `packaging\build.ps1 -IncludeDiffSinger`), so the file name no longer says what it is: this page
and `release-info.json` do. It contains the English "ARPAbet plus" dictionary and the English g2p model, both of
unknown origin ([g2p-plus-provenance.md](g2p-plus-provenance.md), [g2p-model-provenance.md](g2p-model-provenance.md)), so that DiffSinger
voices can be sung. It is refused by `packaging\build.ps1 -ForRelease`, no tester kit is made for it, and every release-gate item of
[release-gate.md](release-gate.md) is still open. The ordinary 1.0.1 installer (no DiffSinger, no plus dictionary, no g2p model) is the one that
can be released, once the gate is open. It has not been built from this tree.

It replaces an installed BLT in place (same application id). It does not include a voicebank: add yours as before.

## What is new

* **DiffSinger voicebanks are sung.** BLT looks at each voicebank. A DiffSinger one is sung by the DIFFSINGER renderer with the DIFFS EN+
  pronunciation engine; a UTAU-style one by the renderer and pronunciation engine that were chosen (or detected from its sounds). Nothing has to be
  typed, and one quartet may mix the two (for example a DiffSinger Lead with UTAU-style Tenor, Baritone and Bass). BLT shows an
  `ENGINE_BY_VOICEBANK` warning when it changes a voice. `--renderer DIFFSINGER` still works.
* **The mix handles DiffSinger's release.** DiffSinger ends every stem about 100 ms after the score. For DiffSinger voices only, the mix drops that
  tail (up to 130 ms and -20 dBFS) with a 30 ms fade before the cut; UTAU-style stems keep the strict check. The manifest records the per-voice
  policy (`tail_policy.per_voice`).
* **On any other host a DiffSinger voicebank is refused up front,** with the reason, instead of rendering silence.
* **The package checks know about the edition.** `-IncludeDiffSinger` relaxes exactly one thing in `verify-host`, the host inventory and the
  absent-data scan: the English plus pack (matched by size and SHA-256 to the pinned source) and DIFFS EN+. Arpasing+, English C+V and
  Voicevox are still refused. The normal build is unchanged.
* **A PDF that a notation program wrote is read directly,** without Audiveris (`docs/pdf-reading.md`); a scanned PDF still needs Audiveris.
  Finale scores in its Maestro font are read too, also when printed through Microsoft Print to PDF.
* **Fixing a score before generating.** *Open Score to Fix* opens a score read from a PDF as an editable copy beside it
  (`Name (from PDF).musicxml`), with the PDF to compare, and offers to use the corrected score once it is saved in MuseScore;
  `barbershop-tracks fix SCORE` on the command line. Titles, buttons, column headers and short labels are in title case.
* **Score handling since 1.0.0** (all in the commit history, `git log v1.0.0..HEAD`): playback tempo follows a fermata on the note of a tempo
  mark; a fermata note ends at the full tempo and gets a 300-tick tail so the end of a word keeps its usual length; the count-in clicks at the
  tempo the score is written at; a MuseScore pickup keeps its own length and the playback is checked to be as long as the score; the mix accepts a
  stem a few milliseconds too long whose last note releases a little above -60 dBFS.

## Tried so far

* Tiger (`TIGER_DS_v106`) and Bennett (ENG) with the 8-bar kit score `english-quartet-known-words`, by the developer, on CPU: Tiger on all four
  parts, Tiger as Lead with Bennett on the others, and Bennett alone each made the 13 tracks (about 40 s, 20 s and 10 s). The developer listened
  to the Tiger tracks and said they sound good. That is an informal listen, not the acceptance checklist.
* A real score: "Ebb Tide" (a MuseScore file, 36 bars, 111.5 s, 21 tempo changes with a ritardando and fermatas) with Tiger on all four parts,
  through the installed app, made the 13 tracks in 166 s on CPU. Its first run was refused (`MIX_STEM_TOO_LONG`, 115.0 ms past the score
  against a 115 ms limit taken from the short score); the DiffSinger limit is now 130 ms, 100 ms of release plus the frame size.
* The unit tests (3,333), ruff, mypy, the package smoke tests and the package's compliance checks pass.

## Not done, and limits

* The installer wizard has not been run: install, upgrade and uninstall are untested here, as are a clean PC and a PC without the Visual C++ runtime.
* **Two renders of the same score are not the same bytes** with a DiffSinger voice (the diffusion noise is inside the model and OpenUtau has no
  seed). UTAU-style voices are still reproducible bit for bit.
* A DiffSinger voice takes no pronunciation overrides, no fermata-tail adjustment and no "built from dictionary pieces" words; a word the
  dictionary lacks is guessed by the plus pack's g2p model and is not reported.
* Not tried: words the dictionary lacks, fermatas and pickups with a DiffSinger voice, long scores, GPU inference, the English-voicebank
  acceptance checklist with Tiger.
* **BLT cannot publish to an output folder on another drive than its staging folder** (`PUBLISH_FAILED`, "cannot move the file to a different disk
  drive"): this also affects 1.0.0 and the ordinary build, and is not fixed.

## Voicebank licence

Tiger is by tigermeat ([tigermeat.xyz](https://tigermeat.xyz/#tiger-ds)); its licence (`extra/LICENSE.md` in the bank) is the author's own: free
use as long as nobody is harmed, no commercial use without a purchased licence, the copyright notice kept with copies, and the artwork not used to
train image models. It is not CC BY-NC-ND. BLT does not ship or download it.

## Third-party software

As in 1.0.0 ([RELEASE-NOTES-1.0.0.md](RELEASE-NOTES-1.0.0.md)), plus what this edition adds: the English plus dictionary and g2p model above, and
the native ONNX Runtime they and DiffSinger run on. DiffSinger itself is part of the OpenUtau 0.1.565 sources BLT builds from.

## Checksums

`BLT-Music-Generator-1.0.1-Setup.exe` (DiffSinger edition): SHA-256 `bd21d04ec4ce16954c67e640f519ca91bcd74e49d554f142786718efb246432a`
(built from the working copy just before commits `3dbd686` and `8273a5a`, which contain exactly those changes, so release-info
says `uncommitted_changes: true`; `research-output\release-diffsinger\artifacts\SHA256SUMS.txt`, and a copy in `installer\`).
Nothing is published.
