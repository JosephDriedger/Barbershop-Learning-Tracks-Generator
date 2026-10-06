# OpenUtau Integration (M0 findings)

Status: **M0 research, desk-based, approved.** Findings come from the official OpenUtau
wiki and the `master` source on GitHub, read in October 2026. Nothing here has been
verified by running OpenUtau yet.

**OpenUtau version: unverified.** Search results disagreed (0.1.568 vs 0.1.571), so no
version is recorded or hard-coded anywhere. Check the current official release first.

**Gate:** no behavior may be implemented from an [Unverified] or [Source] item until the
matching check in section 7 has been performed. Those checks happen **before M6**.
M1 to M5 work against the `SynthesisBackend` abstraction only.

Each finding is marked:

- **[Documented]**: stated on the official wiki.
- **[Source]**: observed in the repository code, not in prose documentation.
- **[Unverified]**: believed, but not confirmed. Must be tested before we rely on it.

Rules this document follows: no GUI automation, no undocumented command-line arguments,
no invented APIs.

## 1. Summary

| Question | Answer |
|---|---|
| Is there a documented CLI or headless render mode? | **No.** None found. See section 3. |
| Does OpenUtau import MusicXML directly? | **Yes** [Documented], but lossily (section 2.2). We will not use it. |
| Does OpenUtau import MIDI, and do lyrics survive? | **Yes.** MIDI lyric meta-events are read and matched to notes by tick [Source]. |
| Is USTX documented? | **Yes**, version 0.6, but with no stated stability guarantees. |
| Can we render automatically? | **No documented, stable mechanism.** `AutomatedOpenUtauBackend` stays reserved. |
| Per-track WAV export in the app? | **Yes**: File > Export Audio > Export wav Files [Documented]. |
| Verdict for v1 | **Semi-automatic.** Write a MIDI bundle, user renders in OpenUtau, app ingests the stems. |

Correction to the earlier architecture review: it said OpenUtau does not read MusicXML.
That was wrong. The reasons we still generate our own import file are in section 2.2.

## 2. Import formats

### 2.1 Officially supported formats [Documented]

Via File > Open and File > Import Tracks:

- `.ustx` (native)
- `.ust` (UTAU)
- `.vsqx` (VOCALOID 3/4)
- `.mid` / `.midi`
- `.ufdata` (UtaFormatix)
- `.musicxml`

Audio import (File > Import Audio): `.wav`, `.mp3`, `.ogg`, `.flac`.

Format detection is by content sniffing of the first lines (for example `MThd` for MIDI,
`score-partwise` for MusicXML) [Source: `OpenUtau.Core/Format/Formats.cs`].

### 2.2 Why we do not use OpenUtau's MusicXML import

**OpenUtau does support MusicXML import.** An earlier assumption in this project that it
does not was wrong. We nevertheless intentionally do **not** use it in the v1 pipeline,
because our application must:

- resolve repeats deterministically;
- validate the performance timeline;
- validate TTBB part assignments (explicit `VoiceRole`);
- validate lyrics;
- produce a known, flattened performance sequence;
- write a manifest describing the expected output;
- fail safely on unsupported notation.

The pipeline is therefore `MusicXML -> our parser -> validated/expanded Song -> MIDI
interchange -> OpenUtau`, not `MusicXML -> OpenUtau`.

For reference, the built-in importer [Source: `Format/MusicXML.cs`]:

- creates one track per MusicXML part;
- ties extend a single note across measures (fine);
- multi-syllable words: appends later syllable text to the first note and marks the
  following notes `+`. This is a heuristic on syllable text, not on MusicXML `syllabic`;
- slurs become `+~`, which conflates a slur with a melisma;
- reads tempo from `sound` elements and time signatures per measure;
- **has no handling for repeats**, grace notes, or voltas.

Parsing ourselves keeps rule 4 (never alter pitches) and rule 5 (report ambiguity)
enforceable in our code instead of inside someone else's importer.

