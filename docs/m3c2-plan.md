# M3c2 plan: performed lyric analysis

Status: **approved with the decisions below, which supersede any conflicting text further down.**

## Approved decisions (supersede the sections below where they differ)

1. **Tied-note lyrics.** The first source note supplies the attack's lyric. An identical repeated
   continuation lyric is WARNING `LYRIC_TIE_REPEATED`; different content is ERROR
   `LYRIC_TIE_CONFLICT`. These are **our performed-interpretation diagnostics, not MusicXML
   validity rules** (the specification is silent). "Identical" compares the meaningful literal
   content: lyric kind, text, `syllabic`, extend form and elided segments (and the logical verse),
   never merely flattened text. A continuation that differs in syllabic, elision or kind is a
   conflict. Nothing is mutated, moved or discarded; extension-only continuation events
   participate in melisma analysis.
2. **Verse.** Logical verse `"1"` covers explicit `number="1"` and unnumbered lyrics (source
   identities stay distinct). Automatic choice: logical `"1"` if present, else the first logical
   verse in document order. A requested verse overrides. Mixed numbering inside the analyzed
   stream is one line-level WARNING `LYRIC_VERSE_MIXED_NUMBERING`; a fallback to a non-1 verse is
   one explanatory WARNING. Source lyrics are never renumbered.
3. **Typed and untyped extenders are separate state machines** (never one `in_melisma` flag).
   - *Typed* (`START`/`CONTINUE`/`STOP`): explicit MusicXML state. A **rest does not end it**
     (the rest itself gets no continuation role). It lasts until `STOP`, a structurally
     conflicting lyric event, or the end of the line. `CONTINUE`/`STOP` need a compatible open
     explicit extension. Lyric-less attacks inside it are continuations, including after a rest.
   - *Untyped* `<extend/>` (MuseScore): inferred. It ends at the next lyric, **a rest**
     (conservative boundary; our interpretation of an underspecified sequence, not a MusicXML
     rule), humming/laughing, or the end of the line. A lyric-less attack after the rest is
     `MISSING`; one line-level WARNING `LYRIC_MELISMA_INTERRUPTED` counts such cases. An untyped
     extender at the end of the line is never flagged. START is never invented for UNTYPED.
4. **`UNSPECIFIED` syllabic** is not an error by itself: outside an open word it is a complete
   one-syllable word. Inside an open word it is ERROR `LYRIC_WORD_AMBIGUOUS` (never silently
   `END`).
5. **Aggregation.** At most one coverage issue per line (`LYRIC_LINE_EMPTY` or
   `LYRIC_MISSING_SUMMARY`) and one issue per text-hazard kind per line. The exact runs stay in
   the structured result. Genuine structural errors (malformed typed sequences, tie conflicts) may
   still be located individually.
6. **Typed `START` that reaches the end of the line (or is ended without `STOP`)** is WARNING
   `LYRIC_MELISMA_UNCLOSED`; the analysis is kept.
7. **Humming and laughing** are explicit vocal events (`HUMMING`, `LAUGHING`). They end an
   inferred melisma and conflict with an open typed extension (ERROR). They are never treated as
   continuation syllables; a following lyric-less attack is `MISSING`.
8. **Text with `CONTINUE`/`STOP`** is an analysis error (`LYRIC_EXTEND_SEQUENCE_INVALID`), not a
   parser error; the source is unchanged.
9. **Word state and melisma state are independent.** `<extend>` never substitutes for
   `BEGIN`/`MIDDLE`/`END`. A rest does not invalidate an open word; no "words cannot cross rests"
   rule exists. Orphan `MIDDLE`/`END` is `LYRIC_WORD_UNOPENED`, an unfinished word
   `LYRIC_WORD_UNCLOSED`.
10. **Result.** `LineLyricAnalysis` is immutable, references (does not copy) source objects, and
    has no OpenUtau `+`, `+~`, phoneme, tick, singer or FFmpeg concept. A permanent regression test
    proves analysis does not modify `Note`, `Lyric`, `PerformanceNote` or any source text, verse,
    syllabic or melisma value.
