# Known limitations (0.1.0)

Things that are not done, not verified, or deliberately restricted. Nothing here is hidden elsewhere.

## Release status

* **Not cleared for public release.** Every build is marked NOT FOR RELEASE, and a release gate ([release-gate.md](release-gate.md))
  refuses publication until people have signed off: a review of the Qt/PySide6 LGPL arrangement, with the source bundle attached to
  the release; the replacement spline that remains in the git history; the provenance of the English g2p model (the proposed release is the build without it; a person still has to sign that choice);
  the AI-assisted authorship of the code; the licence conclusions for the compiled dependencies ([review/INDEPENDENT-REVIEWER-CHECKLIST.md](review/INDEPENDENT-REVIEWER-CHECKLIST.md)); an English-voicebank listening test; a clean-machine test; and the owner's decisions on signing and release
  ([m16-report.md](m16-report.md), [m17-report.md](m17-report.md)). The native `worldline.dll` has no spline code at all (the tension effect, the only user of a GPL spline, is removed;
  [worldline-provenance.md](worldline-provenance.md)); an earlier replacement spline remains in the repository's git history. The English "plus" dictionary,
  whose origin is unknown, is **not** in the build.
* **The proposed release has no English pronunciation model (M18).** The one in OpenUtau's English pack has no documented training data or licence ([g2p-model-provenance.md](g2p-model-provenance.md); the upstream inquiry
  is drafted and not sent), so the release candidate omits it, together with `onnxruntime.dll`. The build with the model exists for internal research only (`-IncludeG2pModel`) and the release gate refuses it. Exact limits of the model-free build:
  * Words are looked up in CMUdict. A word it lacks (poetic and dialect forms such as `ev'ry`, `o'er`, `'neath`, `mammy`, `lov'd`) is **built from what the dictionary does have** (for the Arpasing, English VCCV and X-SAMPA engines): an apostrophe is read as a left-out letter (`ev'ry` is `every`, `o'er` is `over`), a final `in` as `ing` said short (`wond'rin` is `wondering` without its `g`), `Oo` as `ooh`; otherwise the word is cut into a few dictionary words (`Biddilly` is `bid` + `dilly`) and their sounds are joined. This is a spelling-based reading, not a check that it is right: it is recorded in the package as BLT's own (`source: composed`, with how it was built, never as a person's decision), shown as a `PRONUNCIATION_COMPOSED` warning, and the score is never touched. Listen to it; give a pronunciation of your own to replace it (below), or turn it off with `--no-composed-pronunciations` to have every such word stop for you. The built sounds are written in ARPAbet, which every one of these engines takes in a hint and translates itself.
  * A word that cannot be built at all (for example `'neath`, which needs a letter at the start the spelling does not give) **stops generation** before any track is rendered, naming the word, its voices and its bar; BLT never drops a syllable. Two remedies, both left to a person: respell the word in the score (`beneath`), or **give its pronunciation** (M19: File > Pronunciations in the app, or `--approve-pronunciations FILE`), which leaves the score as written. BLT never changes the score.
  * **A pronunciation belongs to one score, one voice, one place, one word and one pronunciation engine** ([design/phonetic-overrides.md](design/phonetic-overrides.md)): the same word in another bar, or in another voice, needs its own decision (the dialog can copy a decision to the other voices at the same place on request); any change to the MusicXML file makes saved decisions invalid, and they must be made again; the notation of one engine is refused for another. BLT checks a pronunciation with the engine itself before rendering (a symbol the engine does not know is named, with its voice and bar) but cannot know whether valid symbols are the *right* ones for the word: that is for the singer to hear.
  * **English VCCV and a word that starts with a vowel is unverified.** With the synthetic test voicebank that engine throws on such words (with or without a pronunciation). BLT names it ("the pronunciation engine failed on...") and refuses a hinted note on which the engine failed; whether a real VCCV voicebank has the same problem is in the acceptance checklist.
  * This holds for the Arpasing, English VCCV and English X-SAMPA engines (tested on the real host with the fixture scores of `docs/acceptance/fixtures`). The default engine does not look words up: the lyric is the sound, and a sound the
    voicebank lacks is reported afterwards as silent notes.
  * A word spread over several notes is sent whole only when the score gives the full chain of syllables (begin, middle, end). When a follower voice holds one note under several Lead syllables (investigated in M19: this comes from the follow-the-Lead rule, not from a part's own lyrics or the word assembly, and is an alignment limit, see [m19-report.md](m19-report.md)), only the first syllable fragment is sung;
    if that fragment is not a dictionary word BLT stops and marks it `[a syllable of a longer word]`; the remedy is a lyric of its own for that voice in the score.
  * A lyric written once under one part is sung by the other parts that start a note at the same moment and hold what it holds (for example a held "Oo" written only under the Baritone while the Lead sings shorter words). The match is the note that is as long as this one; when no part has one that long, a note that only starts at the same moment is used (parts may hold a chord for different times). If the Lead is among the matches, the Lead's words win. If the matching parts write different words, nothing is decided and the note stays a lyric-review item. A note that starts at a different moment falls back to the Lead rule. The score is never edited; the review screen says "Follows the Baritone (the same note, written once)".
  * A slur over notes that have no lyric of their own is read as one syllable held over them (the notes after the slur's first note). A slur written over notes whose syllables were simply forgotten is therefore sung as a hold, not reported as a missing lyric; the plan and manifest record the basis `slur`.
  * A syllable engine can also answer "not enough extension notes" when a word has more vowels than notes; that too stops generation.
  * A voicebank's own pronunciation dictionary is consulted when rendering, not by the dictionary lookup helper.
  * The release gate makes a person choose and sign.
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
* **What BLT reads.** MusicXML (`.musicxml`, `.xml`, `.mxl`; MuseScore's own exports were tested) is read directly. Two other kinds of file are converted first, **by a program you must have installed; BLT ships neither**:
  * a **MuseScore project** (`.mscz`, `.mscx`) is exported to MusicXML by MuseScore's command line (found in its usual folders, or set `BLT_MUSESCORE`). Tested with real MuseScore 4 files: the tracks are byte-for-byte those made from the MusicXML. The conversion is kept in BLT's cache, and everything bound to the score (lyric approvals, pronunciations, the package's record) is bound to the **project file's** SHA-256, not to the export (MuseScore dates every export); the package's `manifest.json` records the conversion (`source.conversion`).
  * a **PDF or image of the music** (`.pdf`, `.png`, `.jpg`) has no notes in it; they are *recognised* by Audiveris (free; `BLT_AUDIVERIS` or its usual folder) when you accept that recognition makes mistakes (a dialog in the app, `--accept-recognition` on the command line). The result is flagged everywhere (a warning in the window, `recognised: true` in the package), and BLT does not check the recognised music: a wrong note or a word under the wrong note will be sung. Several recognised pieces in one PDF are refused (BLT will not choose). **The recognition path is tested only with a stand-in program, not with the real Audiveris, which is not installed on the development PC**: whether it reads real scanned or vector barbershop PDFs well is unknown.
  * A missing program, a failure, a time-out (3 minutes for MuseScore, 20 for recognition) or an empty result is reported with what to do; nothing is guessed. MIDI is not read (no lyrics, no voice names).
* **No playback or preview** inside the app yet (tracked separately). You open the output folder and play the files elsewhere.
* One score at a time; no batch mode in the GUI (the command line scripts well).
* Voicebanks are never included or downloaded; you must supply one and respect its licence.
* Display scaling (125 to 200 %) and screen readers were designed for (accessible names, Qt high-DPI) but not
  systematically tested.
* Unusual scores (more than four parts, very long songs, exotic MusicXML) behave as documented in
  [musicxml-support.md](musicxml-support.md); BLT refuses rather than guesses when a score is not ready.