### 2.3 MIDI import behavior [Source: `Format/MidiWriter.cs`, `LoadProject`]

- One `UVoicePart` per MIDI track chunk that contains notes. Track name comes from
  `SequenceTrackNameEvent`.
- Lyrics: `LyricEvent` meta-events are collected and **matched to notes by identical tick**.
- A note with no matching lyric receives the default lyric from the note presets.
- The lyric text `-` is converted to `+~`.
- Tempo map and time signatures are imported, and ticks are converted to the project
  resolution (480 per quarter) by `time * 480 / PPQ`.
- **No overlap handling.** Overlapping or polyphonic notes are not resolved. Our validator
  must guarantee monophony before export.
- **No singer or phonemizer is assigned.** The user sets these per track after import.

Consequences for our exporter:

1. Write MIDI at **PPQ 480** for v1 so tick conversion is exact. PPQ is an exporter
   parameter and can change later without touching the domain model.
2. The domain model keeps `Fraction` quarter-note time and never uses ticks. Export is
   `Fraction -> ticks -> verify exact representability -> write`. If an onset or duration
   is not an integer number of ticks (for example some tuplets), it is a validation
   **ERROR**, never rounded.
3. Place each lyric event at the note's exact onset tick.
4. Do not rely on the default lyric. Every note gets an explicit lyric.
5. Escape the special case `-`, see section 5.

## 3. CLI and headless rendering

Finding: **no documented CLI or headless rendering interface exists.**

- `OpenUtau/Program.cs` passes `args` straight to Avalonia's desktop lifetime and
  inspects none of them [Source]. There is no argument parsing, no "open this file" flag,
  and no render mode.
- The README and wiki mention no command-line interface [Documented by absence].
- The FAQ has no CLI, batch, or headless content.
- **Legacy plugins** (Batch Edit > Legacy Plugin) are UTAU-style note editors. They edit
  notes in the piano roll and are not a rendering path.
- **Phonemizer and Editing Macro plugin APIs** are in-process C# extension points for
  phoneme and note manipulation. They do not expose rendering control.
- OpenUtau is MIT-licensed. One could reference `OpenUtau.Core` from .NET, but that
  is an internal library with no documented external contract. Out of scope for v1.
- Release notes seen in one search result mention a **"DAW integration API"** with an
  in-app bridge guide [from a summary only; version unverified]. **Unresolved M0 item.**
  We do not design around it. Before M6, investigate it against the current official
  release, source and documentation, and use it only if it provides a documented and
  stable mechanism that fits our use case.

Decision: no automation in v1. `AutomatedOpenUtauBackend` stays a reserved name only.

## 4. USTX generation

- USTX is YAML 1.2 (UTF-8) documented on the official wiki [Documented].
- Current `ustx_version` is `0.6`. Resolution is fixed at 480 ticks per quarter note.
- Top-level sections: project metadata, `tempos`, `time_signature`, `tracks`, `voice_parts`,
  `wave_parts`. Note fields include `position`, `duration`, `tone` (C4 = 60), `lyric`,
  plus optional `pitch`, `vibrato`, `phoneme_expressions`, `phoneme_overrides`.
- Tracks carry `singer` and `phonemizer`, which would let us preselect them.
- The wiki recommends `ruamel.yaml` rather than PyYAML for YAML 1.2.
- **No compatibility or deprecation policy is stated.** The wiki already marks three
  legacy fields deprecated (`bpm`, `beat_per_bar`, `beat_unit`), which shows the format
  does change.

Assessment: documented, but not promised stable. A generated USTX could break on a
future OpenUtau release, and it would reference singer identifiers that depend on the
user's install.

Decision:

- **v1 uses MIDI.** It is a standard, version-independent, and carries everything we need.
- A USTX exporter is a **possible later optional backend**: off by default, gated on an
  exact `ustx_version` match, and refusing unknown versions. It adds the convenience of a
  preselected singer and phonemizer.
