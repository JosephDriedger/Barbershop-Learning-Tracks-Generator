# Known limitations (1.0.0)

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
  * Words are looked up in CMUdict. A word it lacks (poetic and dialect forms such as `ev'ry`, `o'er`, `'neath`, `mammy`, `lov'd`, or an unusual spelling) is **never a stop by default** (for the Arpasing, English VCCV and X-SAMPA engines). BLT tries, in order: (1) the word *spelled out* as a dictionary word (an apostrophe read as a left-out letter: `ev'ry` is `every`, `o'er` is `over`; a final `in` as `ing` said short: `wond'rin` is `wondering` without its `g`; `Oo` as `ooh`); (2) the word cut into a few dictionary words whose sounds are joined (`Biddilly` is `bid` + `dilly`); (3) as a last resort a **rough guess from the spelling** by a few hand-written letter-to-sound rules (`cappuci` as `k ae p ah s ih`). The built sounds are written in ARPAbet, which every one of these engines takes in a hint and translates itself.
  * **What that means, and how you are told.** (1) and (2) use only entries the dictionary has; (3) is a guess and is often wrong (English spelling is not regular; it is not a pronunciation model and has no training data). Every such word is recorded in the package manifest as BLT's own (`source: composed`, or `source: guessed`, with `composed_how`, never as a person's decision) and shown as a `PRONUNCIATION_COMPOSED` or `PRONUNCIATION_GUESSED` warning naming the word, its bar and voice. The score is never touched. Listen to those places; give a pronunciation of your own to replace one (File > Pronunciations, or `--approve-pronunciations FILE`; yours always wins). `--no-guessed-pronunciations` stops at a word that (1) and (2) cannot explain; `--no-composed-pronunciations` stops at every word the dictionary lacks. A word with no letters at all still stops.
  * **A pronunciation belongs to one score, one voice, one place, one word and one pronunciation engine** ([design/phonetic-overrides.md](design/phonetic-overrides.md)): the same word in another bar, or in another voice, needs its own decision (the dialog can copy a decision to the other voices at the same place on request); any change to the MusicXML file makes saved decisions invalid, and they must be made again; the notation of one engine is refused for another. BLT checks a pronunciation with the engine itself before rendering (a symbol the engine does not know is named, with its voice and bar) but cannot know whether valid symbols are the *right* ones for the word: that is for the singer to hear.
  * **English VCCV and a word that starts with a vowel is unverified.** With the synthetic test voicebank that engine throws on such words (with or without a pronunciation). BLT names it ("the pronunciation engine failed on...") and refuses a hinted note on which the engine failed; whether a real VCCV voicebank has the same problem is in the acceptance checklist.
  * This holds for the Arpasing, English VCCV and English X-SAMPA engines (tested on the real host with the fixture scores of `docs/acceptance/fixtures`). The default engine does not look words up: the lyric is the sound, and a sound the
    voicebank lacks is reported afterwards as silent notes.
  * A word spread over several notes is sent whole only when the score gives the full chain of syllables (begin, middle, end). When a follower voice holds one note under several Lead syllables (investigated in M19: this comes from the follow-the-Lead rule, not from a part's own lyrics or the word assembly, and is an alignment limit, see [m19-report.md](m19-report.md)), only the first syllable fragment is sung;
    if that fragment is not a dictionary word BLT stops and marks it `[a syllable of a longer word]`; the remedy is a lyric of its own for that voice in the score.
  * A lyric written once under one part is sung by the other parts that start a note at the same moment and hold what it holds (for example a held "Oo" written only under the Baritone while the Lead sings shorter words). The match is the note that is as long as this one; when no part has one that long, a note that only starts at the same moment is used (parts may hold a chord for different times). If the Lead is among the matches, the Lead's words win. If the matching parts write different words, nothing is decided and the note stays a lyric-review item. A note that starts at a different moment falls back to the Lead rule. The score is never edited; the review screen says "Follows the Baritone (the same note, written once)".
  * A slur over notes that have no lyric of their own is read as one syllable held over them (the notes after the slur's first note). A slur written over notes whose syllables were simply forgotten is therefore sung as a hold, not reported as a missing lyric; the plan and manifest record the basis `slur`.
  * **For a MuseScore project (`.mscz`, `.mscx`) this is no longer a guess:** the project records how far each underscore line runs, BLT reads it (matching each voice to the project by what it sings, and only on an exact match), and every held "oo", "doo" and "loo" lasts at least as long as MuseScore draws it (a line that is drawn short, over one note, is still held on through lyric-less notes after it as before, since MuseScore leaves out lines that are clearly implied); the part then follows the Lead again. The rest of this entry applies to MusicXML and compressed MusicXML (whose export loses the length), and to any voice that could not be matched to the project (the window says how many held syllables were matched, e.g. "85 of 85"). MuseScore's MusicXML writes an extender line ("Oo" with a line) as one untyped extender on the first note and does not say how far the line runs. BLT's analysis takes it to the next lyric or rest, but a part that after its line moves note for note with the Lead (each note starting and ending with a Lead note) is read as having left the line: those notes sing the Lead's words (or hold the Lead's vowel). This is a guess about notation the file does not record: a part that really sings "Oo" in exactly the Lead's rhythm under the Lead's words is read wrongly, and the remedy is to write the part's own lyric or approve the note. A note of a different length, or starting elsewhere, keeps holding. The record of such a note says "the score's extender line ... is read as ended". "Oo" (any number of o's, with or without a final h) is always read as "ooh" by the dictionary engines.
  * A syllable engine can also answer "not enough extension notes" when a word has more vowels than notes; that too stops generation.
  * A voicebank's own pronunciation dictionary is consulted when rendering, not by the dictionary lookup helper.
  * The release gate makes a person choose and sign.
* **The tune-up note and the count-in are simple (not heard on a real voicebank's tracks by a person).** The tune-up note is a sine tone at the tonic of the score's *first* key signature (a later key change is ignored; a transposing score would give the written key). A key signature fits a major key and its relative minor, so BLT does not decide: the person chooses Major Key or Minor Key (major by default); a score with no key signature is C major or A minor, and the manifest says that the key was assumed. The count-in is one bar of clicks at the first tempo and time signature: a tempo change in the first bar, a pickup measure (the count is a whole bar, the pickup follows it) or an unusual meter is not counted differently. The manifest's `audio.frames` then includes them; `audio.duration_seconds` stays the music's length.
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

## macOS (experimental)

What is verified, and only by machines: on GitHub's Apple-silicon (`macos-latest`) and Intel (`macos-15-intel`) runners CI runs ruff, mypy
and the unit tests; builds the render host with BLT's own `libworldline.dylib` (clang and CMake, no spline: checked by
`host/native/verify_dylib.py`) and the same inventory, removed-data and negative-control checks as on Windows; runs the integration tests
with the host and a generated synthetic voicebank; builds `BLT Music Generator.app` and the `.dmg`, audits every file of the app
against the component tables, runs `blt selftest` in a stripped environment (no Python, no .NET, ASCII and non-ASCII paths), and checks
that the Qt libraries are separate, replaceable files.

What is **not** verified:

* **No person has run it on a real Mac.** CI is a headless runner: nothing has been seen in a window, no sound was played, and a real
  voicebank was not used (only a generated sine-wave one). The macOS version of the clean-machine and listening checks is open. The
  [release gate](release-gate.md) has no item for it: it is the owner's call whether a draft release with the `.dmg` is published
  before someone has tried it.
* **Unsigned and not notarised.** Gatekeeper blocks the first start (see [INSTALL.md](INSTALL.md#installing-on-macos)); the signing and
  notarisation steps in `packaging/build_macos.py` exist but are off and have never been run. The owner has not decided on an Apple
  Developer account. Nothing about Gatekeeper's behaviour on a downloaded copy was tested (CI copies carry no quarantine flag).
* Two separate disk images (Apple silicon, Intel), not one universal app. macOS 12 or later is what the build targets; older releases and
  the oldest supported macOS (as opposed to the runners' current one) were not tried.
* Process handling on macOS is the POSIX path (the render host leads its own process group and is ended with it); the Windows job
  objects have no counterpart. Cancelling a render, a time-out and Ctrl+C are covered by the same integration tests as on Windows.
* The kit for testers (`packaging/tester-kit`) and its output checker are Windows PowerShell; they are not part of the macOS build.
* **Two differences of the macOS host from OpenUtau as it is.** (1) OpenUtau keeps its data, logs and render cache in the user's home folder on a Mac
  (`~/Library/OpenUtau`, shared with the OpenUtau application); BLT's host is started with a home folder of its own inside its private runtime copy,
  so it neither reads nor deletes the user's OpenUtau data. (2) The macOS build changes one line of OpenUtau (`host/patch_macos.py`): the length of a
  pitch curve is computed as a `double` and converted to `int`, which OpenUtau does not guard; where the value is out of range x64 gives 0 (the note is
  rendered without a pitch curve) while Apple silicon would stop the render with an out-of-memory error. The macOS build gives 0 on both, which is what
  Windows has always done. The cause of the out-of-range value (seen only in the pronunciation tests with the synthetic voicebank) was not investigated.
* A voicebank's file names that differ only in case, or in Unicode normalisation, behave as the Mac's file system does; not tested with real banks.

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
  * **Ritardando, fermata, "a tempo".** For a MuseScore project BLT follows the tempo MuseScore plays (from its own MIDI export), so
  these are respected as in MuseScore; if that playback disagrees with the score's tempo marks it is left unused and a warning says
  so. For MusicXML, compressed MusicXML and recognised PDFs only the tempo marks in the file count: a `rit.` written as words is
  sung at the tempo before it. Other tempo effects of MuseScore's playback (swing, a gradual tempo change MuseScore itself
  exports as plain steps) are followed as MuseScore plays them; BLT adds none of its own.
* a **PDF or image of the music** (`.pdf`, `.png`, `.jpg`) has no notes in it; they are *recognised* by Audiveris (free; `BLT_AUDIVERIS` or its usual folder) when you accept that recognition makes mistakes (a dialog in the app, `--accept-recognition` on the command line). The result is flagged everywhere (a warning in the window, `recognised: true` in the package), and BLT does not check the recognised music: a wrong note or a word under the wrong note will be sung. Several recognised pieces in one PDF are refused (BLT will not choose). **Real Audiveris was tried once (21 Oct 2026) on a clean PDF that MuseScore exported from a four-part test score**: it found all four parts and every note, but recognised none of the lyrics and no tempo, so readiness blocked generation. Recognition quality is Audiveris's, not BLT's, and it is known to be weak on barbershop layouts (shared staves, two voices per staff, lyrics); treat a PDF as a last resort and prefer MusicXML or a MuseScore project. Scanned PDFs have not been tried.
  * A missing program, a failure, a time-out (3 minutes for MuseScore, 20 for recognition) or an empty result is reported with what to do; nothing is guessed. MIDI is not read (no lyrics, no voice names).
* **No playback or preview** inside the app yet (tracked separately). You open the output folder and play the files elsewhere.
* One score at a time; no batch mode in the GUI (the command line scripts well).
* Voicebanks are never included or downloaded; you must supply one and respect its licence.
* **Adding voicebanks.** *Add voice…* (and `barbershop-tracks voices add`) takes a folder or a `.zip`; 7z and rar must be unpacked first. It never replaces a voice of the same name, never downloads, and adds a one-line `character.txt` to the copy when the bank has none. It copies into the voices folder in use (BLT's own by default). Not tested with real zips of other makers' banks, other than the file names Japanese Windows stores (tested with a generated one).
* **Which voicebanks can be used.** UTAU-style banks (recordings named in an `oto.ini`), directly in the voices folder or inside a pack folder (listed as `Pack\Bank`), with any folder name and any text encoding the bank declares. The singing engine lists a bank only if it has a `character.txt`; BLT says so when one is missing. ENUNU, DiffSinger and VOICEVOX banks are refused with a message (they would only give silence). Whether a given bank is *intelligible* for the words of a song depends on its language and the pronunciation engine; BLT picks the engine from the bank's sound names only when they say clearly which one it was made for.
* Display scaling (125 to 200 %) and screen readers were designed for (accessible names, Qt high-DPI) but not
  systematically tested.
* Unusual scores (more than four parts, very long songs, exotic MusicXML) behave as documented in
  [musicxml-support.md](musicxml-support.md); BLT refuses rather than guesses when a score is not ready.
