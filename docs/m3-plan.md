# M3 plan: MusicXML parser

Status: **approved with the decisions listed at the end. No parser code has been written.**
Research basis and findings: [musicxml-support.md](musicxml-support.md).

## Goal

Read a MuseScore-exported MusicXML file into the validated M2 `Song` model, expanding repeats
deterministically, and report everything it cannot represent. The parser never guesses and
never modifies pitches or lyrics. M3 does **not** include MIDI export, FFmpeg, OpenUtau, the
GUI, or the musical-content validation rules (four voices, monophony, lyric coverage), which
are M4.

## Key design decisions (from the research)

1. **`written_pitch = <pitch>` exactly as in the file.** `PitchTransform` comes only from
   `<transpose>`. `<clef-octave-change>` never transforms pitch, because MuseScore 4.7.4
   ignores it for pitch, and applying both would double-transpose a part.
2. **Time is `Fraction(duration, divisions)`**, never derived from note type or tuplet markup.
3. **One model `Part` per voice line**: `(source part id, staff, voice)`, id like `P1/s1/v1`.
   MuseScore numbers voices across staves (1, 2, then 5, 6), so the staff must be part of the
   identity. Roles are assigned to line ids explicitly.
4. **The parser is literal; interpretation is separate.** The parser reports what the file says
   (including that a melisma note has no lyric element after it). Analyses such as "this
   lyric-less note continues a melisma" are separate, testable functions.
5. **Parser problems become `ValidationIssue`s, not exceptions.** Exceptions
   (`ScoreReadError`) are only for files that cannot be read at all.
6. **A MuseScore oracle backs the tests.** Expected sounding pitches and onsets (including
   expanded repeats) come from MuseScore's own MIDI export, stored as small JSON files.
7. **Clefs are a separate, informational notation model**, not a `Part` field: immutable
   `ClefChange` records (part id, staff, sign, line, octave change, source measure, exact
   timeline position) carried on the `Song`. They never enter pitch math; a test proves
   `<clef-octave-change>` leaves `PitchTransform` and the sounding pitch unchanged.
8. **Missing tempo is a validation condition, not a parse error.** The parser leaves
   `tempo_map` empty; M4 emits generation-blocking `TEMPO_MISSING`; the user supplies a tempo
   through the job request (a `JobRequest` field added when M4/M7 need it). Never a hidden
   120 bpm.
9. **Time and position are never re-interpreted.** A pickup keeps source measure 0, its
   exact local offset and exact global position. No count-in convention is encoded.
10. **Cue notes advance the cursor but are not emitted** (the spec gives `duration` to every
    non-chord `<note>`); a WARNING records line, measure and beat. Grace notes are an ERROR.
11. **Real-world layout is two parts with two voices each** (tenor/lead and baritone/bass
    sharing staves), with no tempo and implied staff 1. The design handles this as the
    normal case without being tailored to one file.

## Module layout (`src/barbershop_tracks/core/musicxml/`)

| Module | Responsibility |
|---|---|
| `source.py` | Open a path: plain XML or `.mxl`. Safe ZIP reading (size and ratio limits, no extraction, first `<rootfile>`, no `media-type` required). |
| `xml.py` | Safe parsing with defusedxml: entities and external resources forbidden, DTD **allowed** (MuseScore emits one). Helpers for text, int and `Fraction` parsing. |
| `attributes.py` | Per-part running state: divisions, time signature, clef (informational), transposition per staff. |
| `measures.py` | Walk measures with a cursor: `backup`, `forward`, `chord`, pickups, measure duration check. Emits raw events with source measure, staff, voice, start (in the measure). |
| `notes.py` | `<note>` to pitch, rest, ties, and flags for unsupported constructs. |
| `lyrics.py` | `<lyric>` to `Lyric`: syllabic, verse, extend, elision, multiple text elements. |
| `tempo.py` | `<sound tempo>` to `TempoChange` at the cursor position. |
| `repeats.py` | Barline repeats and endings to a **measure order** (list of source measure indices), plus issues. Pure, no XML. |
| `lines.py` | Split a part into voice lines and build line ids. |
| `parser.py` | Orchestrate: `parse_musicxml(path) -> ParseResult(song, issues)`. |