- Generated USTX files are never committed to Git.

## 5. Lyrics and melismas

### 5.1 What the English phonemizers expect [Documented]

For the English phonemizers (EN ARPA, EN ARPA+, EN C+V) and for slur notes generally:

- A whole word is typed on its **first** note.
- `+` on following notes moves to the **next syllable** of that word.
- `+~` (or `+*`) **extends the current syllable** instead of advancing.
- `+` followed by a number forces alignment to a specific phoneme position.
- Bracketed phonetic hints (`[l ih v]`) give explicit pronunciation.
- Pronunciation comes from a dictionary. Custom entries can go in `arpasing.yaml`.

### 5.2 Mapping from MusicXML lyric data

Principle: **MusicXML is authoritative.** The `Song` model keeps the original lyric text,
`syllabic` value and melisma (`extend`) information unchanged. The MIDI representation
below is a derived, deterministic transformation. Every transformation is documented here
and recorded in `limitations.txt` and `manifest.json`. If a transformation could materially
change what is sung, it is a validation ERROR, not a WARNING.

MusicXML provides, per note: lyric `text`, `syllabic` (single, begin, middle, end),
`extend` (melisma line), and `elision`. Proposed mapping, written into the MIDI lyric event:

| MusicXML situation | Lyric event text |
|---|---|
| `single` syllable | the word |
| `begin` syllable | the **complete word**, reassembled from its begin/middle/end syllables |
| `middle` / `end` syllable (next note of same word) | `+` |
| Syllable held over more notes (extend/melisma, or tied/slurred continuation carrying no new lyric) | `+~` |
| Note with no lyric and no extension | **validation issue** (see 5.3) |

Example: "beautiful" sung `beau-ti-ful`, with `beau` sustained over two notes, becomes
`beautiful`, `+~`, `+`, `+`.

### 5.3 Limitations we must report, never hide

If the data cannot be expressed in MIDI lyric events without changing meaning, the
validator emits a WARNING or ERROR and names the measure. We never silently edit lyrics.

- **Ambiguous syllable reconstruction.** When begin/middle/end syllables of a word cannot
  be reassembled unambiguously (missing `end`, interrupted by a rest or another part's
  lyric, conflicting `syllabic` values), the validator emits an ERROR if the sung text
  could change, otherwise a WARNING naming the measure.
- **Pronunciation of reassembled words.** The phonemizer re-syllabifies from its
  dictionary. The syllable split in the score may not match the dictionary's split, so `+`
  could land on the wrong syllable. We cannot detect this without the dictionary.
  Reported as a standing note per song, not per word.
- **No phonetic hints from MusicXML.** Barbershop scores often use spelling like "ya",
  "dem", "ooh". We pass them through as typed. The user can add hints inside OpenUtau.
- **Special characters.** A lyric that is exactly `-`, begins with `+`, or contains `[`
  or `]` would be interpreted by OpenUtau. These produce a WARNING instead of being
  rewritten.
- **Elisions** (two syllables on one note) have no direct equivalent. WARNING.
- **Punctuation** in lyric text may be read by the phonemizer. We strip nothing silently;
  we warn when present.
- **Melisma vs. tie vs. slur.** We use MusicXML `extend` and tie semantics, not slurs,
  to choose `+~`. A slur with no `extend` and no new lyric is a WARNING.
- **Unpitched sounds** (humming, "mm", breath, rests) need singer-specific handling.
  Flag, do not guess.
- **Multi-verse lyrics.** v1 uses verse 1 only and warns if other verses are present.
- **Multiple lyric lines per note** are an ERROR in v1.

### 5.4 Not yet confirmed

Section 7 lists the tests that confirm `+` and `+~` actually survive MIDI import and
behave as expected. Until then, treat 5.2 as the design, not a guarantee.

## 6. Proposed v1 handoff workflow

