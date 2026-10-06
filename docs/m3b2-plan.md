# M3b2 plan: musical structure and special cases

Status: **approved with the decisions in "Approved decisions" below. No M3b2 code existed when
this was written.** Implementation is split into M3b2a (ties and note semantics) and M3b2b
(tempo, meter, TTBB integration).
Builds on M3b1 (commit `76768d5`). Research basis: MusicXML 4.0 reference, plus MuseScore Studio
4.7.4 round trips stored in `tests/fixtures/musicxml/tempo_ties/` (inputs, re-exports, and MIDI
oracles with tempo events).

## Research findings

### `<tie>` versus `<tied>`

| Source | Statement |
|---|---|
| MusicXML 4.0 | `<tie>` represents "the tie sound"; `<tied>` represents "the notated tie". `<tie type>` is `start` or `stop`. `<tied type>` is `start`, `stop`, `continue` (system breaks) or `let-ring` (a single, unpaired element). `<tied>` may connect enharmonically equivalent notes with different steps. |
| Authority | **`<tie>` is authoritative for playback and for what is sung.** `<tied>` is notation. |
| MuseScore | Merged a tie written with `<tie>` only, with `<tied>` only, and with both. It merged enharmonic ties (C#4 to Db4 gave one attack). It did **not** merge a tie between different pitches (C4 to D4 sounded twice). Chains (start, stop+start, stop) became one note. Unmatched starts and stops were ignored without error. |

MuseScore's `<tied>`-only behavior differs from the specification (which gives no sound tie).
That is a quirk, not something to copy silently.

### Tempo

| Topic | MusicXML 4.0 | MuseScore 4.7.4 |
|---|---|---|
| Unit | `<sound tempo>` is in quarter notes per minute. | Same. Decimals were kept (`92.5` came out as 92.5). |
| `tempo="0"` | "prompts the sound-generating program to ask the user". | Ignored; its MIDI shows its default 120. |
| No tempo | Valid. | Writes a default 120 into its MIDI. We never copy that default. |
| `<offset>` | Units are divisions. A **direction** `<offset>` affects playback **only if `sound="yes"`** (default `no`, "for compatibility"); otherwise a `<sound>` in the direction takes effect at the current location. A `<sound>`'s **own** `<offset>` child overrides the direction's and always applies. | **Applies a direction's `<offset>` whatever `sound` says** (no, yes and absent all moved the tempo to the cursor plus the offset) and **ignores a `<sound>`'s own `<offset>`** (the tempo stayed at the cursor). |

> **Correction (M3b2b).** The first version of this plan said MuseScore "ignores offsets
> entirely". Re-reading the oracle (`tempo_ties/oracle/t_b..t_e`) showed that was wrong: the
> direction was placed after the first note (480 ticks) and MuseScore put the tempo at 960 for
> `sound="no"`, `"yes"` and absent (it applied the 480-tick offset), but at 480 for the
> `<sound>`'s own offset (it ignored it). Our implementation follows the specification, so it
> agrees with MuseScore only for `sound="yes"` and for no offset; see the permanent tests in
> `test_parser_tempo_offsets.py`.
| `<metronome>` | Notation. | Written alongside `<sound tempo>`. |

### Other

- `<type>` is the graphic note type; `<duration>` is what moves the musical position
  (`duration`: "moves the musical position when used in `<note>` elements that do not contain a
  `<chord>` child"). The reference does not call `<type>` non-authoritative in so many words, so
  the policy below treats `<duration>` as time and `<type>` as a cross-check.

## 1. Ties: policy, matching, and the pure merge helper

**Source notes are never mutated or removed.** Merging is a pure function over a voice line's
source notes and returns a derived performance representation.

### Parsing (parser)
- `<tie type="start">` sets `tied_to_next`; `<tie type="stop">` sets `tied_from_previous`. A
  note with both is a chain member. A tie type other than `start`/`stop` is `TIE_TYPE_INVALID`
  (ERROR). Rests never carry ties.
- `<tied>` is compared with `<tie>` for diagnostics only (policy below) and never sets flags.

### `merge_tied_notes(events, *, part_id) -> TieMergeResult`
(New `core/timeline/ties.py`. Result: `notes: tuple[PerformanceNote, ...]`,
`issues: ValidationResult`.)

`PerformanceNote` (new, `models/performance.py`, frozen): `start`, `duration` (exact sum),
`pitch` (the **first** source note's sounding pitch, or `None` for a rest), `source` (the tied
source notes in order, untouched), `measure`/`beat` of the first note, and the first note's
lyrics. Rests pass through as single-source events.

Algorithm, per voice line, over events ordered by start:
1. Keep a list of **open ties**: sounding notes (or merged groups) with `tied_to_next` whose end
   time is known.
2. For each sounding note `n`, if it has `tied_from_previous`: among open ties whose **end equals
   `n.start` exactly** and whose **sounding pitch equals `n`'s**, take the match. Exactly one
   match: extend it (add duration, append to `source`), and `n` creates no new attack. More than
   one (two unison notes tied at once): ERROR `TIE_AMBIGUOUS`, nothing is paired.
3. No match: if open ties ended at `n.start` but none have this pitch, `TIE_PITCH_MISMATCH`
   (ERROR); otherwise `TIE_UNMATCHED_STOP` (ERROR). In both cases `n` starts a new attack so the
   output stays defined.
4. If `n` also has `tied_to_next`, the extended group stays open, ending at `n.end` (chains).
5. An open tie whose end passes with no continuation, or that is open at the end of the line, is
   `TIE_UNMATCHED_START` (ERROR), located at the note that started it.
6. A tie across a rest or any gap is unmatched, because the end must equal the next start exactly.

Chord members are matched **by sounding pitch**, so simultaneous notes can never be paired with
the wrong neighbour. Exact `Fraction` positions make ties across barlines and across `divisions`
changes work with no special case. Across repeat jumps (M3d) matching runs on the expanded
performance order.

### Spelling versus sounding pitch
Matching compares **sounding** pitch, not spelling. This is what the specification allows
(`<tied>` may join enharmonic equivalents) and what MuseScore does (C#4 to Db4 tie). The
comparison uses a new exact `Pitch.absolute_semitones` (a `Fraction`, so microtonal pitches
compare exactly without ever using an integer MIDI number). If a `<transpose>` changes between
two tied notes, the sounding pitches are compared, so a change that moves the pitch is a
`TIE_PITCH_MISMATCH`, never silently paired. The merged note keeps the first note's spelling.

The parser calls the helper once per line only to collect tie issues; `Song` keeps the source
notes. The exporter and validator call it later for the performance view.

### `<tie>` / `<tied>` policy
`<tie>` decides. Compare the multisets of `start`/`stop` in `<tie>` and `<tied>` per note
(ignoring `continue` and `let-ring`, which are notation-only):

| `<tie>` | `<tied>` | Result |
|---|---|---|
| matches | matches | no issue |
| present | absent | WARNING `TIE_WITHOUT_TIED` (the sound tie wins; the notation lacks it) |
| absent | present | **ERROR `TIED_WITHOUT_TIE`**: the notation shows a tie but the sound says none, and the choice changes what is sung. MuseScore plays it as a tie; the spec does not. Never silently agreed. |
| present | different types or counts | **ERROR `TIE_TIED_MISMATCH`** |

## 2. Tempo

Algorithm: collect each `<sound tempo>` (inside a `<direction>` or directly in the measure) at the
XML cursor with its `divisions` at that moment.
1. **Value.** Parse the decimal exactly as a `Fraction` (92.5 is 185/2). **No domain change is
   needed:** `TempoChange.bpm` is already an exact `Fraction`, so nothing is rounded. Rounding to
   a MIDI tempo happens only in the M6 exporter. A non-numeric or negative value is `TEMPO_INVALID`
   (ERROR). `tempo="0"` ("ask the user") records **no** tempo and gives WARNING
   `TEMPO_ZERO_UNRESOLVED`, which matches the plan to resolve tempo by user input.
2. **Position** = measure start + cursor + offset, where the offset is converted with the current
   divisions to an exact quarter-note `Fraction`, using the specification's rule:
   the `<sound>`'s own `<offset>` if present; otherwise the direction's `<offset>` **only if
   `sound="yes"`**; otherwise zero.
3. **Validity.** After the measure length is known, a position before the measure start or after
   its end is `TEMPO_OFFSET_OUT_OF_MEASURE` (ERROR). Nothing is clamped.
4. **Within a part.** Events are sorted by position. Same position and same value is one event;
   same position and different value is `TEMPO_CONFLICT` (ERROR).
5. **Across parts**: see section 4.
6. `<metronome>` without a `<sound tempo>` is WARNING `METRONOME_WITHOUT_SOUND`. Tempo is never
   inferred from `<metronome>` or from words such as "Allegro".

An absent tempo leaves `Song.tempo_map` empty (no 120 default). `TEMPO_MISSING`, and the case of a
first tempo that starts after position 0, are M4 validation.

## 3. Time-signature map

M3b1 already tracks the meter in effect per measure. M3b2 builds `Song.time_signatures`:
1. For each part, record the **effective meter at the start of every measure**.
2. Across parts, at every measure the effective meters must agree; any difference is
   `TIME_SIGNATURE_CONFLICT` (ERROR, located at the first disagreeing part and measure). A part
   that declares nothing simply inherits, so parts are compared by what is in effect, not by
   what was written.
3. Walk the measures once and emit one `TimeSignature(position, beats, beat_type)` whenever the
   agreed effective meter changes (and for the first measure). Identical declarations in several
   parts, or a restatement of the same meter, produce a single event or none.

(Tempo keeps every explicit event, deduplicated only at identical position and value; meter
records changes. That asymmetry is deliberate: a meter restatement carries no information, but a
tempo restatement is an explicit instruction.)

## 4. Cross-part tempo reconciliation
Merge the parts' tempo events by position. Identical value at the same position becomes one
`TempoChange`. Different values at the same position are `TEMPO_CONFLICT` (ERROR) naming both
parts. A tempo declared in only one part is simply included. The result is strictly increasing and
valid for `Song.tempo_map`.

## 5. Cue, grace and unpitched notes (replacing `NOTE_KIND_NOT_SUPPORTED_YET`)

| Kind | Timeline | Output | Diagnostic |
|---|---|---|---|
| Cue | Advances normally (`duration`, not for `<chord/>`) | Omitted from singer events | WARNING `CUE_NOTE_SKIPPED` |
| Grace | No advance (no duration) | Omitted | ERROR `UNSUPPORTED_GRACE_NOTE` |
| Unpitched | Advances by its duration | Omitted | ERROR `UNSUPPORTED_UNPITCHED_NOTE` |

A grace note that is also marked cue is treated as grace. Each issue carries the best available
location: the source line `Pn/sN/vN` when staff and voice are readable, otherwise the part id,
plus source measure and beat.

## 6. Duration and type consistency
WARNING `DURATION_TYPE_MISMATCH` when `<type>` (with `<dot>` and `<time-modification>`) implies a
different exact duration from `Fraction(<duration>)/divisions`. Timing **always** follows
`<duration>`; the warning never changes it. The check is skipped when `<type>` is absent, for
`<rest measure="yes">`, and when `<normal-type>`/`<normal-dot>` make the expectation ambiguous.
It also adds `MEASURE_NUMBER_REPEATED` (WARNING) for repeated source measure numbers in a part
(without repeat expansion yet).

## 7. TTBB-style fixture
Original and synthetic, mirroring the observed structure but not copied from any score:
`tests/fixtures/musicxml/ttbb/`
- `ttbb_layout.musicxml`: two parts ("TENOR\nLEAD", "BARI\nBASS") in a bracketed part group, one
  staff each with voices 1 and 2, implied staff, divisions 12, a one-beat implicit pickup (measure
  0), G clef with octave change -1 and F clef, a `<forward>`, no tempo, no `<transpose>`, a tie
  across a barline, a mid-score 3/4 measure.
- `ttbb_layout_tempo.musicxml`: the same with the same explicit tempo in both parts (reconciled to
  one event) and a second tempo change in one part only.
- MuseScore re-exports of both and a MIDI oracle JSON each (notes and tempo events).

## 8. MuseScore oracle strategy
- Specification is the authority; MuseScore is evidence. Each comparison is labelled either
  **agreement** (our result equals MuseScore's MIDI) or **documented divergence** (we follow the
  specification or safety, MuseScore differs).
- Agreement: all `u_*` tie fixtures where we merge as MuseScore does (`u_chain`, `u_tie_and_tied`,
  `u_tie_only`, `u_enharmonic`), including **e6, which becomes an exact match after merging**;
  `t_a` and `t_f` tempo positions and values, `t_g` decimal tempo, and both TTBB fixtures.
- Documented divergences (each has a test that asserts our behavior and cites the oracle):
  `u_tied_only` (we ERROR, MuseScore ties), `u_pitch_mismatch`/`u_unmatched_*` (we ERROR,
  MuseScore sounds both notes), `t_b`/`t_e` (direction offset with `sound` no/absent: we keep the tempo at the cursor,
  MuseScore applies the offset) and `t_d` (a `<sound>`'s own offset: we apply it, MuseScore
  ignores it; `t_a` and `t_c` agree), `t_h` and no-tempo fixtures (MuseScore writes 120, we leave the tempo
  unresolved).
- Tempo oracle values are compared exactly: MIDI microseconds-per-quarter are compared to
  `60_000_000 / bpm` as exact rationals, never as floats.

## 9. Files

Created: `models/performance.py`; `core/timeline/__init__.py`, `core/timeline/ties.py`;
`core/musicxml/ties.py` (`<tie>`/`<tied>` reading), `core/musicxml/tempo.py`,
`core/musicxml/meter.py` (map building), `core/musicxml/note_kinds.py` (cue/grace/unpitched),
`core/musicxml/duration_type.py`; fixtures under `tests/fixtures/musicxml/ttbb/`; tests below.
Changed: `core/musicxml/part_reader.py` (use the new modules, keep the cursor), `parser.py`
(tempo and meter reconciliation, tie issues), `models/pitch.py` (`absolute_semitones`),
`models/__init__.py`, docs.

## 10. Issue codes

Added (ERROR): `TIE_TYPE_INVALID`, `TIE_UNMATCHED_START`, `TIE_UNMATCHED_STOP`,
`TIE_PITCH_MISMATCH`, `TIE_AMBIGUOUS`, `TIED_WITHOUT_TIE`, `TIE_TIED_MISMATCH`, `TEMPO_INVALID`,
`TEMPO_CONFLICT`, `TEMPO_OFFSET_OUT_OF_MEASURE`, `TIME_SIGNATURE_CONFLICT`,
`UNSUPPORTED_GRACE_NOTE`, `UNSUPPORTED_UNPITCHED_NOTE`.
Added (WARNING): `TIE_WITHOUT_TIED`, `TEMPO_ZERO_UNRESOLVED`, `METRONOME_WITHOUT_SOUND`,
`CUE_NOTE_SKIPPED`, `DURATION_TYPE_MISMATCH`, `MEASURE_NUMBER_REPEATED`.
Removed: `NOTE_KIND_NOT_SUPPORTED_YET`.
Changed: the earlier idea of `TIED_WITHOUT_TIE` as a warning is now an ERROR (above).
Not in M3b2: `TEMPO_MISSING` (M4), `TIME_SIGNATURE_CHANGE_MID_MEASURE` stays as in M3b1.

## 11. Tests planned
- **Ties (pure helper):** simple pair; chain of three; across a barline; across a `divisions`
  change; across a rest (unmatched); unmatched start; unmatched stop; pitch mismatch; enharmonic
  match; microtonal exact match and mismatch; transposed parts; chord with two tied members paired
  correctly; chord where only one member is tied; unison ambiguity; source notes untouched
  (identity and tuple equality before and after); merged duration exact (thirds); first note's
  pitch and lyrics kept; no second attack.
- **`<tie>`/`<tied>`:** every row of the policy table; `continue` and `let-ring` ignored;
  invalid tie type.
- **Tempo:** one tempo at measure start; tempo mid-measure; two changes in one measure; decimal
  value exact; zero; invalid; offset zero, positive, fractional-quarter via `divisions`, sound-child
  offset overriding the direction's, direction offset with `sound` `yes`/`no`/absent, negative and
  out-of-measure offsets rejected; conflicting same-position tempos; same value deduplicated;
  tempo in only one part; `METRONOME_WITHOUT_SOUND`; no tempo leaves the map empty.
- **Meter:** first-measure meter; change at a later measure; identical declarations in two parts
  make one event; restatement makes none; part with no declaration inherits; conflicting parts
  error; map positions exact with a pickup.
- **Special notes:** cue advances and is omitted; cue chord does not advance; grace error and no
  advance; unpitched advances; location content (line, measure, beat) for each; line falls back to
  the part when voice is missing.
- **Duration/type:** consistent dotted, tuplet and double-dotted notes; mismatch warns and timing
  still follows `<duration>`; skipped cases.
- **Fixtures and oracle:** both TTBB fixtures (parse, four lines, no roles, no tempo vs reconciled
  tempo, meter map); every `u_*` and `t_*` fixture as agreement or documented divergence; e6 exact
  after merging; model isolation test still green.
- **Regression:** `test_clef_never_transposes.py` and all M3b1 tests unchanged.

## Approved decisions

1. `<tied>` without `<tie>` is the ERROR `TIED_WITHOUT_TIE`. `<tie>` is authoritative. The
   diagnostic must carry enough source information (line, measure, beat, the note's pitch and
   the `<tied>` type) for a future explicit UI repair such as "Notation contains a visual tie but
   no playback tie. Treat it as a sound tie?" No such repair happens during parsing.
   `<tie>` without `<tied>` stays the WARNING `TIE_WITHOUT_TIED`; contradictory types or counts
   are the ERROR `TIE_TIED_MISMATCH`.
2. Tempo offsets follow the MusicXML 4.0 specification (direction offset only with
   `sound="yes"`; a `<sound>`'s own offset applies), converted through the active `divisions`,
   never clamped. MuseScore ignoring offsets is a documented compatibility divergence. Permanent
   tests document **both** "specification behavior" and "observed MuseScore divergence" so the
   standards-correct implementation is not later "fixed" to match MuseScore.
3. Tie matching uses exact sounding pitch. C#4 to Db4 can form one performed note; both source
   notes and spellings are preserved, and the performed note uses the first source note's pitch
   and spelling. Microtones need exact equality.
4. `tempo="0"` is unresolved: a parse-time WARNING, no `TempoChange`, never 120 BPM.
5. Meter map: effective changes only. Tempo map: every explicit valid event is kept (even if
   equal to the previous value); identical events at the same global position across parts
   reconcile to one; conflicting values are `TEMPO_CONFLICT`.
6. `PerformanceNote` is an immutable derived model with start, duration, sounding pitch, lyric
   association and source notes (no mutable back-references; no MIDI, OpenUtau, FFmpeg or Qt).
7. `Pitch.absolute_semitones` is an exact `Fraction`. `Pitch.__eq__` stays spelled-pitch equality.
8. Two implementation commits: **M3b2a** and **M3b2b** (scopes below).
9. Duration/type is a consistency check only (WARNING, never changes timing; skipped when `type`
   is absent, for whole-measure rests and where the comparison is not meaningful).
10. Tie diagnostics have a documented, tested precedence (see "Tie diagnostic precedence").

### Tie diagnostic precedence

Applied deterministically in this order for every `tied_from_previous` note `n` at start `s`:
1. **`TIE_AMBIGUOUS`**: two or more open ties with the **same sounding pitch** end exactly at
   `s`. No guess is made; nothing is paired; `n` starts a new attack.
2. **Paired**: exactly one open tie of the same sounding pitch ends at `s`.
3. **`TIE_PITCH_MISMATCH`**: no same-pitch open tie, but at least one open tie ends exactly at
   `s` (the continuation is where a tie should land, with the wrong pitch). The message names
   both pitches.
4. **`TIE_UNMATCHED_STOP`**: no open tie ends at `s` at all. This is an unrelated stop and must not
   be reported as a pitch mismatch.

`TIE_UNMATCHED_START` is reported separately for an open tie that is never continued (it stops
being possible once a later event starts after its end, or at the end of the line), located at the
note that started it. A tie start that was already used to report a `TIE_PITCH_MISMATCH` is not
reported a second time as unmatched: the mismatch consumes it, so one underlying mistake gives one
diagnostic. Each stop and each start gets at most one tie diagnostic.

### M3b2a scope (ties and note semantics)
`PerformanceNote`; `Pitch.absolute_semitones`; `<tie>` and `<tied>` parsing and consistency
diagnostics; `merge_tied_notes` (simple, chains, across barlines, across `divisions`, enharmonic,
microtonal, ambiguous, unmatched, mismatched); cue/grace/unpitched handling; duration/type
checking; removal of `NOTE_KIND_NOT_SUPPORTED_YET`. No tempo or meter reconciliation.

### M3b2b scope (tempo, meter, TTBB)
Tempo extraction with exact decimals, offsets, `tempo="0"`, conflicts and reconciliation;
time-signature map and cross-part reconciliation (`TIME_SIGNATURE_CONFLICT`); the original TTBB
fixtures (no tempo, shared tempo, later tempo change); final MuseScore oracle comparisons.

## 12. Unresolved questions (superseded by the decisions above)

1. **`<tied>` without `<tie>`** as an ERROR (my proposal) versus a warning that follows the
   specification (re-attack). MuseScore ties them.
2. **Tempo `<offset>` follows the specification** (sound-child offset always; direction offset only
   with `sound="yes"`), which refines the earlier "apply `<offset>`". MuseScore differs (it applies a direction's
   offset whatever `sound` says and ignores a `<sound>`'s own offset), so a file that MuseScore
   plays one way we may place differently. This is a documented compatibility divergence.
3. **Tie matching by sounding pitch** (so enharmonic ties join), with the exact
   `Pitch.absolute_semitones` model addition.
4. **`tempo="0"`** treated as unresolved with a WARNING (spec: "ask the user").
5. **Meter map records changes only; tempo map keeps explicit events.** Acceptable asymmetry?
6. **New models:** `PerformanceNote` and `Pitch.absolute_semitones`. Acceptable additions to the M2
   model?
7. **Ties across voices or staves** are not supported (a tie must continue in the same voice line)
   and appear as unmatched.
8. **`MEASURE_NUMBER_REPEATED`** here, before repeat expansion; M3d may refine it.
9. **Commit shape:** one M3b2 commit, or split into (a) ties, special notes, duration/type and
   (b) tempo, meter, TTBB fixtures?