11. **Permanent melisma-length regression:** untyped extenders followed by 1, 2, 6 and 23
    lyric-less attacks all work with no length limit.
12. **Renamed codes:** `LYRIC_TIE_CONTINUATION_REPEATS` -> `LYRIC_TIE_REPEATED`,
    `LYRIC_TIE_CONTINUATION_CONFLICT` -> `LYRIC_TIE_CONFLICT`, `LYRIC_VERSE_NUMBERING_MIXED` ->
    `LYRIC_VERSE_MIXED_NUMBERING`, `LYRIC_EXTEND_UNTERMINATED` -> `LYRIC_MELISMA_UNCLOSED`; new:
    `LYRIC_MELISMA_INTERRUPTED`.

---

*Original proposal follows.*

Status of the original text: **proposal, awaiting review. No M3c2 code has been written.**
Builds on M3c1 (commit `635045b`). Research: MusicXML 4.0 reference, 11 synthetic tie-lyric
files through MuseScore Studio 4.7.4 (`tests/fixtures/musicxml/lyrics_ties/`), and the M3c
findings already recorded in [m3c-plan.md](m3c-plan.md).

The analysis is a **pure function** over a voice line. It never mutates the `Song`, a `Note`
or a `Lyric`, never rewrites text, never moves a lyric, and never produces OpenUtau syntax,
phonemes, MIDI ticks or any backend field.

## 1. Research findings

### Lyrics on tied notes
| Case (fixture) | MuseScore 4.7.4 export | MIDI attacks |
|---|---|---|
| lyric on the start only (`t1`, `t5`) | kept as authored | **one attack** per tie group |
| same lyric repeated on the continuation (`t2`) | kept on both notes | one |
| different lyric on the continuation (`t3`) | kept on both notes | one |
| continuation lyric, none on the start (`t4`) | kept as authored | one |
| three notes, lyrics on later members (`t6`) | kept on every member | one |
| extender on the start (`t7a`) / on the continuation (`t7b`) | kept as authored | one |
| extension-only lyric on the continuation (`t7c`) | **dropped** (no text) | one |
| verse 2 on the continuation (`t9`) | kept, number intact | one |

So MuseScore preserves and never moves tie lyrics, and its playback ignores them: a tie group
is one attack carrying whatever the first note's lyric is. MusicXML 4.0 is **silent** about
lyrics on tied notes (the reference pages for `lyric`, `tie` and `tied` say nothing about it).

Three things are kept strictly apart in this plan:

| Level | Statement |
|---|---|
| **MusicXML-specified** | Nothing about tied-note lyrics. A `<tie>` makes the notes one sounding note; a `<lyric>` belongs to the note element that contains it. |
| **MuseScore behavior** | Keeps all lyrics, one attack per tie group, drops an extension-only continuation lyric. |
| **Our conservative policy (ours, not a MusicXML rule)** | The lyric sung at a performed attack is the **first** source note's. A lyric on a later source note must never be silently swallowed (below). |

### Other facts the design relies on
- `PerformanceNote.source` carries every source note with its lyrics, so analysis needs nothing
  beyond a list of `PerformanceNote`s plus the line id (for locations).
- Real-score evidence: untyped extenders followed by 1 to 23 lyric-less notes; whole lyric-less
  voices; no lyrics on tie continuations. The analysis must therefore be cheap on long runs and
  must not flood on lyric-less voices.
- MuseScore always writes an untyped extender and no typed `continue`/`stop`; typed forms come
  from other writers and must still be handled deterministically.

## 2. Input, output, and API

**Input:** `Sequence[PerformanceNote]` for one voice line (the result of `merge_tied_notes`),
the line id, and an optional verse. Rests are included (they end melismas and words). No new
input structure is needed.

