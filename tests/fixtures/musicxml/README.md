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

Provenance: generated on 2026-10-06 with MuseScore Studio 4.7.4 on Windows. These are
research inputs for the M3 parser, not final test fixtures; M3 will add its own focused ones.
