# Known limitations (0.1.0)

Things that are not done, not verified, or deliberately restricted. Nothing here is hidden elsewhere.

## Release status

* **Not cleared for public release.** Every build is marked NOT FOR RELEASE, and a release gate ([release-gate.md](release-gate.md))
  refuses publication until people have signed off: a review of the Qt/PySide6 LGPL arrangement, with the source bundle attached to
  the release; the replacement spline that remains in the git history; the provenance of the English g2p model (or the choice of the build without it);
  the AI-assisted authorship of the code; the licence conclusions for the compiled dependencies ([review/INDEPENDENT-REVIEWER-CHECKLIST.md](review/INDEPENDENT-REVIEWER-CHECKLIST.md)); an English-voicebank listening test; a clean-machine test; and the owner's decisions on signing and release
  ([m16-report.md](m16-report.md)). The native `worldline.dll` has no spline code at all (the tension effect, the only user of a GPL spline, is removed;
  [worldline-provenance.md](worldline-provenance.md)); an earlier replacement spline remains in the repository's git history. The English "plus" dictionary,
  whose origin is unknown, is **not** in the build.
* **The English pronunciation model has no documented training data or licence.** Words outside CMUdict (poetic and dialect forms such as `ev'ry`, `o'er`, `'neath`, `mammy`) get their pronunciation from a small neural model
  in OpenUtau's English pack. It is the OpenUtau author's own file in an MIT repository, and the training recipe in the same source tree uses CMUdict, but no document says what this binary was trained on
  ([g2p-model-provenance.md](g2p-model-provenance.md); the upstream inquiry is drafted and not sent). A build without the model exists and is tested (`packaging/build.ps1 -ExcludeG2pModel`): then a
  word outside CMUdict makes the singer silent on that note, generation stops with a message naming the word, and the user must respell it. The release gate makes a person choose.
* **Tension is not supported.** OpenUtau's per-note/curve "tension" voice effect is not in BLT's native library. BLT never writes it; a project that asks for it
  is refused by the host ("unsupported_tension") instead of being rendered without it.
* **Two English phonemizers are missing.** Because the "plus" dictionary is excluded, upstream OpenUtau's *Arpasing+* and *English
  C+V* phonemizers (and the DiffSinger English+ one) are not in BLT's host. The CMUdict-based ones (Arpasing, English VCCV, X-SAMPA)
  and the default phonemizer are. A voicebank that only works with C+V cannot be used.
* **Visual C++ Redistributable is a prerequisite.** BLT does not ship Microsoft's runtime; Setup checks for it, offers Microsoft's
  download or a file you bring, and refuses a silent install without it. Tested with the real Setup window on the developer's PC
  (`packaging/installer-gui-test.ps1`: the dialog, the offline file route, refusing files not signed by Microsoft, a failing download).
  Not tested by a machine: the Windows administrator prompt and Microsoft's own installer running (it needs a person; it is in
  [acceptance/clean-machine-verification.md](acceptance/clean-machine-verification.md)). If the runtime is removed after BLT is
  installed, BLT cannot start and cannot show its own message.
* **Not verified with an English voicebank.** The listening test in [acceptance/english-voicebank-acceptance.md](acceptance/english-voicebank-acceptance.md)
  (protocol background: [m12-acceptance.md](m12-acceptance.md)) has not been run; whether English lyrics are intelligible with a given voicebank, how melismas sound, and whether the
  predominant tracks are clear enough are all unknown. Only a generated sine-wave voicebank and a French voicebank
  (technical checks) were used.
* **The GUI tests run with a workaround.** Python's garbage collector is switched off inside each GUI test because, without it, the suite aborted at random on CI ("Fatal Python error: Aborted" in
  `MainWindow.changeEvent`). The workaround hides, and does not explain, a lifetime problem somewhere in the Qt objects the tests leave behind; it has not been seen in the packaged program. An opt-in run
  without the workaround, with a collection trace and a crash log, exists ([gui-gc-diagnostics.md](gui-gc-diagnostics.md)). Do not read the green test suite as proof that the underlying problem is gone.
* **Not verified on a pristine machine or by users.** The clean-machine check and a usability test with
  non-developers have not been done ([acceptance/clean-machine-verification.md](acceptance/clean-machine-verification.md);
  background: [m12-verification.md](m12-verification.md)). Automated tests ran in a stripped
  environment on the development PC.

## Installation and trust

* The installer and executables are **unsigned**: SmartScreen warns, the publisher shows as unverified, and some
  antivirus products may flag PyInstaller programs.
* Windows 10/11 **x64** only. Not tried on ARM64 (x64 emulation).
* Footprint: about 212 MB installed, plus about 115 MB of private working files per user after the first run
  (the singing engine's copy; old versions' copies are removed after a day).
* A user name with non-ASCII characters was only emulated (all folders BLT uses placed under such a path).

## Features

* **Renderer:** WORLDLINE-R only. CLASSIC renders but its audio runs a few tens of milliseconds past the performed length
  and the mix check rejects it (`MIX_STEM_TOO_LONG`, seen with a real voicebank), so it is not offered. The neural renderers are not offered: Vogen and VOICEVOX are
  removed from the host (licensing), and ENUNU and DiffSinger have never been tested with BLT.
* **MP3 needs an FFmpeg you install**; none is bundled. WAV needs nothing.
* **No playback or preview** inside the app yet (tracked separately). You open the output folder and play the files elsewhere.
* One score at a time; no batch mode in the GUI (the command line scripts well).
* Voicebanks are never included or downloaded; you must supply one and respect its licence.
* Display scaling (125 to 200 %) and screen readers were designed for (accessible names, Qt high-DPI) but not
  systematically tested.
* Unusual scores (more than four parts, very long songs, exotic MusicXML) behave as documented in
  [musicxml-support.md](musicxml-support.md); BLT refuses rather than guesses when a score is not ready.