Pure helpers live beside it, tested without XML:

| Module | Responsibility |
|---|---|
| `core/timeline/ties.py` | `merge_tied_notes(events)` for synthesis; reports unmatched or pitch-mismatched ties. |
| `core/lyrics/analysis.py` | Classify each note as syllable, melisma continuation, tie continuation, or missing lyric. Used by M4 validation and the M6 exporter. |

`ParseResult` is a small frozen dataclass: `song: Song | None` and `issues: ValidationResult`.
`song` is `None` only when the structure cannot be recovered (for example, not partwise).
Anything else yields a `Song` plus ERRORs, and the pipeline refuses to generate when
`issues.has_errors`.

## Data flow

```
path -> source (xml or mxl) -> safe XML tree
     -> per part: attributes + measures + notes + lyrics + tempo   (source order, divisions)
     -> repeats.py: measure order for every part, compare across parts
     -> instantiate measures in performance order (Fraction start positions)
     -> split into voice lines -> Parts (ties preserved as flags)
     -> Song + issues
```

Notes in the `Song` are on the **performance** timeline. A repeated measure appears twice
with the same source `measure` number and different `start`.

## Issue codes (initial list)

Errors: `SCORE_NOT_PARTWISE`, `MXL_INVALID`, `DIVISIONS_MISSING`, `TIME_SIGNATURE_MISSING`,
`MEASURE_DURATION_MISMATCH`, `BACKUP_BEFORE_MEASURE_START`, `UNSUPPORTED_GRACE_NOTE`,
`UNSUPPORTED_UNPITCHED_NOTE`, `UNSUPPORTED_JUMP`, `REPEAT_UNRESOLVED`, `REPEAT_NESTED`,
`REPEAT_MISMATCH_ACROSS_PARTS`, `ENDING_INVALID`, `TIE_UNMATCHED`, `TIE_PITCH_MISMATCH`,
`TRANSPOSE_NOT_SPELLABLE`, `MIDI_TICKS_NOT_EXACT` (reserved for M6).

Warnings: `CUE_NOTE_SKIPPED`, `MEASURE_NUMBER_NONNUMERIC`, `MEASURE_NUMBER_REPEATED`,
`TIED_WITHOUT_TIE`, `LYRIC_MULTIPLE_TEXT`, `LYRIC_MULTIPLE_VERSES`,
`DURATION_TYPE_MISMATCH`, `METRONOME_WITHOUT_SOUND`.

M3b2a replaces `NOTE_KIND_NOT_SUPPORTED_YET` with `CUE_NOTE_SKIPPED` (WARNING),
`UNSUPPORTED_GRACE_NOTE` and `UNSUPPORTED_UNPITCHED_NOTE` (ERRORs), and adds the tie codes,
`DURATION_TYPE_MISMATCH` (see musicxml-support.md and m3b2-plan.md); `TIED_WITHOUT_TIE` is an
ERROR, not the warning listed above.

M3b1 also defines `TIME_SIGNATURE_CHANGE_MID_MEASURE` and `TRANSPOSE_DOUBLE_UNSUPPORTED` (both
ERRORs; see musicxml-support.md), and has no `TRANSPOSE_DOUBLE_IGNORED` code.

`TEMPO_MISSING` (ERROR, generation-blocking, user-resolvable) is emitted by M4 validation,
not by the parser. Likewise simultaneous pitched notes in one voice line
(`LINE_NOT_MONOPHONIC`) are reported by validation; the parser keeps every note.

## Sub-milestones

Each ends with pytest, ruff, mypy and the audio guard green, one commit, and green CI.

