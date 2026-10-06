# M3d plan: plain repeat expansion

Status: **plan, revised after review**. No M3d code has been written. The research fixtures
(`tests/fixtures/musicxml/repeats/`, 50 inputs with MuseScore 4.7.4 MIDI oracles) are in the working
tree and not yet committed. M3d covers `<repeat direction="forward|backward" times="n">` only.
Endings/voltas are M3e. D.C./D.S./segno/coda/fine stay unsupported (`UNSUPPORTED_JUMP`).

The local real score (San Francisco Bay Blues, 2 parts, 71 measures) contains **no repeats, endings or
jumps**, so M3d is for generality and safety, not for that score.

## 1. What MuseScore does (oracle) and where we deliberately differ

| Case | MuseScore 4.7.4 | M3d decision |
|---|---|---|
| `\|: A B :\| C` | A B A B C | Same. |
| `times` absent | 2 passes | Default 2 (the specification is silent on the default; every tool agrees). |
| `times="n"` | n **total** passes (3 gives three passes, 9 gives nine) | Same: `times` is the total number of passes. |
| `times` 0, 1, non-numeric | one pass | `0`, negative, non-integer, non-numeric: ERROR `REPEAT_TIMES_INVALID`. `1`: WARNING `REPEAT_TIMES_ONE`, one pass. |
| backward, no forward anywhere before | repeats from the score start | Same, no issue (the normal MusicXML reading). |
| second backward, no forward between | returns to the **score start** (`r02c`) but, after a forward-marked repeat, returns to the **earlier forward** (`s06`) | ERROR `REPEAT_START_AMBIGUOUS`: the conventional reading (return to the end of the previous repeat) differs from both. Only a backward whose nearest preceding repeat sign is a forward, or which is the first repeat sign of the score, is accepted. |
| nested `\|: A \|: B C :\| D :\| E` | does not nest: A B C B C D B C D E | ERROR `REPEAT_NESTED_UNSUPPORTED`. A forward while another is open is rejected even when only one backward follows (`s07`). |
| forward never closed | plays straight through | Same: plays through, one WARNING `REPEAT_FORWARD_UNUSED`; never blocks. |
| repeats in several parts | silently keeps **one** part's structure (the last) for all parts | Every part must carry the same structure; otherwise ERROR `REPEAT_STRUCTURE_CONFLICT`. A part with no marks while another has some counts as a conflict. |
| barline `location` | attaches the repeat to the measure **containing** the barline, whatever its `location` | Accept only forward at `left` and backward at `right`; anything else (including a missing `location` on a forward, which defaults to `right`) is ERROR `REPEAT_BARLINE_PLACEMENT`. The specification reading (a `right` forward starts one measure later) differs from MuseScore's, so we refuse rather than guess. |
| barline in the middle of a measure | moves it to the measure end | ERROR `REPEAT_MID_MEASURE`. |
| `after-jump="yes"` | ignored | ERROR `REPEAT_AFTER_JUMP_UNSUPPORTED` (it only means something with D.C./D.S.). |
| pickup measure | replayed verbatim | Same. No special case. The final measure is *not* shortened or lengthened by us. |
| tie leaving a repeat | held only on the last pass | Same (see §5). |
| tie around a jump (`r07b`) | never merged | Same. |
| tied-to note at a repeat start, later passes | **no attack** (artefact) | The note is a **new attack** with WARNING `TIE_BROKEN_BY_REPEAT`. A sung note is never silently dropped. |
| nested/unsupported `times` etc. | see above | Never emulate the inner-replaces-outer behaviour. |
| tempo at a landing | re-asserts the tempo in force at the **source position** of the landing measure (`s01`: 120, not 60) | **Differs**: explicit events replay per visit and effective tempo carries across the jump (section 6); a test pins the divergence. |
| meter at a landing | that measure's own meter | Explicit events replay per visit; every measure keeps its parsed length (section 6). |

## 2. Where expansion operates (the key decision)

Considered: (1) expand source measures before line construction, (2) expand parsed source events,
(3) a derived performance-order representation.

**Chosen: (3)**, with the source `Song` left literal and untouched. Reasons from the research:

* Ties cannot be resolved in source order (`r07`, `r07b`, `r07c`): whether a tie holds depends on
  which measure *performed* next.
* Tempo and meter are properties of the source position, but the maps are consumed in performed time.
* Lyrics words and melismas can be cut by a jump.
* The literal `Song` must stay what the file says (debuggable, M4 validates it, UI shows it).

Pipeline:

