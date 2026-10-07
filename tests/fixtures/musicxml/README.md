# MusicXML research fixtures

All scores here are tiny, original and hand-authored. No copyrighted music.

| Directory | Contents |
|---|---|
| `inputs/` | Hand-written MusicXML experiments (`e1_...` to `e12_...`). |
| `musescore_roundtrip/` | The same files after MuseScore Studio 4.7.4 imported and re-exported them (`musescore_roundtrip/e1_tenor_clef8vb_pitch_oct4.mxl` is the compressed form). |
| `oracle/` | Note-on onsets and MIDI note numbers from MuseScore's MIDI export of each input, as JSON (480 PPQ). MuseScore expands repeats and merges ties, so these are the expected sounding timeline. |

What each experiment checks:

| File | Question |
|---|---|
| `e1_*` | Does `<clef-octave-change>` change `<pitch>`? (No.) |
| `e2_*` | `<transpose>` semantics; combining it with an octave clef (double transposition). |
| `e3_*` | One part with two staves and four voices vs four separate parts. |
| `e4_forward_gap` | `<backup>`/`<forward>` positioning of a late-starting voice. |
| `e5_pickup` | Implicit pickup measure. |
| `e6_ties` | Tie across a barline. |
| `e7_triplet` | Eighth triplet and exact durations. |
| `e8*`, `e9`, `e12` | Repeats, `times`, first/second endings. |
| `e10_lyrics` | Syllabic, extend (melisma), elision, two verses. |
| `e11_dacapo` | D.C. al Fine (MuseScore did **not** play the jump; inconclusive). |

## `tempo_ties/`

Research for M3b2 (see `docs/m3b2-plan.md`). Same layout as above (`inputs/`,
`musescore_roundtrip/`, `oracle/`), but the oracle JSON also lists MIDI tempo events as
`microseconds_per_quarter` integers (exact, no floats). Every score is a four-note C D E F
scale or a variation of it, hand-written for this purpose: original, synthetic, no melodies and
no lyrics from any real work, and safe to publish.

| File | Question |
|---|---|
| `t_a_at_cursor` | Tempo placed between notes (beat 3). |
| `t_b_dir_offset_no`, `t_c_dir_offset_yes`, `t_e_dir_offset_default` | Direction `<offset>` (after one quarter note) with `sound` no / yes / absent. MusicXML 4.0: only `yes` moves the tempo. MuseScore moves it in all three (tempo at tick 960). |
| `t_d_sound_offset` | `<offset>` inside `<sound>`. MusicXML 4.0: it applies. MuseScore ignores it (tempo stays at tick 480). |
| `t_f_two_changes` | Two tempo changes in one measure. |
| `t_g_decimal` | Decimal tempo (92.5). |
| `t_h_zero` | `tempo="0"` (spec: "ask the user"). MuseScore ignores it and writes 120. |
| `u_tie_and_tied`, `u_tie_only`, `u_tied_only` | `<tie>` and `<tied>` combinations. MuseScore merges all three. |
| `u_chain` | Three tied notes. |
| `u_enharmonic` | C#4 tied to Db4. |
| `u_pitch_mismatch`, `u_unmatched_start`, `u_unmatched_stop` | Invalid ties. MuseScore plays every note. |

MuseScore's MIDI output always contains a tempo event (a default 120 when the score has none), so
that default is never treated as score data.

## `lyrics/`

Research for M3c (see `docs/m3c-plan.md`): 38 single-measure scores with `inputs/` and
MuseScore 4.7.4 `musescore_roundtrip/` outputs. Every lyric is an original nonsense syllable
(`la`, `ni`, `na`, `ma`, `ba`) or a short symbol string used only to test special-character
handling (`+`, `-`, `[la]`, `la~`). No real lyrics.

