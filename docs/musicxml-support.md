# MusicXML support

Status: **M3 research complete and plan approved. No parser code exists yet.**
This document records what MusicXML and MuseScore actually do, and the deliberately
limited subset the v1 parser will support. Implementation plan: [m3-plan.md](m3-plan.md).

## Method and authority

- **Primary authority:** the W3C MusicXML 4.0 reference
  (`w3.org/2021/06/musicxml40/musicxml-reference/`).
- **Where the reference is silent**, behavior was observed in **MuseScore Studio 4.7.4**
  (installed locally). Tiny original MusicXML scores were authored by hand, then
  imported and re-exported by MuseScore's command line, once to MusicXML and once to MIDI.
  MuseScore's MIDI export plays repeats and endings out, so it serves as an independent
  **oracle** for sounding pitch and for the expanded timeline.
- Fixtures and oracle data are in `tests/fixtures/musicxml/` (see its README). All scores
  are original and trivial. No copyrighted arrangements are used.

Limits of this research (read before relying on it):

- The scores in `tests/fixtures/musicxml/` were **authored as MusicXML and round-tripped
  through MuseScore**, not drawn in the MuseScore editor. The layout of a real barbershop
  template was checked separately against one real export (see "Evidence from a real TTBB
  export" below). That export is **not** in the repository.
- MuseScore's import/export is consistent with itself, which shows how it *interprets* and
  *writes* pitch, but it is not the specification.
- The W3C reference pages are terse. Several semantics (below) are not stated there at all.

## Findings

### Pitch, clefs and transposition

| Question | MusicXML 4.0 reference | MuseScore 4.7.4 (observed) | M3 decision |
|---|---|---|---|
| What does `<pitch>` mean? | Defined as step + alter + octave. The page does **not** say written or sounding. | Without `<transpose>`, `<pitch>` is the **sounding** pitch. With `<transpose>`, `<pitch>` is the **written** pitch. | `written_pitch = <pitch>` exactly as in the file. |
| `<clef-octave-change>` | "used for transposing clefs. A treble clef for tenors would have a value of -1." Silent on whether `<pitch>` is affected. | **No effect on `<pitch>` or sounding pitch.** A G-clef with octave change -1 and `<pitch>` C4 sounds MIDI 60. The same notes written as C5 sound MIDI 72. | Never creates a `PitchTransform`. |
| `<transpose>` | "what must be added to a written pitch to get a correct sounding pitch". Children: `diatonic?`, `chromatic`, `octave-change?`, `double?`. | `diatonic=-1, chromatic=-2` with written C5 sounds MIDI 70 (B-flat 4). | Maps 1:1 to `PitchTransform(diatonic, chromatic, octave_change)`. **`<double>` is rejected** (see below). |
| Both together | Not addressed. | Clef -1 plus `<transpose>` octave-change -1, written C4, sounds MIDI **48** (C3). Only `<transpose>` is applied. | **Applying both would double-transpose.** The clef is informational only. |
| Round trip | | MuseScore re-exports the same `<pitch>`, clef and `<transpose>` values it read, so its exporter writes sounding pitch for octave-clef staves with no `<transpose>`. | Consistent with the rule above. |

Consequences:

1. For a tenor part on a treble-8vb clef, expect `<clef-octave-change>-1` and **no**
   `<transpose>`. Then `written_pitch` equals the sounding pitch and the transform is the
   identity. The note sits an octave higher on the printed staff than it sounds; that
   printed position is not in `<pitch>`.
2. `<transpose>` can change mid-score (it appears inside `<attributes>`) and may carry a
   `number` attribute for a single staff. The parser tracks it per staff and stamps each
   note's `transform`.
3. If `<transpose>` omits `<diatonic>`, the sounding spelling cannot be derived without
   guessing. That is an ERROR unless the transform is a pure octave shift.
4. To satisfy "display the original notation", the plan proposes recording the clef per
   part as **informational only** (never used in pitch math). See open question 2.

**`<transpose><double>`.** The MusicXML 4.0 reference says `<double>` "indicates that the music
is doubled one octave from what is currently written" (below by default, above with
`above="yes"`; used for mixed flute/piccolo or cello/bass parts). That is a second sounding
note, which a `PitchTransform` (one written pitch to one sounding pitch) cannot express. It is
therefore **not ignored**: a `<transpose>` containing `<double>` is the ERROR
`TRANSPOSE_DOUBLE_UNSUPPORTED`, and notes under it are left out. A clef octave change is a
different thing and is never combined with it.