```
parse (M3a-c)      -> Song (literal; unchanged contract)  +  structural issues
plan_performance   -> PerformancePlan (which source measures are played, in what order)
expand             -> PerformedSong (derived copies on the performed timeline)
merge_tied_notes   -> PerformanceNote lines (existing function, unchanged)
analyze_*_lyrics   -> LineLyricAnalysis (M3c2; one small addition, see §7)
M4 validation, M6 export read the performed objects
```

For a score without repeats the plan is the identity and the expansion returns equal events, so all
current behaviour is preserved.

## 3. Model (revised after review: no `visit` on `Note` or `ValidationIssue`)

A source note has no repeat visit; one source note yields several performed occurrences. Visits and
boundaries therefore live only in derived performance objects. `Note` and `ValidationIssue` are
unchanged.

Source facts on `Song`, read literally (like tempo and meter):

* `MeasureSpan(index, number, raw_number, start, length, implicit)`: `index` is the stable 0-based
  source measure index and **the identity**; `number` is the display number (a non-negative int, with
  the existing `MEASURE_NUMBER_NONNUMERIC` fallback) and `raw_number` the text as written. Display
  numbers may repeat, be `0` or be non-numeric and are never used as identity. `length` is the actual
  parsed length (a pickup keeps its true length), never a nominal meter length.
* `RepeatMark(kind: FORWARD|BACKWARD, measure_index, times: int | None)`; `Song.repeat_marks` is the
  structure all parts agreed on. `times` is `None` when absent.

Derived, in `models/performed.py`:

* `TransitionKind`: `START` (first measure played), `SEQUENTIAL` (ordinary source adjacency),
  `REPEAT_JUMP` (backward repeat taken, landing at the start of the span), `REPEAT_EXIT` (backward
  repeat finished, continuing to the next source measure). M3e adds `ENDING_SKIP` without touching the
  others.
* `PlayedMeasure(source_index, number, visit, performed_index, performed_start, length, arrival)`:
  `visit` counts how many times *that source measure* has now been played (1, 2, 3 ...); `arrival` is
  the `TransitionKind` that led here.
* `PerformancePlan(played)`: `segments`, `jump_positions` (performed positions whose arrival is
  `REPEAT_JUMP`), `is_identity`, `locate(position)`.
* `NoteOccurrence(part_id, source_event_index, measure_index, visit, performed_start)`: the provenance
  of one expanded note.
* `PerformedLine(part: Part, occurrences: tuple[NoteOccurrence, ...])`: `part.events` are ordinary
  shifted `Note` copies in chronological order (so tie merging and lyric analysis work unchanged) and
  `occurrences[i]` describes `part.events[i]`. `occurrence_of(note)` recovers provenance from a copy,
  including from a `PerformanceNote.source` member.
* `PerformedSong(song, plan, lines, tempo_events, meter_events, issues)`: `song` is referenced, never
  copied or mutated.
* `PerformanceLocation(measure_index, number, visit, performed_position, performed_measure_index)` and
  `LocatedIssue(issue, location)`: optional structured provenance for performed diagnostics (used by
  M3d2 for `TIE_BROKEN_BY_REPEAT` and lyric findings). `ValidationIssue` itself is not changed. M3e can
  add the ending number to `PerformanceLocation`.

Positions are exact `Fraction` quarter notes (global performed time). No ticks.

## 4. Planner rules (`core/timeline/repeats.py`, pure)

Per part the barline reader produces marks; marks are reconciled structurally (4.2) and only then
planned.

### 4.1 Reading a barline (MusicXML semantics, not MuseScore's)

* `<repeat direction>` must be `forward` or `backward` (`REPEAT_DIRECTION_INVALID`).
* A forward must sit at `location="left"` and a backward at `location="right"`. A forward at the
  default `right`, a backward at `left`, or any other combination is outside what M3d interprets:
  ERROR `REPEAT_BARLINE_PLACEMENT`. (By the specification a left backward ends the repeat one measure
  earlier and a right forward starts it one measure later; MuseScore attaches both to the containing
  measure. We refuse rather than guess.) `location="middle"`, or a repeat barline that does not sit
  before all notes (left) or after all notes (right), is `REPEAT_MID_MEASURE`.
* `times` (spec: `nonNegativeInteger`, no default, backward repeats only): absent means 2 total passes
  (our documented choice, matching MuseScore). `0`, negative, non-integer and non-numeric are ERROR
  `REPEAT_TIMES_INVALID`; never coerced. `1` is valid, one pass, WARNING `REPEAT_TIMES_ONE`. Above 16:
  ERROR `REPEAT_TIMES_EXCESSIVE`. `times` on a forward is ignored with WARNING `REPEAT_TIMES_IGNORED`.
