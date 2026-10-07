# M3e plan: endings (voltas)

Status: **research and plan for review**. No M3e code has been written. The research fixtures
(`tests/fixtures/musicxml/endings/`, 38 synthetic inputs with MuseScore 4.7.4 MIDI oracles) are in
the working tree and not yet committed. M3e extends the M3d `PerformancePlan` / `PlayedMeasure` /
transition model; it does not replace the repeat engine. D.C./D.S./segno/coda/fine stay unsupported
(`UNSUPPORTED_JUMP`).

The local real score has no repeats, endings or jumps; M3e is for generality and safety.

## 1. What MusicXML 4.0 says (the authority)

* `<ending>` is an optional child of `<barline>` (children order: ... `ending`, then `repeat`).
* `number` (`ending-number`) "indicates which times the ending is played, similar to the time-only
  attribute". Pattern `([ ]*)|([1-9][0-9]*(, ?[1-9][0-9]*)*)`: a comma-separated list of positive
  integers without leading zeros, **or** zero or more spaces (software that detected an ending but not
  its number). **Ranges (`1-2`) and leading zeros are not valid.** The number may also say whether an
  ending plays during a larger D.S./D.C. repeat (unsupported here).
* `type`: `start` is "associated with the left barline of the first measure in an ending"; `stop` is
  an ending that "concludes with a downward jog" (typically a first ending); `discontinue` has no jog
  (typically a last ending). Both `stop` and `discontinue` end the ending span at the right barline of
  its last measure. The element text is display text only (MuseScore writes the numbers there).
* Barline `location="left"` should be the first element of the measure; `right` (the default) the
  last. The specification does not say which of the two an ending marker sits on beyond the `start`
  wording above.
* `repeat times` "is only used with backward repeats that are not part of an ending". So with
  endings the pass count comes from the ending numbers, not from `times`.

## 2. What MuseScore does (oracle, not authority)

| Case (fixture) | MuseScore 4.7.4 | M3e decision |
|---|---|---|
| Standard `[1 C :\| [2 D` (`v01`, `v01b`, `v10`) | A B C A B D E; `stop` and `discontinue` behave the same | Same. The close type does not change playback. |
| Multi-measure endings (`v02`, `v03`) | Correct | Same. |
| `1, 2` then `3` (`v04`), three endings (`v05`) | n passes from the endings | Same; the endings define the passes. |
| `times="3"` with endings 1, 2 only (`v06`) | Two passes (`times` ignored) | Same; `times` that contradicts the endings is ERROR `REPEAT_TIMES_ENDINGS_CONFLICT` (v06 would be rejected). |
| Endings with no backward repeat (`v07`, `v08`) | Plays A B C and **drops the rest of the score** | ERROR `ENDING_WITHOUT_REPEAT`. |
| Missing / `x` / `0` / range `1-2` / `01` / spaces number (`v09*`) | Marks ignored (or `01` read as 1) | ERROR: `ENDING_NUMBER_INVALID` (missing, non-matching, range, leading zero) or `ENDING_NUMBER_UNSPECIFIED` (spaces). Never repaired. |
| Endings numbered 3 and 2 (`v09g`) | Plays A B and stops | ERROR `ENDING_PASS_MISSING`/`ENDING_PASS_DUPLICATE`. |
| `start` without `stop` (`v11`), `stop` without `start` (`v12`) | Tolerated / ignored | ERROR `ENDING_UNCLOSED`, `ENDING_STOP_WITHOUT_START`. |
| Only a second ending (`v13`) | A B A B C D | ERROR `ENDING_PASS_MISSING` (pass 1 has no ending, and the repeat is not part of one). |
| Ending at the end of the score; two consecutive volta groups (`v14`, `v15`) | Correct | Same. |
| `start` on the right barline of the previous measure (`v16`) | Attached to the **containing** measure | ERROR `ENDING_BARLINE_PLACEMENT` (we refuse; same reasoning as repeat placement). |
| Ending with a bare backward repeat (`v18`, `v19`) | Repeats from the score start | Same as M3d: allowed when it is the first repeat sign. |
| Several parts (`v20`, `v20b`) | One part's structure applied to all | Parts must agree: `REPEAT_STRUCTURE_CONFLICT` otherwise. |
| Ties (`w01`-`w05`) | Tie never crosses a skip/jump; a tie into a skipped-to ending drops the attack (`w02`) | Cut (`TIE_BROKEN_BY_REPEAT` / `TIE_BROKEN_BY_ENDING`); the destination is a new attack, never dropped. |
| Tempo / meter in endings (`x01`, `x02`) | Replayed when the measure plays | Same as M3d (explicit events replay per visit). |
| Pickups (`y01`, `y02`) | Replayed verbatim | Same. |