### Timeline

| Topic | MusicXML 4.0 reference | MuseScore observation | Decision |
|---|---|---|---|
| `<divisions>` | Divisions per quarter note; duration / divisions = quarter notes. May change in later `<attributes>`. Should not exceed 16383 for MIDI compatibility. | Writes `divisions` per its own choice (1, 2, 3, 6 seen); it changes the value on re-export. | Exact `Fraction(duration, divisions)`. Track divisions per part. Reject missing or zero. Accept a decimal string if present. |
| `<backup>` / `<forward>` | Backup moves the timeline cursor back by `duration`; used to move between voices and staves; may not cross a measure boundary. Forward moves ahead. | Voice 2 starting on beat 3 was exported as a single `<backup>`, with no `<forward>` and no leading rest. | Implement a per-measure cursor handling both. Gaps and omitted rests are legal and simply produce no events. Backup before the measure start is an ERROR. |
| `<chord/>` | A note with `<chord/>` shares the previous note's start. | Used for simultaneous notes in one voice. | Parsed as simultaneous notes (the model allows this). A chord inside a voice line is a validation ERROR in v1. |
| Time signature | `<time>` in `<attributes>`. | Written at the start of a measure. | A `<time>` at local position 0 (including after a `<backup>` that returns exactly to 0) is supported. **A `<time>` at a nonzero position in the measure is the generation-blocking ERROR `TIME_SIGNATURE_CHANGE_MID_MEASURE`.** The new meter is not applied, the measure keeps the meter it started with, and nothing is split or reinterpreted. Only simple meters (4/4, 6/8, ...) are supported; senza misura, additive and composite meters are `TIME_SIGNATURE_UNSUPPORTED`. |
| Short measures | | | A non-implicit measure shorter than the meter is the WARNING `MEASURE_INCOMPLETE`; its position on the timeline keeps the nominal meter length and no voice needs explicit rests. An overfull measure is the ERROR `MEASURE_DURATION_MISMATCH`. An implicit measure (pickup) may be short. |
| Tuplets | `<time-modification>` plus `<tuplet>` are notation. | An eighth triplet was exported with `divisions=3`, giving durations 1/3 quarter exactly. Sounding onsets 0, 160, 320 ticks at 480 PPQ. | Use `<duration>/<divisions>` as the authority. Never derive time from `<type>` and `<time-modification>`. Cross-check them as a WARNING on mismatch. |
| Pickup measure | `implicit="yes"`; "Pickup measures conventionally use `0` with implicit set to yes". Measure numbers need not be numeric or unique. | Pickup exported as `number="0" implicit="yes"`. MIDI starts the pickup at tick 0. | The timeline starts at the first note of the pickup. **No count-in convention is encoded.** Each note keeps the source measure number (0 for the pickup), its exact local offset from the start of that source measure, and its exact global position. `Note.beat` is `1 + local offset`, so the first note of a one-beat pickup is at beat 1 of measure 0; presenting it as "beat 4" is a later UI or analysis decision. Non-numeric or repeated measure numbers: warn and keep the source string in the message. |
| Ties | `<tie>` (sound) and `<tied>` (notation). | Both written. MIDI merges tied notes into one sounding note (one note-on). | `<tie>` is authoritative. Tied notes stay separate in the `Song` (flags set); a pure function merges them for synthesis. Unmatched or pitch-mismatched ties are ERRORs. |
| Tempo | `<sound tempo>` in a `<direction>`. | A score with no tempo marking exports **no** tempo at all (the real TTBB export below has none). | The parser preserves that no tempo was supplied (`Song.tempo_map` is empty) and never assumes 120 bpm. Missing tempo is **not** a parse error. Validation reports `TEMPO_MISSING`, a generation-blocking condition that the user resolves by supplying a tempo. |
| Cue notes | "a cue note is a silent note with no playback". | None observed in test files. | The spec says `duration` moves the musical position in `<note>` elements without `<chord/>`, and does not exempt cue notes. A cue note therefore **advances the cursor** by its duration but emits no event, and produces a `CUE_NOTE_SKIPPED` WARNING naming the line, source measure and beat. A cue note with `<chord/>` does not advance. |
| Grace notes | No `duration`; do not advance the cursor. | | ERROR `UNSUPPORTED_GRACE_NOTE` with line, measure and beat. Support may come later. A grace note that is also marked cue is treated as a grace note. |
| Unpitched notes | Have a `duration` and move the cursor. | | ERROR `UNSUPPORTED_UNPITCHED_NOTE`; the note advances time and is omitted. |
| `<type>` versus `<duration>` | `<type>` is the graphic note type. `<duration>` moves the musical position. | | `<duration>` is always the timing. `<type>` with `<dot>` and `<time-modification>` is only a cross-check: WARNING `DURATION_TYPE_MISMATCH`, never a timing change. Skipped when `<type>` is absent (allowed), for whole-measure rests, for an unknown type, and when `<time-modification>` is incomplete or uses `<normal-type>`/`<normal-dot>`. |