* `after-jump="yes"`: ERROR `REPEAT_AFTER_JUMP_UNSUPPORTED`. `winged` is cosmetic and ignored.
* Any `<ending>`: ERROR `ENDING_NOT_SUPPORTED_YET` and no partial interpretation; D.C./D.S./segno/
  coda/fine keep `UNSUPPORTED_JUMP`.

### 4.2 Cross-part structure

Structure of a part = the ordered list of `(kind, measure_index, resolved times)`. Parts are equal when
the lists are equal (a missing `times` equals an explicit 2). Equal: one shared plan. Different in any
way (including one part having none): ERROR `REPEAT_STRUCTURE_CONFLICT`, naming the first differing
mark; the plan is then the identity. Parts are never expanded onto incompatible timelines.

### 4.3 Planning

Walk the marks with one optional open start:

* forward with a forward already open: ERROR `REPEAT_NESTED_UNSUPPORTED` (it is either nesting or
  authoring debris, and we do not choose).
* backward with an open forward: the span is played `times` times.
* backward with none open: if no repeat sign precedes it, repeat from the score beginning (the normal
  MusicXML reading; no issue at all). If an earlier backward already closed a repeat, the start is
  ambiguous (`r02c`: MuseScore returns to the score start; `s06`: to the earlier forward): ERROR
  `REPEAT_START_AMBIGUOUS`, documented as "a backward repeat that follows another repeat without its
  own forward repeat".
* a forward never consumed: play through; one WARNING `REPEAT_FORWARD_UNUSED` per unused forward
  (MusicXML permits it and it is a likely authoring leftover, so it is reported but never blocks).
* consecutive and one-measure repeats are plain sequences.
* limit 10 000 performed measures: ERROR `REPEAT_EXPANSION_TOO_LARGE`.

An error leaves the plan as the identity so the output stays defined while the ERROR blocks
generation.

## 5. Ties across jumps (M3d2)

Expansion happens **before** tie merging, and the source-order tie merge is never duplicated. The
expander knows each transition's kind. Rule: a tie survives only where the performed neighbour is the
written neighbour, i.e. across `SEQUENTIAL` and `REPEAT_EXIT` transitions, never across `REPEAT_JUMP`.

* A tie start on the last note before a jump is copied with `tied_to_next=False`; the tied-to note at
  the landing is copied with `tied_from_previous=False`. Each case is one WARNING
  `TIE_BROKEN_BY_REPEAT` (a `LocatedIssue` with part, measure index, number and visit). The note at the
  landing is a **new attack**, never dropped.
* Chains that intersect a boundary are cut at the boundary only; the remaining notes keep their ties
  and merge normally.
* `merge_tied_notes` is unchanged and sees contiguous performed notes with the right flags;
  `PerformanceNote.source` are the expanded copies and `PerformedLine.occurrence_of` recovers their
  source identity and visit.

## 6. Tempo and meter (M3d2)

Explicit events and effective state are kept apart.

* `PerformedSong.tempo_events`: each **explicit** source tempo event inside a visited measure occurs
  again at its shifted position on every visit. Nothing is synthesised for carried state.
* Effective tempo at any performed position is a query over the explicit events in performed order
  (`effective_tempo_at(position)`): it carries across a jump, so a tempo set before a repeat holds
  until replaced, and a tempo changed on the first traversal is still in force at the landing unless
  the repeated region re-declares it. MuseScore instead re-asserts the landing measure's source tempo
  (`s01`); we treat that as an oracle divergence, pinned by a test, because re-asserting a tempo the
  score never wrote would invent a declaration.
* Meter likewise: explicit time-signature events replay with each visit; effective meter is a query.
  A measure's own length always comes from the parsed `MeasureSpan`, so a meter change inside a
  repeated region keeps correct measure lengths on every pass. `Song.time_signatures` is not mutated.

## 7. Lyrics after expansion (M3d2)

Analysis runs on the expanded, merged line. `analyze_line(..., jumps=frozenset())` receives
`plan.jump_positions` (derived from `arrival`, never from measure numbers). At a jump all lyric state
ends: an inferred extender ends (counting toward `LYRIC_MELISMA_INTERRUPTED` if a lyric-less attack
follows), an open typed extension is `LYRIC_MELISMA_UNCLOSED`, an open word is `LYRIC_WORD_UNCLOSED`,
and a landing `MIDDLE`/`END` is `LYRIC_WORD_UNOPENED`. Each visit starts a fresh traversal.

## 8. Source-measure provenance