| Files | Question |
|---|---|
| `l01`-`l05` | Melisma: typed extend, untyped extend, slur with no extend, extend across a rest, extend at the end of the part. MuseScore always writes an untyped `<extend/>` and leaves following notes lyric-less. |
| `l06`-`l08` | Lyrics and ties: on the first note only, on both notes, with an extender. |
| `l09`-`l12` | Lyrics on a rest, a cue note, a grace note, and chord members. MuseScore keeps the first two and moves the grace and chord lyrics onto the main/first note as a second lyric with the same number. |
| `l13`-`l17` | Verses: two verses, verse 2 only (MuseScore renumbers it to 1), no number, `name`, `time-only` (both attributes dropped). |
| `l18`-`l22` | Syllabic: a three-syllable word, a word split by a rest, `end` without `begin`, `begin` never ended, text without `<syllabic>` (written as `single`). |
| `l23`-`l26` | Elision (`<elision>` with a glyph, an underscore, a SMuFL glyph) and a text containing a space. |
| `l27`-`l29` | `<humming/>`, `<laughing/>` (dropped by MuseScore), `end-line` / `end-paragraph` (dropped). |
| `l30`-`l34` | Special characters, a trailing hyphen, two voices with their own lyrics, edge whitespace (kept), empty text (dropped). |
| `l35`-`l38` | `<elision>` forms: `smufl="lyricsElision"`, `smufl="lyricsElisionWide"`, a no-break space, and an empty element. MuseScore writes the same single SMuFL glyph **U+E551** (font "Leland Text") between two `<text>` elements for all three non-space forms, and keeps only one `<syllabic>` (the last). A no-break-space elision becomes one `<text>` with U+00A0 inside. |

The 38 lyric inputs contain only the syllables `la`, `ni`, `na`, `ma`, `ba` and the symbol strings
named above; no other words appear in any of them.

## `lyrics_ties/`

Research for M3c2 (see `docs/m3c2-plan.md`): lyrics on tied notes, with `inputs/`, MuseScore
4.7.4 `musescore_roundtrip/` and `oracle/` JSON (the MIDI note-ons, i.e. the performed attacks).
Original nonsense syllables only (`la`, `ni`, `na`). MuseScore keeps every lyric exactly as
given and plays one attack per tie group whatever the lyrics are.

| File | Case |
|---|---|
| `t1_lyric_on_start_only` | Lyric on the tie start only (the normal case). |
| `t2_same_lyric_repeated` | The same lyric repeated on the continuation. |
| `t3_different_lyric_on_continuation` | A different lyric on the continuation. |
| `t4_continuation_lyric_only` | A lyric on the continuation and none on the start. |
| `t5_three_note_tie_first_only` | Three tied notes, lyric on the first only. |
| `t6_three_note_tie_later_members` | Three tied notes with a lyric on every member. |
| `t7a_extend_on_tie_start` | An extender on the tie start. |
| `t7b_extend_on_continuation` | A lyric with an extender on the continuation. |
| `t7c_extend_only_on_continuation` | An extension-only lyric on the continuation (MuseScore drops it). |
| `t8_tie_then_next_note_lyric_less_after_melisma` | A melisma whose second attack is a tie group. |
| `t9_verse2_only_on_continuation` | Verse 2 lyric on the continuation, verse 1 on the start. |

## `ttbb/`

Original, synthetic fixtures that mirror the *structure* of a common MuseScore barbershop export
(not any real score): two parts ("TENOR\nLEAD", "BARI\nBASS") in a bracketed part group, one
implied staff and two voices each, divisions 12, G clef with octave change -1 and F clef, a
one-beat implicit pickup (measure 0), a tie across a barline, a 4/4 to 3/4 meter change, and a
voice that enters via `<forward>`. The pitches are a plain scale/arpeggio pattern with no melody
or lyrics from any real work.