### Ties (implemented in M3b2a)

`<tie>` is "the tie sound" and is authoritative; `<tied>` is "the notated tie". The parser sets
`Note.tied_to_next` / `tied_from_previous` from `<tie>` alone and compares it with `<tied>`
(`continue` and `let-ring` are notation-only and ignored):

| `<tie>` | `<tied>` | Result |
|---|---|---|
| matches | matches | none |
| present | absent | WARNING `TIE_WITHOUT_TIED` (the sound tie is used) |
| absent | present | **ERROR `TIED_WITHOUT_TIE`**. The note is *not* tied; the diagnostic names the line, measure, beat, pitch and notated type so a future explicit UI repair ("treat it as a sound tie?") has what it needs. Nothing is repaired while parsing. MuseScore ties these notes; the specification gives no sound tie, so this is a documented divergence. |
| present | different types or counts | ERROR `TIE_TIED_MISMATCH` |
| any invalid `<tie type>` | | ERROR `TIE_TYPE_INVALID` |

Source notes are never merged in the `Song`. `core.timeline.merge_tied_notes(events, part_id=...)`
returns derived `PerformanceNote`s and tie diagnostics:

- Matching uses **exact sounding pitch** (`Pitch.absolute_semitones`, a `Fraction`): a tie may join
  C#4 and Db4, microtones need exact equality, and `Pitch.__eq__` is still spelled-pitch equality.
  The performed note keeps the first source note's spelling and lyrics and references every source
  note.
- A tie only continues into a note that starts **exactly** where the previous one ends, so ties
  across barlines and `divisions` changes work and a tie across a rest or gap is unmatched.
- Chord members pair by pitch, never by position in the chord.
- Diagnostic precedence for a tie stop at a given start: `TIE_AMBIGUOUS` (two or more open ties
  of that pitch end here; nothing is guessed) > paired > `TIE_PITCH_MISMATCH` (no open tie of that
  pitch, but one ends here) > `TIE_UNMATCHED_STOP` (no open tie ends here at all). A tie start
  never continued is `TIE_UNMATCHED_START`; a start already named by an ambiguity or mismatch
  diagnostic is not reported again.
- MuseScore comparison: chains, enharmonic ties, `<tie>`+`<tied>` and `<tie>`-only agree with its
  MIDI after merging (`e6_ties` is now an exact match). Invalid ties give the same attacks as
  MuseScore but are ERRORs for us.

### Tempo and meter (implemented in M3b2b)

**Tempo** comes only from `<sound tempo>` (inside a `<direction>` or directly in a measure), in
quarter notes per minute, as an exact `Fraction` (92.5 is 185/2; nothing is rounded).
- No tempo leaves `Song.tempo_map` empty. There is never a default and MuseScore's MIDI default
  of 120 is not score data. `TEMPO_MISSING` is a later validation condition.
- `tempo="0"` ("ask the user") is WARNING `TEMPO_ZERO_UNRESOLVED` and sets nothing. An invalid
  value is ERROR `TEMPO_INVALID`. A `<metronome>` without `<sound tempo>` is WARNING
  `METRONOME_WITHOUT_SOUND`; tempo is never inferred from it or from words such as "Allegro".