```
MusicXML
  -> BarbershopLearningTracks: parse, validate, expand repeats
  -> writes bundle:  <work dir>/<Song>/openutau_bundle/
        <Song>.mid          single file, 4 named tracks (Tenor, Lead, Baritone, Bass)
        manifest.json       roles, per-part note counts, expected duration, tempo map,
                            PPQ, tool version, checksum of the .mid
        limitations.txt     lyric limitations from section 5.3 for this score
        INSTRUCTIONS.txt    exact steps below
  -> user in OpenUtau:
        1. File > Open: <Song>.mid
        2. For each of the 4 tracks: choose singer and English phonemizer
        3. Listen, correct pronunciation as needed
        4. File > Export Audio > Export wav Files
        5. Note the export folder (next to the saved project)
  -> BarbershopLearningTracks "Import stems":
        user selects the 4 WAVs (or the export folder) and confirms which file is which role
  -> stem ingest validates, then FFmpeg mixes the 13 outputs
```

Design decisions:

- **Single MIDI file with four tracks**, not four files. One open step, and track names
  identify roles.
- **Role assignment is confirmed by the user.** We may pre-fill from filenames, but we do
  not guess silently, because export file naming is unverified.
- **Ingest validates** each stem before mixing:
  - all four present, readable, non-silent;
  - same sample rate and channel count (otherwise resample explicitly to a documented
    format, never implicitly);
  - duration within a configurable tolerance of the manifest's expected duration;
  - durations match each other within tolerance. Shorter stems are padded with silence
    at the end only, and this is reported.
  - failure aborts generation. Nothing partial is written.
- The user may also reuse the same ingest step with stems from another synthesizer. That
  is the `ExternalStemsBackend`.
- `ManualOpenUtauBackend` writes the bundle and then waits for stems. The pipeline stage
  is split in two, "prepare" and "ingest and mix", so the app does not block while the
  user works in OpenUtau.

## 7. Hands-on checks (required before M6)

Needs OpenUtau installed (not done yet) and a voicebank. Use a short public-domain test
melody, not a copyrighted arrangement. Record results here. Do not implement behavior
that depends on an unchecked item.

1. Current official OpenUtau release version (record it here; do not hard-code it).
   Also whether `File > Open` accepts a command-line path (record only; we will not use it).
2. MIDI import preserves a lyric on each note at the exact tick, with PPQ 480.
3. `+` and `+~` entered as MIDI lyric text behave as in 5.1 with the EN ARPA phonemizer.
4. A lyric that is exactly `-` becomes `+~`. Confirm our escape/warn plan.
5. A note with no lyric gets the default lyric (confirm what it is).
6. Tempo and time signature import correctly, including a mid-song tempo change.
7. A pickup measure and a rest at the very start keep correct timing.
8. Export wav Files: output folder location, **file naming**, sample rate, channel count,
   bit depth.
9. All four exported stems have equal length when the parts end at different times.
   Check leading offset with a click-aligned test.
10. Track names from the MIDI file are preserved in OpenUtau and in exported WAV names.
11. Singer and phonemizer assignment behavior after MIDI import (per track, defaults,
    whether it persists).
12. Investigate the "DAW integration API" against the current release, source and docs;
    use it only if documented and stable (see section 3).

## 8. Open questions

- Which English singer and phonemizer do we recommend in the docs? Not decided. The
  domain model must not depend on any specific voicebank. Singer and phonemizer will be
  user-selected settings later.
- Whether to ship an optional USTX exporter after v1.

## Sources

- OpenUtau wiki: home, Getting Started, Phonemizers, Legacy Plugins, USTX File Format, FAQ
  (`github.com/stakira/OpenUtau/wiki`, mirrored at `github.com/openutau/OpenUtau`)
- Source: `OpenUtau/Program.cs`, `OpenUtau.Core/Format/Formats.cs`,
  `OpenUtau.Core/Format/MidiWriter.cs`, `OpenUtau.Core/Format/MusicXML.cs` (master branch)
- OpenUtau releases page (0.1.57x notes mention a DAW integration API)