Precondition: attacks are in time order and do not overlap. Simultaneous attacks (a chord in a
lyric line) are reported as `LYRIC_SIMULTANEOUS_ATTACKS` (ERROR) and analyzed in input order;
whether such a line is allowed at all is M4's decision.

```
select_verse(streams: Iterable[Lyric | str], *, requested: str | None = None) -> VerseChoice
analyze_line(performed, *, part_id, verse: str | None = None) -> LineLyricAnalysis
analyze_song_lyrics(song, *, verse: str | None = None) -> SongLyricAnalysis
```
`analyze_song_lyrics` merges ties per line, chooses **one** verse for the whole song, and
returns an analysis per line id; tie diagnostics are not repeated (the parser already reported
them).

### Result model (immutable, backend-neutral)
```
AttackRole: SYLLABLE | MELISMA_CONTINUATION | MISSING | HUMMING | LAUGHING | REST | CONFLICT
AttackLyric: index, performed (PerformanceNote), role, lyric (the source Lyric supplying it,
             or None), syllable_count, word_index, syllable_index (within its word),
             melisma_origin (index of the attack that opened the active extension),
             melisma_position (1-based position in that run)
LyricWord:   index, syllables (attack index and part index within an elided lyric),
             text (the syllable texts joined literally, no hyphen handling), interrupted_by_rest
MissingRun:  first_index, last_index, count, first (measure, beat), last (measure, beat)
LyricCoverage: sung, syllables, continuations, missing, humming, laughing, has_any_lyric,
               missing_runs, longest_melisma
LineLyricAnalysis: part_id, verse, verses (all logical verses in document order), attacks,
                   words, coverage, issues
```
There is no field for `+`, `+~`, phonemes, ticks or a synthesizer, by construction.
`CONFLICT` is an attack that cannot be classified without choosing between two lyrics for the
same logical verse; the parser already reported `LYRIC_DUPLICATE_VERSE`.

## 3. Verse selection

Grouping uses `logical_verse` only; the source `verse` is never altered. A line is analyzed for
one **logical verse**. Because an absent `number` and `"1"` share logical verse `"1"`, "explicit
`1`, else unnumbered" collapses to one rule:

1. the requested verse, if given (and found);
2. else logical verse `"1"` if the line has any lyric in it, **whether numbered `1` or
   unnumbered**;
3. else the first logical verse in document order.

A line mixing explicit `1` and unnumbered lyrics is analyzed as one stream (they are the same
logical verse), with WARNING `LYRIC_VERSE_NUMBERING_MIXED` naming that both forms occur.
More than one logical verse gives WARNING `LYRIC_MULTIPLE_VERSES` (selected, available); a
fallback to a non-1 verse because several exist says which was chosen. A requested verse the
line does not have gives ERROR `LYRIC_VERSE_NOT_FOUND`. The song-level function picks one verse
from all lines so every line is analyzed consistently, and a different verse can be requested
later from the UI.

## 4. Classification of each attack (selected verse)

Process attacks in order; keep one melisma state `(active, origin, run)`.

| Attack | Result |
|---|---|
| Rest | Role `REST`. **Ends** any active extension and any melisma run (the extender is not carried across a rest; this is our conservative policy, not a MusicXML statement). |
| Lyric kind `TEXT` for the verse | `SYLLABLE`. Ends any active extension (a new lyric ends the previous melisma). If the lyric's extend form is `UNTYPED` or `START`, a new extension opens here. |
| `HUMMING` / `LAUGHING` | Roles `HUMMING` / `LAUGHING`. End any active extension. Following lyric-less attacks are `MISSING` (no extender semantics exist for them). |
| `EXTENSION`-only lyric, form `CONTINUE` | Requires an active extension: the attack is a `MELISMA_CONTINUATION`. Without one, ERROR `LYRIC_EXTEND_WITHOUT_START`. |
| `EXTENSION`-only lyric, form `STOP` | As `CONTINUE`, and the extension ends **after** this attack. |
| `EXTENSION`-only lyric, form `UNTYPED` or `START` | ERROR `LYRIC_EXTEND_SEQUENCE_INVALID`: an extender that starts with no syllable has no deterministic reading. |
| `TEXT` lyric whose extend form is `CONTINUE` or `STOP` | ERROR `LYRIC_EXTEND_SEQUENCE_INVALID`: it both starts a syllable and claims to continue or stop an earlier one. |
| No lyric for the verse, extension active | `MELISMA_CONTINUATION`, run length +1. **No maximum run length** (a 23-note run is fine). |
| No lyric for the verse, no active extension | `MISSING`. |
| Two lyrics for the verse (duplicate) | `CONFLICT`; nothing is chosen. |