- **Position = cursor + offset**, with the offset in `divisions` converted exactly. Following
  MusicXML 4.0: a `<sound>`'s own `<offset>` applies and overrides the direction's; a direction's
  `<offset>` applies **only** with `sound="yes"` (default `no`: the sound takes effect at the
  current location). A position outside its measure is ERROR `TEMPO_OFFSET_OUT_OF_MEASURE`; it is
  never clamped.
- **MuseScore divergence (documented, pinned by permanent tests):** MuseScore 4.7.4 applies a
  direction's `<offset>` whatever `sound` says and ignores a `<sound>`'s own `<offset>`. We follow
  the specification; `test_parser_tempo_offsets.py` records both behaviors.
- Every explicit valid tempo is kept (even if equal to the previous one). Identical values at the
  same position, in one part or several, are one event; different values at the same position are
  ERROR `TEMPO_CONFLICT` and that position is left unresolved. A tempo declared in one part only
  (typical for MuseScore) is used.

**Meter**: `Song.time_signatures` has one `TimeSignature` per **effective change**. Each part
records the meter in effect at every measure; parts are compared by what is in effect (a part
that declares nothing inherits), and any difference is ERROR `TIME_SIGNATURE_CONFLICT`. Repeated
declarations of the same meter, in one part or several, add no event.

### Lyrics (literal parsing, M3c1)

The parser stores each `<lyric>` exactly as written on the note where it occurs. It does not
infer melismas, join syllables, choose a verse, fill gaps or produce OpenUtau text; interpretation
is the separate lyric analysis (M3c2).

| Source | Stored as |
|---|---|
| `<text>` | Verbatim (never stripped). Single `<text>` containing a space, undertie or underscore is one literal text. |
| `<syllabic>` | `Syllabic`; **absent is `UNSPECIFIED`**, never `single` (MuseScore re-exports `single`). |
| `number` | As written; **absent is `None`**, not `"1"`. `Lyric.logical_verse` groups an absent number with the default verse `"1"` without changing the source. |
| `name`, `time-only` | `Lyric.name` and `Lyric.time_only`, verbatim. `time-only` is also ERROR `LYRIC_TIME_ONLY_UNSUPPORTED` (it depends on the repeat pass). |
| `<extend>` | `Melisma`: none / **untyped** / start / continue / stop. Untyped is not translated to start in the source model. An extender with no text is an `EXTENSION` lyric. |
| `<humming/>`, `<laughing/>` | Preserved as `LyricKind.HUMMING` / `LAUGHING` (MusicXML 4.0: "a humming voice", "a laughing voice", replacing text). Not an error; later stages decide whether a backend can sing them. MuseScore drops them. |
| `<elision>` | `LyricSegment` with `joiner` (its text) and `joiner_smufl` (its `smufl` name). |
| MuseScore elision | Recognized only as `text, U+E551, text [, U+E551, text ...]` (SMuFL `lyricsElisionNarrow`, the only glyph MuseScore wrote for every elision form). Other private-use characters, including U+E550 and U+E552, are **not** elisions. |
| Any other multi-`<text>` shape, a second `<syllabic>` without an elision, a bad `<syllabic>` value, mixed humming/text, two `<extend>` | ERROR `LYRIC_TEXT_STRUCTURE_UNSUPPORTED`; nothing is concatenated on a guess. |
| Invalid `<extend type>` / empty `number` | ERROR `LYRIC_EXTEND_TYPE_INVALID` / `LYRIC_NUMBER_INVALID`. |
| No usable content (empty `<text>`, only `<syllabic>`) | WARNING `LYRIC_EMPTY`; the lyric is skipped. |
| `<end-line/>`, `<end-paragraph/>` | Ignored (formatting). |

Problems and placements:
- Two lyrics in the same **logical** verse on one note are ERROR `LYRIC_DUPLICATE_VERSE`. Both are
  kept; none is chosen. (MuseScore creates these itself when it moves a grace or chord lyric.)
