# M3c plan: lyrics and melisma interpretation

Status: **approved with the decisions in "Approved decisions" below, which supersede any
conflicting text further down.** Split into M3c1 (literal parsing) and M3c2 (performed lyric
analysis).

## Approved decisions

1. **`<syllabic>` is source information.** `Syllabic` gains `UNSPECIFIED` (absent). M3c1 never
   invents `SINGLE`. A permanent divergence test records: source has no `<syllabic>` -> our model
   keeps `UNSPECIFIED` -> MuseScore's re-export writes `single`. M3c2 may interpret
   `UNSPECIFIED` conservatively.
2. **`number` is preserved as written:** `Lyric.verse` is `None` when the attribute is absent
   (never the literal `"1"`). Logical grouping is separate: a small `logical_verse` rule treats an
   absent number as the default stream `"1"` for duplicate detection and (M3c2) verse grouping,
   without changing the source value. `<lyric>` and `<lyric number="1">` stay distinguishable.
3. **Elisions and multiple `<text>`:**
   - A standard `<elision>` is parsed per the specification into `LyricSegment`s, keeping its
     text and `smufl` name.
   - MuseScore's pattern is supported only when deterministic: texts `t0, g1, t1, g2, ...` where
     every in-between text is **exactly one `U+E551`** (SMuFL `lyricsElisionNarrow`). That is the
     only glyph observed (MuseScore writes U+E551 for `lyricsElision`, `lyricsElisionNarrow`,
     `lyricsElisionWide` and an empty elision alike; fixtures `l25`, `l35`-`l38`). Other private-use
     characters, including U+E550 and U+E552, are **not** treated as elisions.
   - Any other multi-`<text>` structure is `LYRIC_TEXT_STRUCTURE_UNSUPPORTED` (ERROR). Texts are
     never concatenated on a guess. A single `<text>` containing an undertie, underscore, no-break
     space or ordinary space is one literal text (reported later by analysis).
4. **Duplicate logical verse on one note is an ERROR** (`LYRIC_DUPLICATE_VERSE`), including the
   moved grace and chord lyrics MuseScore produces. `Note.lyrics` is a tuple, so **both** source
   lyrics are kept; none is chosen.