| File | Tempo |
|---|---|
| `ttbb_layout` | none (MuseScore's MIDI adds a default 120, which is never score data) |
| `ttbb_layout_shared_tempo` | 96 in both parts at the start |
| `ttbb_layout_tempo_change` | 96 then 72 (at the 3/4 measure), declared in both parts |
| `ttbb_layout_tempo_first_part_only` | 96 then 72, declared in the first part only (typical MuseScore) |

Each has a MuseScore re-export and an oracle JSON (notes and exact tempo events).

Provenance: generated on 2026-10-06 with MuseScore Studio 4.7.4 on Windows. These are
research inputs for the M3 parser, not final test fixtures; M3 will add its own focused ones.

## `repeats/`

M3d research. Every fixture is one **whole note per measure**, and the pitch names the measure
(C4 = A = measure 1, D4 = B = measure 2, E4 = C, F4 = D, G4 = E, A4 = F, B4 = G), so a playback
order is readable straight off the oracle. Each `*.oracle.json` holds MuseScore Studio 4.7.4's MIDI
export of the fixture (480 PPQ): note onsets with their measure label, tempo events and time
signatures. MuseScore is a behavioural oracle only; where it is silent, wrong or inconsistent with
the specification the M3d plan says so and a permanent test pins the divergence.

| Fixtures | What they show |
|---|---|
| `r01_simple`, `r01_times_*` | `times` absent = 2 passes; `times` is the **total** number of passes (3 = three passes, 9 = nine). `times` 0, 1 and non-numeric: MuseScore plays one pass. |
| `r02_*`, `s05`, `s06` | Backward repeat with no forward: MuseScore repeats from the **start of the score**, including for a second such repeat (`r02c`), but after a forward-marked repeat a later bare backward returns to that **earlier forward** (`s06`). The two readings disagree, so M3d only accepts the first. |
| `r03_*`, `s07` | Nested repeats: MuseScore does **not** nest. The inner forward replaces the outer one, so `\|: A \|: B C :\| D :\| E` plays A B C B C D B C D E (true nesting would restart at A). A second forward before any backward also replaces the first. |
| `r04_*`, `s08` | Consecutive repeats, including one-measure repeats and per-barline `times`. Fine. |
| `r05_*` | Pickup measures: replayed verbatim, as a short measure; no special case. |
| `r06_*`, `s09`, `s10` | Repeats in more than one part. MuseScore silently keeps **one part's** structure (the last part's) and applies it to all parts, even when the parts disagree. |
| `r07_*` | Ties and repeats. MuseScore ties only across **score-adjacent** measures: a tie out of the end of a repeat is held on the last pass and broken on the others; a tie never crosses a jump (`r07b`); a tied-to note at a repeat start produces **no attack** on later passes (`r07c`, a MuseScore artefact). |
| `r08_*`, `s01`-`s03` | Tempo and repeats: a tempo is a property of the **source position**. Every pass re-emits the tempo in force at the landing measure (`s01`: 120 again, not the 60 carried from the previous pass). |
| `r09_*`, `s04` | Meter: likewise; each pass replays each measure with that measure's own meter. |
| `r12_after_jump` | `after-jump="yes"` is ignored by MuseScore. |
| `r13`, `q01`-`q07` | Repeat barline placement: MuseScore attaches a repeat to the **measure that contains the barline element**, whatever its `location`. A forward at `right` of measure 2 starts at measure 2; a backward at `left` of measure 3 ends at measure 3; a missing `location` (default `right`) on a forward starts at its own measure. The specification's reading of those is one measure later (forward) or earlier (backward). |
| `q08_mid_measure_back` | A repeat barline in the middle of a measure is moved to the end of the measure. |

All `repeats/` fixtures are original synthetic scores (one whole note per measure, no lyrics, no real music). Only the extracted JSON is committed; the `.mid` files MuseScore wrote are not, so the audio/binary guard needs no MIDI exemption.

The `r05*` pickup fixtures end with a three-beat measure written in 4/4 without `implicit`, so our existing `MEASURE_INCOMPLETE` policy (the timeline assumes the full measure) and MuseScore (which shortens it) give different timings. The oracle tests assert the performed **order** only for them; the exact pickup/repeat arithmetic is tested separately with `implicit="yes"` measures.