- A lyric on a rest, cue, grace or unpitched note is the ERROR `LYRIC_ON_REST`,
  `LYRIC_ON_CUE_NOTE`, `LYRIC_ON_GRACE_NOTE` or `LYRIC_ON_UNPITCHED_NOTE`. Its literal text is in
  the message and it is **never attached to another note** (MuseScore moves a grace lyric to the
  next note and a later chord member's lyric to the first member; we do not).
- Lyrics on tied notes, including a tie continuation, stay on their own source notes.
- Slurs are not read and are not melisma evidence; a slurred lyric-less note stays lyric-less.

### Evidence from a real TTBB export

One real barbershop score supplied by the project owner (a 71-measure arrangement exported
from MuseScore Studio 4.7.4 as `.mxl`) was inspected **locally for structure only**. It is
not in the repository because it may be a commercial arrangement; a tiny original export
belongs in `tests/fixtures/musicxml/real/`. It is one data point, not a specification.

| Aspect | Observed |
|---|---|
| Parts | **Two** `<part>` elements, not four, inside a bracketed `<part-group>`: P1 named "TENOR" / "LEAD" (instrument "Tenor/Lead", sound `voice.tenor`) and P2 named "BARI" / "BASS" (instrument "Baritone/Bass", sound `voice.bass`). Part names contain a line break. |
| Sharing | **Tenor and Lead share a staff; Baritone and Bass share a staff.** Each part has one staff and two voices, numbered 1 and 2. |
| Staff element | No `<staves>` and no `<staff>` on notes. Staff 1 is implied and the parser must say so. |
| Clefs | P1: G clef line 2 with `<clef-octave-change>-1</clef-octave-change>`. P2: F clef line 4. One clef each, at the pickup measure. |
| `<transpose>` | **None**, in either part. |
| Divisions | 12. Time signature 4/4. |
| Timeline | A `<backup>` in every measure (two voices per staff) and a few `<forward>` elements, so both occur in real data. |
| Pickup | Measure `0` with `implicit="yes"`. |
| Not present | Tempo marking, repeats, endings, jumps, chords, grace notes, cue notes, elisions. |
| Lyrics | Verse 1 only, on voice 2 of P1 for almost every lyric and on both voices of P2, with 30 and 6 `<extend>` elements. Voice 1 of P1 carries very few lyrics. |

What this means:

- Line ids `P1/s1/v1`, `P1/s1/v2`, `P2/s1/v1`, `P2/s1/v2` are the normal case. The model's
  "one `Part` per voice line" design is confirmed; four named `<part>` elements are not
  guaranteed.
- Which voice is which singer is **not** in the file. Roles are assigned explicitly. A UI may
  later suggest a default, but the parser and model never infer one.
- A missing tempo is real. `TEMPO_MISSING` must be resolvable by user input.
- **One voice may carry lyrics for the whole staff.** A line with no lyrics (here, voice 1
  of the tenor/lead staff) is common. The parser stays literal and reports no lyrics. How a
  lyric-less line is voiced is an M4/M6 policy decision, never a parser guess.
- `<clef-octave-change>` with no `<transpose>` confirms rule 1: the tenor staff's `<pitch>`
  values are used as given.

### Voices, staves and TTBB layouts

- A `<part>` can hold several staves (`<staves>`, `<staff>` on each note) and several voices
  (`<voice>` on each note). The reference defines no link from a voice to "Tenor" or "Lead".
- Observed export of one part with two staves, voices 1 and 2 on staff 1 and two more on
  staff 2: MuseScore wrote voices **1, 2 on staff 1 and 5, 6 on staff 2**. Voice numbers are
  **not reused per staff**, and a staff-2 voice is not "voice 1".
- Four separate parts (one staff each, tenor and lead on treble-8vb, baritone and bass on
  bass clef) export as four `<part>` elements.
- Two simultaneous pitched notes in one logical voice (a chord or divisi) cannot be mapped to
  one singer without choosing which note belongs to whom. That would be a guess. The parser
  keeps both notes and validation reports an ERROR; no note is dropped or selected.

Decision: the parser produces one model `Part` per **voice line**, identified by
`(source part id, staff, voice)`. A line id such as `P1/s1/v1` is the `Part.part_id`, and
role assignments are keyed by line id. Roles are never inferred from names. Voice ids are
not assumed to be globally unique, contiguous, or to mean anything (`voice 1 = Tenor` is not
assumed). A missing `<staff>` means staff 1, and a missing `<voice>` is reported rather than
silently merged into another voice.

### Clef information (notation model)

Clefs are preserved for display and debugging only and **never participate in sounding-pitch
calculation**. Because clefs can change during a score and a part can have several staves,
they are not a field of `Part`. Instead the `Song` carries a tuple of immutable
`ClefChange` records: source part id, staff number, clef sign, clef line, octave change, source
measure and the exact timeline position at which the clef becomes active. A test asserts that
`<clef-octave-change>` leaves both `PitchTransform` and the sounding pitch unchanged, using the
`e1_*` fixtures and their oracles.

### Repeats and endings

| Topic | MusicXML 4.0 reference | MuseScore observation |
|---|---|---|
| `<repeat direction>` | `forward` starts a repeat, `backward` ends it. | Both written as a `<barline>` child. |
| `times` | "the number of times the repeated section is played". Does **not** say whether this counts the first play. Applies to backward repeats. | `times="3"` played the section **three times in total** (the first pass plus two repeats). Absent means 2. **This interpretation was verified against MuseScore 4.7.4 behavior (oracle files `e8_simple_repeat` and `e8b_repeat_times3`), not derived from the specification.** It applies to ordinary repeats only and is not generalized to D.C./D.S./coda jumps. |
| `<ending number type>` | `number` is "1" or "1, 2"; types `start`, `stop`, `discontinue`. No playback algorithm is stated. | Endings 1 and 2 played on passes 1 and 2, then the part continued after the final ending. `"1, 2"` then `"3"` with `times="3"` played passes 1, 2 and 3 in order. |
| Expanded sequence | | MuseScore MIDI gave: simple repeat 1-2-1-2-3; volta 1-2(end 1)-1-3(end 2)-4; times 3 gave 1-2-1-2-1-2-3. These match the conventional reading and are stored as oracle files. |
| Jumps (D.C., D.S., segno, coda, fine) | `<sound dacapo/dalsegno/segno/coda/tocoda/fine>` | **Inconclusive.** A hand-written D.C. al Fine was not played as a jump by MuseScore. Not verified. |

Decision: no jump is ever expanded in v1. Any of those `<sound>` attributes is an ERROR.

### Lyrics

| Topic | MusicXML 4.0 reference | MuseScore observation | Decision |
|---|---|---|---|
| `<syllabic>` | single, begin, middle, end. | Preserved exactly. | `Lyric.syllabic`. |
| Verses | `number` attribute. | Two verses on one note kept as two `<lyric>` elements. | `Lyric.verse`. More than one verse or lyric line is reported (earlier decision). |
| `<extend>` | "always treated as the start of the extension" when `type` is absent; `type` may be start, stop, continue. | MuseScore writes `<extend/>` **without a type** on the first note's lyric. The following notes in the melisma have **no `<lyric>` element at all** (my hand-written continue/stop lyrics were dropped). | The parser is literal: the first note gets `Melisma.START`; later lyric-less notes stay lyric-less. A separate analysis step (see plan) decides which lyric-less notes are melisma continuations, tie continuations, or missing lyrics, and reports anything ambiguous. |
| Elision | `<elision>` element between text parts. | MuseScore exported `the`, a glyph, `ir` as **three consecutive `<text>` elements**, with **no `<elision>`** and no second `<syllabic>`. | Support `<elision>`. For consecutive `<text>` elements without `<elision>`, keep the pieces and emit a WARNING; never merge silently. |

### Compressed `.mxl`

- MuseScore wrote a ZIP with `META-INF/container.xml` and `score.xml` (the real TTBB export
  did the same).
- `container.xml` held `<rootfile full-path="score.xml">` with **no `media-type`**, so the
  loader must not require one.
- Archive handling: read `META-INF/container.xml` and follow its rootfile path. Reject, with a
  typed error, a missing container, a container with no rootfile, ambiguous multiple
  rootfiles, a rootfile that is absent from the archive, an absolute or `..` path, an
  unreasonable decompressed size, and an unreasonable compression ratio. Never extract to
  disk; read named members in memory only.
- **Rootfile selection (v1).** A `<rootfile>` is a candidate when its `media-type` is absent
  or is `application/vnd.recordare.musicxml+xml` or `application/vnd.recordare.musicxml`
  (compared case-insensitively). Exactly one candidate is used, none is an error, and several
  are an error because choosing between them would be a guess. Rootfiles with any other
  media type (PDF, MIDI, ...) are not candidates.
- **Encryption.** Only the members that must be read matter: `META-INF/container.xml` and the
  selected rootfile are rejected if encrypted. Other members, encrypted or not, are never
  opened and do not make the score fail, but every entry still counts toward
  `max_archive_entries`.
- **Limits** (`LoaderLimits`, binary units): 50 MiB per score (also for plain XML), 50 MiB total
  relevant content, 1 MiB for `container.xml`, 100:1 compression ratio, 1000 entries.

### XML safety

- MuseScore's XML begins with a `DOCTYPE` that has a PUBLIC identifier. defusedxml's
  default parse accepts it, but **`forbid_dtd=True` rejects MuseScore files** (tested).
- The DOCTYPE is allowed only as far as needed to parse normal MuseScore output. Entity
  declarations and expansion stay forbidden (`forbid_entities=True`), external resources
  stay forbidden (`forbid_external=True`), and no DTD or other network resource is ever
  fetched.
- Security tests (M3a): ordinary MuseScore DOCTYPE accepted; internal malicious entity
  (billion laughs) rejected; external entity rejected; malformed XML rejected.

## Supported subset for v1

Supported (parse and preserve):

- `score-partwise`, any number of parts, plain `.musicxml` / `.xml` and compressed `.mxl`.
- `divisions`, `time`, `<sound tempo>`, `clef` (informational), `transpose`.
- Notes and rests with exact `duration`, `chord`, `voice`, `staff`, `tie`, tuplets via duration.
- `backup` and `forward`; pickup measures (`implicit`).
- Lyrics: `syllabic`, `text`, `extend`, `elision`, multiple verse numbers.
- Repeats as in the table below.

Reported as an ERROR (generation stops): grace notes, unpitched notes, `score-timewise`,
jump markers (D.C./D.S./coda/fine), nested or unresolvable repeats, repeat structure that
differs between parts, time-signature problems that make timing ambiguous, measure
durations that do not match the time signature (except pickups), `backup` crossing a measure
start, unmatched ties, and `transpose` without enough information to spell the result.

Reported as a validation condition (not a parse error): **no tempo** (`TEMPO_MISSING`,
generation-blocking, resolved by user input) and simultaneous pitched notes in one voice line.

Reported as a WARNING: cue notes (skipped but still advancing time), non-numeric or repeated measure numbers,
`<tied>` without `<tie>`, multiple `<text>` elements in one lyric, more than one verse,
`<metronome>` without `<sound tempo>`, `type`/`time-modification` disagreeing with `duration`.

Silently ignored (no effect on timing or pitch): layout, fonts, `print`, stems, beams,
dynamics, articulations, `harmony`, credits.

## Repeat structures

Any repeat structure that cannot be resolved deterministically is a validation **ERROR**
that prevents generation. The intended performance order is never guessed.

| Phase | Structure | Rule |
|---|---|---|
| 1 | Forward repeat (start) | Marks the section start. |
| 1 | Backward repeat (end) | Plays the section `times` times in total (default 2). With no preceding forward repeat the section starts at the beginning of the piece, as in the MuseScore oracle. |
| 1 | Sequential, non-nested repeats | Each is expanded in order. |
| 2 | First/second endings (voltas) | `number` lists the passes on which the ending plays; `"1, 2"` form accepted. Must be a complete, consistent set. |
| Not supported | Nested repeats, jumps and codas, `discontinue` without a clear structure, endings that skip a pass | ERROR. |

All parts must expand to the **same measure order**, otherwise the ERROR is
`REPEAT_MISMATCH_ACROSS_PARTS`. Phase 1 is validated against the oracle files; phase 2
against the volta oracles.

## Open items

- The real-export evidence comes from one score. A tiny original export is still wanted in
  `tests/fixtures/musicxml/real/`.
- D.C./D.S./coda behavior in a MuseScore-authored score remains unverified (unsupported).
- How a lyric-less line is voiced is an M4/M6 decision.