5. **Lyrics on rests, cue, grace and unpitched notes are distinct ERRORs:** `LYRIC_ON_REST`,
   `LYRIC_ON_CUE_NOTE`, `LYRIC_ON_GRACE_NOTE`, `LYRIC_ON_UNPITCHED_NOTE`. The literal lyric text
   is in the diagnostic and is **never attached to another note** (we do not reproduce
   MuseScore's moving of a grace lyric onto the next note or a chord lyric onto the first member).
6. **`Lyric.name`** is preserved verbatim (metadata, not unsupported). **`time-only`** is
   preserved verbatim in `Lyric.time_only` and is `LYRIC_TIME_ONLY_UNSUPPORTED` (ERROR) in v1,
   because it changes which repeat pass a lyric applies to.
7. **Slurs are not melisma evidence.** A slur is notation, not a substitute for lyric `<extend>`.
   lyric + `<extend>` is eligible melisma evidence; lyric + slur only infers nothing, and a
   lyric-less attack in the slur remains unresolved. The observed MuseScore behavior is documented.
8. **Missing lyrics are WARNINGs at M3c2, aggregated:** whole line has no lyrics; N unresolved
   attacks; an unresolved run from measure X to Y. No per-note flood.
9. **Default verse (M3c2, deterministic):** an explicit `"1"`, else unnumbered, else the first
   lyric stream in document order. A fallback to a non-1 stream is a WARNING naming the stream.
   Source verses are never renumbered, and the architecture allows choosing another verse later.
10. **`<extend>` keeps its source form** (no extend / untyped `<extend/>` / `start` / `continue` /
    `stop`): `Melisma` gains `UNTYPED`. M3c1 does not translate untyped to `START`; M3c2
    interprets it ("always treated as the start", MusicXML 4.0) and documents MuseScore's dialect.
11. **Ties:** lyrics stay on the source notes, including tie continuations; nothing is moved to
    the first note. M3c2 defines how several source notes of one `PerformanceNote` that carry
    different lyric text are reported (ambiguity ERROR, final code named after research).
12. **`<humming/>` and `<laughing/>` are legitimate vocal events** (MusicXML 4.0: "a humming
    voice" / "a laughing voice", always empty, replacing text). They are **preserved literally**
    (`LyricKind.HUMMING` / `LAUGHING`) and are not an error in M3c1. M3c2/M6 decide whether a
    backend can sing them. That MuseScore drops them on re-export is compatibility evidence only.
13. **Research commit first**, then M3c1; M3c1 is reviewed before it is committed.

### Revised model (M3c1)

`Lyric(kind, text, syllabic, verse, name, time_only, melisma, elided)`: `kind` is `TEXT`,
`EXTENSION` (extender only), `HUMMING` or `LAUGHING`. Only `TEXT` has text and a `Syllabic`
other than `UNSPECIFIED`. `verse` is `str | None`. `LyricSegment(text, syllabic, joiner,
joiner_smufl)`. `Melisma` is `NONE`, `UNTYPED`, `START`, `CONTINUE`, `STOP` (the source form of
`<extend>`). The model does **not** judge odd combinations (text with `extend type="stop"`); the
source is stored and M3c2 flags what matters.

### New codes in M3c1
`LYRIC_DUPLICATE_VERSE`, `LYRIC_ON_REST`, `LYRIC_ON_CUE_NOTE`, `LYRIC_ON_GRACE_NOTE`,
`LYRIC_ON_UNPITCHED_NOTE`, `LYRIC_TIME_ONLY_UNSUPPORTED`, `LYRIC_TEXT_STRUCTURE_UNSUPPORTED`,
`LYRIC_EXTEND_TYPE_INVALID` (ERRORs); `LYRIC_EMPTY` (WARNING; a lyric with no usable content is
skipped). `LYRIC_EXTEND_INVALID` from the first draft is dropped.

---

*Original proposal follows; where it differs from the decisions above, the decisions win.*
Builds on M3b2b (commit `629b554`). Evidence: the MusicXML 4.0 reference; MuseScore Studio 4.7.4
round trips of 34 synthetic lyric files (`tests/fixtures/musicxml/lyrics/`); and structure-only
counts (never text) from one real TTBB export that is not in the repository.

All lyric fixtures use original nonsense syllables (`la`, `ni`, `na`, `ma`, `ba`) and a few
symbol strings (`+`, `-`, `[la]`, `la~`) for special-character tests. No real lyrics.

## 1. Principle: literal source, separate interpretation

| Layer | Does | Never does |
|---|---|---|
| **Parser** (M3c1) | Reads each `<lyric>` into the M2 `Lyric` model exactly as written, on the note where it occurs. Reports lyric structures that cannot be stored or are ambiguous. | Infer melismas, join syllables into words, choose a verse, copy lyrics between lines, or touch OpenUtau conventions. |
| **Analysis** (M3c2, `core/lyrics/analysis.py`) | A pure function over one voice line's *performed* notes: classifies every attack (syllable, melisma continuation, missing), reconstructs words, checks syllabic chains, and flags text hazards. Source notes and `Song` are untouched. | Emit `+`, `+~`, or any MIDI/OpenUtau text. Decide blocking policy for missing lyrics (that is M4/M6). |

The exporter (M6) will consume the analysis output; OpenUtau `+`/`+~` conversion stays out of M3c.

## 2. Research findings

### MusicXML 4.0
- Content model: `(syllabic?, text, (elision?, syllabic?, text)*, extend?) | extend | laughing |
  humming`, then optional `end-line`, `end-paragraph`. "A second `<syllabic>` is not allowed
  unless preceded by an `<elision>`."
- `number` is the lyric line (verse); `name` labels a type such as "verse" or "chorus";
  `time-only` says which repeat passes use the lyric.
- `<syllabic>` is single / begin / middle / end; the reference does not say it is mandatory.
- `<extend type>` is start / stop / continue; when absent it is "always treated as the start of
  the extension" (the pre-3.0 behavior).
- `<elision>` carries the joining symbol (no-break space, underscore, undertie) or a `smufl`
  glyph name; with neither, the glyph is application-specific.
- `<humming/>` and `<laughing/>` stand in for text.
- The reference says nothing about lyrics on rests, tied notes, grace notes or chords.

### MuseScore 4.7.4 (observed)
| Case | Observation |
|---|---|
| Melisma | `<extend/>` is **always written with no `type`**, on the first note only. Following notes carry **no `<lyric>` element**. Typed start/continue/stop input is normalized to this. |
| Slur without extender | The slurred notes after a lyric have no lyric and **no extend**. Nothing in the lyric data says they belong to the syllable. |
| Melisma across a rest | The extend stays on the first note; the lyric-less note after it and the rest are just written. |
| Tie | The lyric stays on the first tied note. A lyric on the tie's **continuation is kept** (it can carry a different syllable). An extend on a tied first note is kept. |
| Rest | A lyric on a **rest is kept**. |
| Cue note | A lyric on a cue note is kept. |
| Grace note | The grace note's lyric is **moved to the next main note**, giving that note two lyrics with the **same** `number`. |
| Chord | A lyric on a later chord member is **moved to the first member**, again as a second lyric with the same `number`. |
| Verses | Several numbers on one note are kept. A file with only verse 2 comes out as verse **1** (MuseScore renumbers). `name` and `time-only` attributes are **dropped**. A missing `number` is written as `1`. |
| Syllabic | begin/middle/end are preserved exactly, including a word interrupted by a rest, an `end` with no `begin`, and a `begin` never closed. Text without `<syllabic>` is written as `single`. |
| Elision | One `<text>` element holding the whole string (`la‿ni`, `la_ni`), or, with a SMuFL elision, three `<text>` elements (the middle one a private-use glyph, e.g. U+E551). It does not write `<elision>`. |
| `<humming/>`, `<laughing/>` | **Dropped** on import (no lyric exported). |
| `<end-line/>`, `<end-paragraph/>` | Dropped. |
| Special text | `+`, `-`, `[la]`, `la~` are preserved verbatim. A text ending in a hyphen (`ba-`) is kept with its hyphen. |
| Whitespace | Leading and trailing spaces are preserved; an empty `<text>` is dropped. |
| Two voices | Each voice keeps its own lyrics. |

### Real TTBB export (structure only)
Two parts, two voices each. Verse 1 only. **Every `<extend>` is untyped** (36 in total). Melisma
runs of lyric-less notes after an extender were 1 to 6 notes long, plus one of 23. Lyric-less
notes were the large majority: whole voices carry no lyrics at all (their notes are lyric-less
and not tied or extended). There were no lyrics on rests or tie continuations, no duplicate
verses, no multi-`<text>` lyrics or elisions, no `name`/`time-only`, no edge whitespace and no
special characters. Slurs were common (36 and 40).

Consequences: the untyped extender is the dialect that matters; lyric-less lines are the norm,
so analysis must summarize rather than flood; and slurred notes may or may not be melismas.

## 3. M3c1: parser (literal)

For every `<lyric>` on a note that becomes a `Note`, in document order:

| Source | Result |
|---|---|
| `number` | `Lyric.verse` verbatim. **Absent number = verse `"1"`** (a deterministic default, documented; MuseScore does the same). |
| `<text>` | Stored **verbatim**: no stripping, no case change. (The shared `child_text` helper strips and must not be used here.) |
| `<syllabic>` | `Syllabic` as written. **Absent with text**: stored as "unspecified" (see decision 1). |
| `<extend>` | Absent `type` or `start` = `Melisma.START`; `continue` = `CONTINUE`; `stop` = `STOP`. A lyric with text and a `continue`/`stop` extend, or an extension-only lyric with `start`/absent type, is `LYRIC_EXTEND_INVALID` (ERROR). |
| `<elision>` between texts | `LyricSegment(text, syllabic, joiner=<elision text>)`. |
| Consecutive `<text>` with no `<elision>` | If a middle `<text>` is only private-use (SMuFL) characters it is the joiner (MuseScore's form). Any other multi-text lyric is `LYRIC_MULTIPLE_TEXT_AMBIGUOUS` (ERROR). |
| `name` | New optional `Lyric.name` (decision 6). |
| `time-only` | `LYRIC_TIME_ONLY_UNSUPPORTED` (ERROR, v1): it makes the lyric depend on the repeat pass. |
| `<humming/>`, `<laughing/>` | `LYRIC_NONTEXT_UNSUPPORTED` (ERROR). Nothing is guessed (e.g. "mm"). |
| `end-line`, `end-paragraph` | Ignored (formatting only). |
| Empty `<text>` | `LYRIC_EMPTY_TEXT` (WARNING); that lyric is skipped. |

Notes that cannot hold the lyric, plus duplicates:

| Situation | Result |
|---|---|
| Two lyrics with the **same verse** on one note (including MuseScore's moved grace/chord lyrics) | `LYRIC_DUPLICATE_VERSE` (ERROR). Both are kept in the `Song`; nothing picks one. |
| Lyric on a **rest** | `LYRIC_ON_REST` (ERROR). `Note` forbids lyrics on rests, so the lyric is **not stored**; the diagnostic message carries its text, verse and location so it can be repaired. |
| Lyric on a **cue, grace or unpitched** note (not sung, not emitted) | `LYRIC_ON_UNSUNG_NOTE` (ERROR), message carries the text. The syllable would otherwise vanish silently. |
| Lyric on a **chord member** | Kept on that note as written. (Chord handling is M4.) |

Lyric-less notes stay lyric-less. A lyric on a **tie continuation** is kept on its source note
(analysis reports it).

## 4. M3c2: analysis (`core/lyrics/analysis.py`)

`analyze_line(performed: Sequence[PerformanceNote], *, verse: str, part_id: str) ->
LineLyricAnalysis`. Also `available_verses(performed) -> tuple[str, ...]` (document order).

Per **attack** (a `PerformanceNote`, so tied groups are one attack):

| `LyricRole` | When |
|---|---|
| `SYLLABLE` | The first source note has a lyric with text for this verse. |
| `MELISMA_CONTINUATION` | No lyric, and the previous attack in the line is a syllable or continuation whose lyric started a melisma (`START`, i.e. an extender), with no rest and no new lyric between. A typed extension-only lyric (`CONTINUE`/`STOP`) from other writers is honored; `STOP` ends the run. |
| `MISSING` | No lyric and not explained by a melisma. |
| `REST` | A rest (no lyric needed). |

Derived facts (no OpenUtau text): word membership (word id, syllable index, syllable count),
melisma run length, and which lyric supplied the syllable.

Diagnostics (all located by line, measure, beat):

| Code | Severity | Meaning |
|---|---|---|
| `LYRIC_MISSING` | WARNING | A **run** of consecutive missing attacks (one issue per run, with its length), not one per note. |
| `LYRIC_LINE_EMPTY` | WARNING | The whole line has no lyric for this verse (reported once, instead of `LYRIC_MISSING`). |
| `LYRIC_ON_TIE_CONTINUATION` | ERROR | A tied continuation carries a lyric that merging would swallow. |
| `LYRIC_WORD_UNCLOSED` | ERROR | A `begin`/`middle` syllable is not followed by a `middle`/`end` of the same word before a new word starts or the line ends. |
| `LYRIC_WORD_UNOPENED` | ERROR | A `middle`/`end` syllable with no open word. |
| `LYRIC_SYLLABIC_MISSING` | WARNING | Text with no `<syllabic>`; treated as `single` for chaining only. |
| `LYRIC_MULTIPLE_VERSES` | WARNING | More than one verse exists; only the chosen verse is analyzed. |
| `LYRIC_ELIDED` | WARNING | Two syllables on one note. |
| `LYRIC_TEXT_WHITESPACE` / `LYRIC_TEXT_INNER_SPACE` / `LYRIC_TEXT_TRAILING_HYPHEN` | WARNING | Leading/trailing space; a space inside one note's text; a hyphen written inside the text as well as `<syllabic>`. |
| `LYRIC_TEXT_RESERVED_CHARACTERS` | WARNING | The text is, or starts or ends with, characters a synthesizer front end may interpret: a lone `-`, a leading `+`, `[`/`]`, `~`. Reported, never rewritten. |

A word that is split by a rest (`ba [rest] na`) is valid and not reported. Which lyric a
melisma continuation belongs to is data in the result, not a rewrite of the source.

Missing lyrics are reported as WARNING **facts**. Whether a lyric-less line may be generated
(copy another voice, use a fill syllable, ask the user) is a product decision for M4/M6.

## 5. Constraints this must respect for the later OpenUtau step (no conversion in M3c)

- One lyric per OpenUtau note: the analysis is per **attack** (tied groups merged), so each
  performed note maps to one syllable or one continuation.
- A syllable is only meaningful inside its **word** (the phonemizer works on whole words), hence
  the word reconstruction and the unclosed/unopened errors.
- Melisma notes will need the "extend the current syllable" form later; a lyric-less note must
  never reach the exporter unresolved (the default lyric would be invented), hence `MISSING`.
- Two syllables on one note, internal spaces and reserved characters cannot be represented
  faithfully; they are reported so the exporter can refuse or ask.
- Only one verse can be sung; the chosen verse is explicit.

## 6. Fixtures and tests

Fixtures (synthetic, original): the 34 research files already staged in
`tests/fixtures/musicxml/lyrics/{inputs,musescore_roundtrip}`, plus a TTBB-layout lyric fixture
(`lyrics_ttbb.musicxml`: lyrics on one voice with melismas, a tie, a word split by a rest, and a
lyric-less second voice) with a MuseScore re-export.

Planned tests: every row of the parser tables (including exact text preservation with edge
spaces); every extend/type/position case; duplicate-verse (grace and chord inputs from the real
MuseScore output); rest/cue/grace/unpitched lyrics; verse number defaults and multiple verses;
analysis roles for typed and untyped extenders, runs broken by lyrics and rests, melisma at the
end of a line, tie continuation with and without a lyric, the unclosed/unopened/interrupted word
cases, `begin`..`end` across a rest, run grouping for `LYRIC_MISSING`, `LYRIC_LINE_EMPTY`, special
characters and whitespace, verse selection, source immutability, and `Song`/`Note` unchanged by
analysis. Permanent MuseScore tests: "MuseScore always writes untyped `<extend/>`", "MuseScore
moves grace and chord lyrics onto one note", "MuseScore renumbers a lone verse 2".

## 7. Proposed split
- **M3c1**: model touch-ups (decisions 1 and 6), the literal parser, its tests and fixtures.
- **M3c2**: `core/lyrics/analysis.py` and its tests.
Each ends with a commit, push and green CI.

## 8. Decisions needed

1. **Absent `<syllabic>` on a text lyric.** Preserve "unspecified" (relax the M2 invariant so
   `syllabic` may be `None` with text; analysis treats it as `single` with
   `LYRIC_SYLLABIC_MISSING`), or default to `SINGLE` in the parser? I recommend preserving it.
2. **Absent `number` is verse `"1"`.**
3. **Elision forms.** A middle `<text>` made only of private-use (SMuFL) characters is the joiner;
   any other multi-`<text>` lyric is an ERROR. OK?
4. **Duplicate verse on one note is an ERROR** (this includes the MuseScore-moved grace and chord
   lyrics). OK?
5. **Lyrics on rests, cue, grace or unpitched notes are ERRORs** and, for rests/unsung notes,
   are not stored (the message keeps the text). OK?
6. **`Lyric.name`** added to the model (label only), while `time-only` is an unsupported ERROR in v1.
7. **Slurs.** Conservative (recommended): slurs are not read, so a slurred lyric-less note with no
   extender is `MISSING` (the user adds an extender in MuseScore). The alternative is to read
   slurs as notation data and treat them as melisma hints. Which?
8. **Severity of missing lyrics** is WARNING from the analysis, with blocking left to M4/M6. OK?
9. **`humming`/`laughing`** unsupported (ERROR), never mapped to "mm".
10. **Verse selection.** The analysis takes the verse explicitly; the default for the first
    release is the first verse in document order, with `LYRIC_MULTIPLE_VERSES` when there are
    more. OK?
11. **Split** into M3c1 and M3c2 as above?
12. **Research commit.** Commit this plan and the staged lyric fixtures first (as before)?