Typed `START` that is never closed by `STOP` before the next lyric, rest or end of line is
WARNING `LYRIC_EXTEND_UNTERMINATED` (implicitly ended). An untyped extender is never flagged for
this: it ends at the next lyric, a rest, or the end of the line, which is how MuseScore writes
every melisma. An open extension at the end of the line is fine.

### Lyrics on tie continuations (our policy)
For each performed tie group, compare the lyrics (for the selected verse) on source notes 2..n
with the attack's lyric (first note):
- **Identical** to the attack's lyric (same kind, text, syllabic, extend form, elision): WARNING
  `LYRIC_TIE_CONTINUATION_REPEATS`. It is redundant, and nothing sung is lost.
- **Anything else** (different text, a lyric where the attack has none, a different extend or
  syllabic): **ERROR `LYRIC_TIE_CONTINUATION_CONFLICT`**, because merging the tie would swallow
  content. The lyric is never moved to the attack and never dropped from the source.
- An **extension-only** continuation lyric (`CONTINUE`/`STOP`) is not content; it is fed to the
  melisma state at that position.
Lyrics for other verses on a continuation are ignored for the selected verse (the multiple-verse
warning already applies).

## 5. Syllabic chains and word reconstruction

Over the `SYLLABLE` attacks, flattening elided segments in order (each segment is a syllable):

| Sequence | Result |
|---|---|
| `SINGLE` | Its own word. |
| `BEGIN` ... `MIDDLE`* ... `END` | One word. |
| `MIDDLE` or `END` with no open word | ERROR `LYRIC_WORD_UNOPENED` (orphan). |
| `BEGIN` or `MIDDLE` open and then `SINGLE` or `BEGIN` | ERROR `LYRIC_WORD_UNCLOSED` for the open word. |
| Open word at the end of the line | ERROR `LYRIC_WORD_UNCLOSED`. |
| `UNSPECIFIED` | WARNING `LYRIC_SYLLABIC_MISSING` (one per line, with the count). With no word open it is its own one-syllable word. **With a word open it is ERROR `LYRIC_WORD_AMBIGUOUS`** (it could be a continuation or a new word; no guess). |

A word interrupted by a rest is valid and recorded (`interrupted_by_rest`), not an error.
`MISSING`, humming and laughing attacks inside a word do not break the chain. Words are
reconstructed by joining syllable text literally; the source text is not touched.

## 6. Missing-lyric aggregation (no floods)

After classification, **at most one coverage issue per line**:
- no syllable, humming or laughing attack at all: WARNING `LYRIC_LINE_EMPTY`;
- otherwise any `MISSING` attacks: one WARNING `LYRIC_MISSING_SUMMARY`: "N of M sung attacks have
  no lyric, in R runs; first at measure m beat b, longest K."
Every run is also in the structured `coverage.missing_runs` for a UI. Attacks explained by an
active melisma are `MELISMA_CONTINUATION` and are never reported. Whether any of this blocks
generation is M4/M6's decision.

## 7. Text hazards (analysis only; the text is never rewritten)

Per `SYLLABLE` lyric of the selected verse, aggregated to **one issue per kind per line** (count
and first location): `LYRIC_TEXT_WHITESPACE` (leading or trailing), `LYRIC_TEXT_INNER_SPACE`,
`LYRIC_TEXT_TRAILING_HYPHEN`, `LYRIC_TEXT_RESERVED_CHARACTERS` (text that is only `-`, starts with
`+`, or contains `[`, `]` or `~`), `LYRIC_ELIDED` (two syllables on one note). All WARNINGs: they
describe what a later synthesis step might misread.