Because MuseScore silently loses music in several of these cases, none of its quirks are emulated.

## 3. Model: marks, spans, groups (revised after review)

Three layers, each derived from the previous one, and nothing is repaired on the way:

1. **`EndingMark`** (reader level, literal): one `<ending>` element exactly as found: `kind`
   (`start`, `stop`, `discontinue`), the source measure index, the barline `location`, and the raw
   `number` text. A mark that cannot be read (bad number, bad type, bad placement, middle of a measure)
   is an explicit ERROR and is never turned into a span.
2. **`EndingSpan`** (source fact, on `Song.ending_spans`): a validated pairing of a `start` mark with the
   `stop`/`discontinue` mark that closes it: `start_index`, `end_index` (source measure indices, the
   identity), `numbers: tuple[int, ...]` (the pass set, sorted), `closing: EndingClose`
   (`STOP` | `DISCONTINUE`, preserved even though playback treats them alike), and `raw_number` (the
   text as written). The marker provenance is the two measure indices. Unmatched `start`, unmatched
   `stop`/`discontinue`, overlapping spans and a closing number that differs from the opening one are
   ERRORs, not spans. Performed pass numbers never appear here.
3. **`VoltaGroup`** (derived in the planner, `core/timeline/volta.py`): the structural relationship of
   a repeat and its endings, validated from the spans and the repeat marks, **not** found by scanning for
   adjacent ending measures. A group has:
   * `start_index`: the repeat start (the open forward repeat, or the score beginning when no repeat
     sign precedes, as in M3d);
   * the **body**: `start_index` .. the measure before the first ending;
   * `endings`: the spans in source order, which must tile the measures from the end of the body to the
     end of the group without gaps or other material between them;
   * `passes` (`N`) and the **pass-to-ending mapping** (`pass p -> ending`);
   * the **repeat-back marks**: the backward repeat on the closing barline of every ending except the
     last, and nowhere else;
   * the **exit**: the measure after the last ending.

Group validation (each rule is its own diagnostic):

* the ending numbers (positive integers only; `0`, negatives, leading zeros, ranges, spaces, missing
  or malformed tokens are `ENDING_NUMBER_INVALID`/`ENDING_NUMBER_UNSPECIFIED`) must partition
  `1..N` exactly: a pass claimed twice is `ENDING_PASS_DUPLICATE`, a pass nobody claims is
  `ENDING_PASS_MISSING`. Nothing is renumbered. `N` is at most 16;
* a comma list is valid; ending order does not have to be numeric ({2} may precede {1}), but the
  traversal must be deterministic: the **last ending in source order must be exactly `{N}`** (it is the
  exit and has no backward repeat), and every other ending ends with a backward repeat that jumps back to
  `start_index`. A non-last ending without one, or a last ending with one, makes the route ambiguous:
  `ENDING_WITHOUT_REPEAT` / `ENDING_STRUCTURE_UNSUPPORTED`;
* a lone ending that carries its own backward repeat (`v17`) is `ENDING_STRUCTURE_UNSUPPORTED`; a lone
  ending with no backward repeat is `ENDING_WITHOUT_REPEAT`. No second ending is implied and no plain
  repeat is applied;
* a forward repeat inside the body, other repeat structure that overlaps the group, or a group with
  no resolvable start are the M3d errors (`REPEAT_NESTED_UNSUPPORTED`, `REPEAT_START_AMBIGUOUS`);