Identity is the source measure index, never the display number. Source `Note`s are untouched.
`PerformancePlan.locate(position)` and `PerformedLine.occurrence_of(note)` recover index, display
number, visit, performed position and the global performed measure index. `MEASURE_NUMBER_REPEATED`
stays informational at most.

## 9. Issue codes

ERROR: `REPEAT_NESTED_UNSUPPORTED`, `REPEAT_START_AMBIGUOUS`, `REPEAT_STRUCTURE_CONFLICT`,
`REPEAT_BARLINE_PLACEMENT`, `REPEAT_MID_MEASURE`, `REPEAT_DIRECTION_INVALID`, `REPEAT_TIMES_INVALID`,
`REPEAT_TIMES_EXCESSIVE`, `REPEAT_EXPANSION_TOO_LARGE`, `REPEAT_AFTER_JUMP_UNSUPPORTED`,
`ENDING_NOT_SUPPORTED_YET` (temporary, M3e). Retained: `UNSUPPORTED_JUMP`.
WARNING: `REPEAT_FORWARD_UNUSED`, `REPEAT_TIMES_ONE`, `REPEAT_TIMES_IGNORED`, `TIE_BROKEN_BY_REPEAT`.
Removed: `REPEAT_NOT_SUPPORTED_YET`.

## 9b. Implementation split

* **M3d1**: repeat marks and measure table, cross-part reconciliation, planner (`times`, missing
  forward, nesting, ambiguity), transitions and visits, `PerformedLine` with shifted notes and
  `NoteOccurrence`, `PerformedSong` with the plan; no tie/tempo/meter/lyric integration beyond proving
  performed order and positions.
* **M3d2**: tie breaking with `LocatedIssue`, performed tempo and meter events/queries, lyric jump
  boundaries, pickup timing tests across the pipeline, the full oracle comparison.

## 10. Tests

* Oracle: every fixture in `repeats/` parsed and expanded; for the cases we accept, the played
  measure order and the performed onsets equal the MuseScore oracle (A B A B C ... and the tick
  positions at 480 PPQ), including tempo and meter events. For the cases we deliberately refuse or
  differ on, a permanent divergence test names the MuseScore behaviour and our result.
* Planner unit tests (hand-built measure tables): every §4 rule, `times` 2/3/16/17, one-measure and
  consecutive repeats, pickups, the 10 000-measure limit.
* Expansion: global positions exact, provenance (`NoteOccurrence`: part, measure index, visit,
  position) correct, display numbers never used as identity, source `Song` and
  `Note`s deep-equal before and after (immutability), identity for scores without repeats (the whole
  existing suite is the regression test).
* Ties: `r07`, `r07b`, `r07c`, `r07d`, plus a tie inside a repeat and across a contiguous boundary.
* Tempo/meter maps per pass (`r08`, `r09`, `s01`-`s04`).
* Lyrics: word cut by a jump, extender cut by a jump, typed extension cut by a jump, 23-note melisma
  inside a repeat (unchanged `longest_melisma`).
* Parser: each placement/times/mid-measure/after-jump/ending case; cross-part agreement and
  disagreement (`r06`, `s09`, `s10`).
* Existing tests that assert `REPEAT_NOT_SUPPORTED_YET` are updated to the new behaviour.

## 11. Files

New: `models/performed.py`, `core/timeline/repeats.py` (planner), `core/timeline/expand.py`
(expander), `core/musicxml/repeat_marks.py` (barline reader), tests under
`tests/unit/core/timeline/` and `tests/unit/core/musicxml/`. Changed: `models/song.py` (measures and
repeat marks), `core/musicxml/repeats.py` (shrinks to ending/jump detection), `part_reader.py` (measure table, marks), `parser.py` (agreement, expansion call, tie
reports), `core/lyrics/analysis.py` and `melisma.py`/`words.py` (jump reset),
`docs/musicxml-support.md`, `tests/fixtures/musicxml/README.md`.

## 12. Review outcome

All seven decisions were settled in review; the provenance model in section 3 replaces the
`visit` fields originally proposed. The comparison table in section 1 is the research record; where
it conflicts with sections 3-9, sections 3-9 win.

## 13. M3d1 status notes

* `times` is a non-negative integer in MusicXML with no default; **absent means 2 total passes is our own performance policy**, not something the specification states.
* Temporary: until M3d2, tie diagnostics still run in source order, so a score containing repeat jumps has not yet received final performed-order tie validation. M3d2 replaces them; the two must never be active together.
* An identity plan caused by a failed repeat structure is distinguishable from a repeat-free score only through the issues (`ParseResult.issues` carries the ERROR); there is deliberately no separate validity flag.
