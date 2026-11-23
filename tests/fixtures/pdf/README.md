# Score PDF fixtures

PDFs that MuseScore Studio 4.7.5 exported (File > Export > PDF, default style) from BLT's own
hand-written fixtures, so the PDF reader can be checked against the MusicXML each was made from:

| PDF | Made from |
|---|---|
| `e1_tenor_clef8vb_pitch_oct4.pdf`, `e3b_four_parts.pdf`, `e4_forward_gap.pdf`, `e5_pickup.pdf`, `e6_ties.pdf`, `e7_triplet.pdf`, `e8_simple_repeat.pdf`, `e9_volta.pdf`, `e10_lyrics.pdf`, `e11_dacapo.pdf`, `e12_volta_1_2_3.pdf` | `../musicxml/inputs/` (same name) |
| `english-quartet-known-words.pdf` | `../../../docs/acceptance/fixtures/english-quartet-known-words.musicxml` |

No copyrighted music: the scores are BLT's own tiny tests. The fonts embedded in the PDFs are
MuseScore's Leland, LelandText, Edwin and BravuraText (subsets), all under the SIL Open Font
Licence 1.1, which allows them to be embedded in documents and passed on with them.

`e8b_repeat_times3` is not here on purpose: MuseScore does not print a repeat's play count, so the
PDF cannot say it (a documented limit of reading PDFs).