## 8. Issue codes

ERROR: `LYRIC_TIE_CONTINUATION_CONFLICT`, `LYRIC_EXTEND_WITHOUT_START`,
`LYRIC_EXTEND_SEQUENCE_INVALID`, `LYRIC_WORD_UNCLOSED`, `LYRIC_WORD_UNOPENED`,
`LYRIC_WORD_AMBIGUOUS`, `LYRIC_SIMULTANEOUS_ATTACKS`, `LYRIC_VERSE_NOT_FOUND`.
WARNING: `LYRIC_TIE_CONTINUATION_REPEATS`, `LYRIC_EXTEND_UNTERMINATED`, `LYRIC_SYLLABIC_MISSING`,
`LYRIC_MULTIPLE_VERSES`, `LYRIC_VERSE_NUMBERING_MIXED`, `LYRIC_LINE_EMPTY`,
`LYRIC_MISSING_SUMMARY`, `LYRIC_TEXT_WHITESPACE`, `LYRIC_TEXT_INNER_SPACE`,
`LYRIC_TEXT_TRAILING_HYPHEN`, `LYRIC_TEXT_RESERVED_CHARACTERS`, `LYRIC_ELIDED`.

## 9. Files and tests

New: `models/lyric_analysis.py` (the result types), `core/lyrics/__init__.py`,
`core/lyrics/verses.py`, `core/lyrics/melisma.py` (state machine), `core/lyrics/words.py`,
`core/lyrics/hazards.py`, `core/lyrics/analysis.py`.

Fixtures (synthetic, original): the 11 staged `lyrics_ties` files plus new analysis fixtures built
in tests (inline XML via the existing builders) and one TTBB-layout fixture with a lyric-bearing
voice (single syllables, a three-syllable word, a word split by a rest, a 23-note untyped melisma,
a tie group, a lyric-less second voice).

Tests: normal single syllables; multisyllabic words; untyped melisma followed by 1, 2, 6 and 23
lyric-less attacks; typed start/continue/stop chains and the invalid orders; extender ended by a
new lyric, by a rest, and by the end of the line; humming and laughing; every tie row above
(including the extension-only and verse-2 cases); multiple verses and the selection rules (only
`1`; only unnumbered; both mixed; only verse 2; several without `1`; requested verse; missing
verse); a completely lyric-less voice (one issue, not hundreds); a mostly lyric-less voice with
isolated lyrics; malformed syllabic chains (orphans, unclosed, begin-then-single, `UNSPECIFIED`
inside an open word); elided text; every hazard; simultaneous attacks; and source immutability
(the `Song`, notes and lyrics are equal before and after, and no issue changes any text).

## 10. Decisions needed

1. **Tie policy:** identical repeated continuation lyric is a WARNING; anything else an ERROR.
   Extension-only continuation lyrics feed the melisma state. Agreed?
2. **Verse rule:** logical verse `"1"` (explicit or unnumbered) first, then the first logical verse;
   mixed `1`/unnumbered is analyzed as one stream with a warning. Agreed?
3. **Rest ends a melisma** (a lyric-less attack after a rest is `MISSING`). Agreed, given the
   specification is silent and MuseScore's behavior across a rest could not be confirmed?
4. **`UNSPECIFIED` inside an open word is an ERROR** (`LYRIC_WORD_AMBIGUOUS`). Agreed?
5. **Aggregation:** at most one coverage issue and one issue per hazard kind per line, with the
   runs in the structured result. Agreed?
6. **Typed `START` never closed** is a WARNING; untyped is never flagged. Agreed?
7. **Humming/laughing** end a melisma and are followed by `MISSING` for lyric-less attacks.
   Agreed?
8. **Research commit first** (this plan plus the `lyrics_ties` fixtures), then M3c2?
