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
