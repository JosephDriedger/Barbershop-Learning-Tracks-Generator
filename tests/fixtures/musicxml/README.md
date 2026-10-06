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