## `endings/`

M3e research (first/second endings, voltas). Same conventions as `repeats/`: one whole note per measure, the pitch names the measure (A = measure index 0 ... G = 6), original synthetic scores, JSON oracle extracted from MuseScore Studio 4.7.4's MIDI export (no `.mid` committed). `<ending>` semantics come from the MusicXML 4.0 reference first; MuseScore is behavioural evidence only.

| Fixtures | What they show |
|---|---|
| `v01`, `v01b`, `v10` | Standard `\|: A B [1 C :\| [2 D \| E` plays A B C A B D E. `stop` versus `discontinue` makes no difference to playback. |
| `v02`, `v03` | An ending spanning two measures (first or second ending). |
| `v04`, `v17` | Comma lists: MuseScore writes `number="1, 2"` and puts `times="3"` on the backward repeat inside that ending. The ending list drives the passes. |
| `v05`, `v05b`, `v06` | Three endings give three passes with no `times` needed. `times` is ignored when endings exist (`v06`: `times="3"` with endings 1 and 2 plays two passes), as the specification says (`times` is for repeats that are not part of an ending). |
| `v07`, `v08` | Endings with no backward repeat: MuseScore plays only A B C and **drops the second ending and everything after it**. |
| `v09a`-`v09g` | Missing, non-numeric, `0`, range `1-2`, spaces and leading-zero numbers: MuseScore ignores the ending marks (plays the ending measure on every pass) except `01`, which it reads as 1, and `3`, where it drops music after the repeat. The specification pattern allows neither ranges nor leading zeros. |
| `v11`, `v12` | An ending start with no stop is tolerated; a stop with no start is ignored. |
| `v13` | Only a second ending after a plain repeat. |
| `v14`, `v15` | An ending at the end of the score; two consecutive volta groups. |
| `v16` | An ending `start` on the **right** barline of the previous measure: MuseScore attaches it to the measure that contains the barline (the same containing-measure reading as for repeats). |
| `v18`, `v19` | Endings with a bare backward repeat (repeat from the score start); an ending spanning measures. |
| `v20`, `v20b` | Several parts: identical structure, and endings in one part only (MuseScore applies one part's structure to all). |
| `w01`-`w05` | Ties around endings. MuseScore ties only score-adjacent notes: a tie into ending 1 is broken on the pass that skips it (`w01`), a tie from the end of ending 1 into ending 2 is never held and its destination attack is **silently dropped** (`w02`). |
| `x01`, `x02` | Tempo and meter declared inside endings: explicit declarations replay when their measure is played. |
| `y01`, `y02` | Pickups before and inside the repeat. |

**How to read the `endings/` fixtures.** Four things are kept apart: what the MusicXML 4.0 reference says (the authority), whether MuseScore agrees, whether it diverges, and what our supported subset does.

* *Specification-supported and MuseScore agrees; accepted:* `v01`, `v01b`, `v02`, `v03`, `v04`, `v05`, `v05b`, `v10`, `v14`, `v15`, `v18`, `v19`, `v20`, `x01`, `x02`, `y01`, `y02`, `w03`.
* *Spec says `times` is not used with endings; MuseScore ignores it; we reject a contradiction:* `v06`.
* *MuseScore loses or reinterprets music; we reject with a specific error and never emulate:* `v07`, `v08` (drops the rest of the score), `v09a`-`v09g` (malformed, missing, range, zero, leading-zero, spaces numbers; `01` normalised by MuseScore), `v11`, `v12`, `v13`, `v16` (containing-measure placement), `v20b` (one part wins), `w02` (silently drops the destination attack).
* *Outside our supported subset although MuseScore plays it:* `v17` (a lone ending carrying its own backward repeat).
* *Ties across skipped endings; MuseScore ties only score-adjacent notes, we cut and keep the destination attack:* `w01`, `w02`, `w04`, `w05`.