* the pass count is **derived from the endings only**. A backward repeat of the group that carries
  `times` must equal `N`; otherwise ERROR `REPEAT_TIMES_ENDINGS_CONFLICT` (neither value is chosen).
  MuseScore itself writes `times="3"` on the repeat of a three-pass group, which is consistent.

Reading rules (per barline): `start` only at the left barline of the first measure of an ending,
`stop`/`discontinue` only at the right barline of its last measure (`ENDING_BARLINE_PLACEMENT`);
`middle` or an ending after the notes / before the end of the measure is `ENDING_MID_MEASURE`;
`type` outside the three values is `ENDING_TYPE_INVALID`; `print-object` and the element text are
ignored. A `start` while a span is open is `ENDING_OVERLAP`; a `start` never closed is
`ENDING_UNCLOSED`; a closing mark with no open span is `ENDING_STOP_WITHOUT_START`; a closing number
that differs from the opening one is `ENDING_NUMBER_MISMATCH`.

Safety (the M3d principle): if any ending mark or group cannot be read or validated, the whole
repeat/ending structure is left unexpanded (identity plan), the ERROR stays reachable through the
result, and no other repeat mark is partially executed. The 10 000 performed-measure cap applies after
endings are added and is an ERROR, never a truncation.

Cross-part: the structural signature of a part is its repeat marks **plus** its ending spans
(`start_index`, `end_index`, `numbers`; the closing kind is presentation and is not compared, the
spans' pass assignments are). Differences give `REPEAT_STRUCTURE_CONFLICT`; no part is authoritative.

## 4. Derived model (additive)

In `models/performed.py`:

* `TransitionKind.ENDING_SKIP`: the performed transition skipped source material because the pass does
  not select an ending: arrival at the first measure of an ending that is not the one written directly
  after the body. `SEQUENTIAL` (including entering the first ending in source order), `REPEAT_JUMP` and
  `REPEAT_EXIT` keep their M3d meanings; leaving the last ending is `REPEAT_EXIT` and preserves source
  adjacency.
* `PlayedMeasure.repeat_pass: int | None`: the 1-based pass through the containing repeat or volta
  group; `None` outside any repeat context. It is **not** `visit` (how many times that written measure
  has been played). `PlayedMeasure.endings: tuple[int, ...]`: the pass set of the ending being played,
  empty outside an ending.
* `PerformancePlan.discontinuity_positions`: positions reached by any arrival that is not written
  adjacency (`REPEAT_JUMP`, `ENDING_SKIP`). `jump_positions` keeps its M3d meaning. The transition kind
  stays on every measure; the position set is a convenience, not a replacement. Downstream asks "did the
  traversal cross a discontinuity?", not "was this a backward repeat?".
* `PerformanceLocation` gains `repeat_pass` and `endings`, beside the source measure identity, display
  number, visit and performed position, so a UI can show "measure 8, second visit, pass 2, ending 2"
  from structured data. `describe()` is only a formatter. `Note` and `ValidationIssue` are unchanged.

Planner: a validated `VoltaGroup` becomes a section with pass count `N` and per-pass ending, using the
existing builder. Timing is accumulated from exact `MeasureSpan.length` after the source traversal is
planned, never from displayed numbers or nominal meters.

## 5. Downstream behaviour (all reuse M3d machinery)

* **Ties**: a tie never crosses a discontinuity (`REPEAT_JUMP` or `ENDING_SKIP`); one algorithm, with the code chosen by the arrival kind: `TIE_BROKEN_BY_REPEAT` for a repeat jump and `TIE_BROKEN_BY_ENDING` for an ending skip (an ending skip is never called a repeat jump). A tie from the body into ending 1 is
  held on pass 1 and cut (with `TIE_BROKEN_BY_ENDING`) on later passes that skip ending 1 (`w01`); a
  tie out of an ending that is followed by a jump is cut, and the destination ending's tied-to note
  becomes a new attack (`w02`, `w04`); the last ending's tie into the next written measure holds
  (`w03`). Performed-order merging stays the only tie pass.
* **Tempo and meter**: explicit events inside an ending replay each time that ending measure is
  played; the tempo carried across a skip is the effective query; the meter in force is the written
  context of the measure played (`effective_meter_at`), with no event invented. `Song.tempo_map` and
  `Song.time_signatures` are untouched.
* **Lyrics**: the analysis takes the discontinuity set. An ending skip is a hard state boundary exactly like a repeat jump (words, typed and
  untyped melismas end; typed open is `LYRIC_MELISMA_UNCLOSED`, an open word `LYRIC_WORD_UNCLOSED`).
  Pass-specific lyrics (`time-only`, different verses per ending) remain unsupported as before.
* **Pickups**: a pickup before the repeat is not replayed; a pickup inside it is replayed verbatim.
  Lengths always come from the parsed measures (`y01`, `y02`).
* **Provenance**: `NoteOccurrence` is unchanged (part, measure index, visit, performed start); the
  new `PlayedMeasure` fields give pass and ending, so "measure 4, second pass, ending 2" is
  derivable without any change to `Note` or `ValidationIssue`.

## 6. Issue codes

ERROR: `ENDING_NUMBER_INVALID`, `ENDING_NUMBER_UNSPECIFIED`, `ENDING_TYPE_INVALID`,
`ENDING_BARLINE_PLACEMENT`, `ENDING_MID_MEASURE`, `ENDING_OVERLAP`, `ENDING_NUMBER_MISMATCH`,
`ENDING_STOP_WITHOUT_START`, `ENDING_UNCLOSED`, `ENDING_PASS_DUPLICATE`, `ENDING_PASS_MISSING`,
`ENDING_WITHOUT_REPEAT`, `ENDING_STRUCTURE_UNSUPPORTED`, `REPEAT_TIMES_ENDINGS_CONFLICT`; the M3d repeat
errors still apply (`REPEAT_STRUCTURE_CONFLICT` includes endings).
WARNING: `TIE_BROKEN_BY_REPEAT`, `TIE_BROKEN_BY_ENDING` (M3e2).
Removed: `ENDING_NOT_SUPPORTED_YET`, `ENDING_PASSES_INVALID` (split into duplicate/missing).

## 7. Tests

* Oracle: every fixture in `endings/`; accepted structures must equal the MuseScore onsets
  (`v01`-`v05`, `v10`, `v14`, `v15`, `v17` equivalents, `v18`, `v19`, `v20`, `x*`, `y*`); every
  divergence (`v07`-`v09*`, `v11`-`v13`, `v16`, `v20b`, `w02`) is a permanent test naming the
  MuseScore behaviour and our ERROR or warning; every fixture classified.
* Planner: pass/ending assignment for 2, 3 and 16 passes, `1, 2` lists, multi-measure endings,
  consecutive groups, mixed with plain repeats, every `ENDING_*` rule, expansion limit, transitions
  (`SEQUENTIAL`, `ENDING_SKIP`, `REPEAT_JUMP`, `REPEAT_EXIT`) and `repeat_pass`/`endings`.
* Reader: the MuseScore export forms (`<ending ...>1</ending>` text, `1, 2`, `times` inside an
  ending), every placement, number, type and pairing error.
* Downstream: the ties, tempo, meter, lyric and pickup cases of section 5, source immutability, and
  provenance (`PerformanceLocation.describe`).
* Existing M3d tests stay green (plain repeats are unchanged).

## 8. Review outcome

Settled in review: the mark/span/group layering above; pass-set partition with specific diagnostics;
`times` contradicting the endings is an error; the lone-ending rejection; `ENDING_SKIP` and
generalised discontinuities with `repeat_pass`/`endings`; distinct tie codes; STOP/DISCONTINUE preserved
in the span but equivalent for playback. Split: M3e1 (reading, spans, groups, planner, transitions,
provenance) then M3e2 (ties, lyrics, tempo/meter, locations, full oracle comparison).