| Step | Scope | Verified by |
|---|---|---|
| M3a | Typed errors, `source.py`, `xml.py`: plain XML and `.mxl`, MuseScore DOCTYPE accepted, entity/external-resource rejection, archive safety | Fixtures including the `.mxl`; crafted malicious XML and ZIPs (no parsing of music yet) |
| M3b | `ClefChange` notation model; `attributes`, `measures`, `notes`, `lines`, `parser` (no lyrics, no repeats): divisions, backup/forward, chords, voices and staves, pickup, tuplets, ties, cue/grace, transpose, tempo | Oracle comparison on `e1`-`e7` (pitch via `PitchTransform`, onsets at 480 PPQ after tie merge) |
| M3c | `lyrics.py`, `lyrics/analysis.py` | Fixture `e10`; verse, syllabic, extend, elision cases |
| M3d | `repeats.py` phase 1: forward/backward, `times` | Oracle `e8` (ordinary repeat, twice) and `e8b` (`times="3"`, three performances); mismatch-across-parts cases; jumps rejected |
| M3e | `repeats.py` phase 2: endings (`"1"`, `"1, 2"`, `"3"`) | Oracle `e9`, `e12` |
| M3f | Finalize `docs/musicxml-support.md`; `tempo.py` once question 3 is decided | Docs review |

Order of M3d/M3c can swap. M3e is separate on purpose, as you asked repeats to be incremental.

## Test strategy

- **Oracle tests:** for each fixture, build the `Song`, convert `Fraction` positions to ticks
  *inside the test helper* (the model has no ticks), apply `merge_tied_notes`, and compare to
  `oracle/*.json` from MuseScore. A tick that is not an exact integer fails the test.
- **Round-trip fixtures:** both the hand-authored input and MuseScore's re-export must parse
  to the same notes, which guards against parsing quirks specific to MuseScore's output.
- **Negative tests:** one small crafted file per ERROR and WARNING code.
- **Security tests:** billion-laughs entity file, external entity, zip bomb ratio, path
  traversal member name, missing container, empty archive.
- **No Qt, FFmpeg, OpenUtau or network** in any test, as before.

## Risks

- Evidence comes from round-tripped hand-written scores plus one real two-part TTBB export
  (not committed). It is a data point, not a guarantee of every MuseScore template.
- The reference is silent on `times` counting and on endings playback; I rely on MuseScore's
  behavior and the conventional reading. The oracle makes this testable and visible.
- Jumps (D.C., D.S.) are untested against a real MuseScore-authored score and are rejected.
- `divisions` may be a decimal in the schema (the reference page I read says integer). The
  parser accepts either via exact decimal parsing.

## Approved decisions

1. A tiny original TTBB export goes in `tests/fixtures/musicxml/real/` (still to be supplied;
   only original, publicly committable material). It is evidence, not a reason to change the
   architecture.
2. Clefs: an informational notation model (`ClefChange`), never in pitch math; tested.
3. Missing tempo: parser preserves absence; validation emits `TEMPO_MISSING`; generation is
   blocked until the user supplies a tempo. No silent default.
4. Melismas: the parser is literal; a separate analysis stage interprets them later.
5. Pickups: no right-alignment. Source measure, exact local offset and exact global position
   are preserved.
6. `times` = total performances, verified against MuseScore, with fixtures for twice and
   three times. Not generalized to jumps, which stay unsupported and generation-blocking.
7. Cue notes: skipped with a located WARNING (cursor still advances per the duration rule).
   Grace notes: ERROR.
8. Line ids `P1/s1/v1`; no assumptions about voice numbering; simultaneous pitched notes in one
   voice are an ERROR, never flattened.
9. XML: MuseScore DOCTYPE allowed only as needed; entities and external resources forbidden;
   security tests required.
10. `.mxl`: supported in M3 via `container.xml`, with archive-safety checks and no
    extraction to disk.
11. Research documentation and original research fixtures are committed before any parser
    code.
