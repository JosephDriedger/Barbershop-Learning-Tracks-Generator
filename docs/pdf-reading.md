# Reading score PDFs

BLT reads a PDF that a notation program wrote **itself, exactly**, with no optical recognition and no
program to install (`src/barbershop_tracks/core/pdfscore`). A scanned PDF or a photo still goes to
Audiveris, with the person's consent (`core/musicxml/convert.py`).

## Why it can be exact

A notation program does not put a picture of the music in its PDF. It draws every notehead, rest,
flag, dot, accidental, clef and time signature as a **character of its music font** at an exact point,
and fonts that follow SMuFL (MuseScore's Leland, Bravura in Dorico and MuseScore, Finale's SMuFL fonts)
give each symbol a fixed code point (U+E0A4 is a black notehead in every one of them). Staff lines,
stems, barlines, ledger lines, hyphens and the underscore lines of held syllables are drawn lines;
beams, ties and slurs are filled shapes; the lyrics and tempo marks are text. Reading those gives
the score as it was written, not a guess at it.

## How it reads

| Step | Module | What it does |
|---|---|---|
| Page drawing | `pdf.py` | A small PDF reader of BLT's own (no dependency): objects, compressed and object streams, the page tree, fonts with their `ToUnicode` maps and widths, form XObjects, and the path and text operators. Out come positioned glyphs, line segments and filled shapes. Encrypted PDFs are refused. |
| Layout | `layout.py` | Staves (five equally spaced lines), systems (staves joined at the left), barlines (thicker than a stem, top line to bottom line), repeat dots. |
| Music | `recognise.py` | Noteheads joined to their stems (a notehead at the root of another stem belongs to that one), lengths from notehead, flags, beams, dots and tuplet numbers, voices (stems up and down where two voices sound together; elsewhere stems follow the pitch, so the rhythm decides), hidden rests (a voice that starts late takes its times from the columns of the voices that fill the measure), pitch from clef, key and the accidentals of the measure (a tie carries its accidental over the barline), ties (a flat curve from one notehead to the next of the same pitch; a slur rises). |
| Slurs | `slurs.py` | Every curve that is not a tie, from the note it starts at to the note it ends at, in the voice it arches over (above the upper voice, below the lower), also over a line break. A note under a slur needs no syllable of its own. |
| Words | `lyrics.py` | Rows of text matched to notes: a syllable is centred on its note, or starts at it when it is held; each syllable is a text of its own in the PDF (when a program writes whole lines as one text, letters of one syllable touch exactly and two syllables side by side do not); a drawn hyphen joins syllables of a word; rows between two staves go to the staff they stack under. Verse numbers per measure, nearest the staff first. |
| Marks | `directions.py`, `endings.py` | Metronome marks, "a tempo", `rit.` and its dashed line, words, fermatas, first and second endings. |
| Whole score | `score.py` | Systems in order, measure numbers as printed, time and key signatures (a system with no key signature is in C), underscore-line lengths (also over line breaks), title and part names. |
| MusicXML | `writer.py` | The result in the shape MuseScore's own export has (voices 1 and 2 per staff, the written pitch with the octave clef, a pickup as measure 0), so BLT reads it like any MusicXML. |

The lengths of the held syllables go to BLT the way a MuseScore project gives them
(`lyric_lines.py`), and the tempo of fermatas and `rit.` lines is worked out by MuseScore's rules
(`core/musicxml/marked_playback.py`), so a song sounds the same from its project, its MusicXML and
its PDF.

## How it was tested

`tests/unit/core/pdfscore` reads PDFs that MuseScore made from BLT's own fixtures (octave clef, four
staves, pickup, ties, triplet, repeats, first and second endings, D.C., lyrics with an elision and two
verses) and requires the same reading as the MusicXML they came from.

`tests/integration/test_pdf_corpus.py` does the same for a folder of real songs (set
`BLT_PDF_CORPUS`; each song as `.mscz`, and the `.pdf` and `.musicxml` MuseScore exported from it). On
five four-part barbershop arrangements (two staves, two voices each, words above and below, key and
time changes, ritardandos, fermatas):

| Song | Notes | Words | Held syllables | Tempo | The 13 tracks from PDF = from project |
|---|---|---|---|---|---|
| Ebb Tide | 382/382 | 102/102 | same | differs at one `rit.` (its line was dragged in MuseScore) | no (that `rit.`; the MusicXML gives the same tracks) |
| I'll Take You Home Again Kathleen | 479/479 | 141/141 | same | same | yes, every WAV byte for byte |
| San Francisco Bay Blues | 1149/1149 | 288/288 | same | same | yes, every WAV byte for byte |
| What Child Is This | 700/700 | 321/321 | same | same | yes, every WAV byte for byte |
| When She Loved Me | 869/873 | 240/254 | differs | same | (not exportable from any of the three: the score is not ready) |

All five songs were also exported in nine other engraving styles: the Bravura and the
hand-written Petaluma music fonts, Bravura with tight spacing, A4 paper with larger staves, landscape
paper, very large staves (many more line breaks), very small staves with crushed spacing, small staves
with tight spacing, and the words in Times New Roman or in a larger Arial instead of MuseScore's
Edwin. All 41 PDFs read as the project does (notes, ties, slurs, words, held syllables, tempo; Ebb
Tide's dragged `rit.` and When She Loved Me's hand-made changes apart), and BLT's quartet MIDI from
each of the 27 of Kathleen, San Francisco Bay Blues and What Child Is This is byte for byte the one
from the project. Run them again with `BLT_PDF_CORPUS` and `variants/<style>/` subfolders. What the styles
taught the reader: Bravura and Petaluma draw noteheads with their own code points (U+F4BC to
U+F4BE); a program writes each syllable as a text of its own, which says where syllables part even
when tight spacing makes them touch, and a title or credit as one text of several words; a font's ties
lie at their own distance from the notes, so the reader measures it over the whole score; a line
that ends with a courtesy key or time signature has its music end before the staff does; a held
syllable can run to the page margin, so a credit is known by being one text of several words; a
row of words midway between two staves goes to the side whose voice sings the most words.

When She Loved Me is the case a PDF cannot settle: words below the staff that MuseScore keeps on the
tenor where tenor and lead move together (drawn exactly as the lead's would be), a duplicated text
above the staff kept as the lead's second verse, and four measures where the tenor's and lead's
stems were turned by hand.

## What a PDF cannot show

A PDF shows the music as drawn. These are not drawn, so they are not read, and nothing is invented
for them: who owns a word that two voices could sing at that note; voice numbers swapped by hand;
the play count of a repeat ("x3"); a hidden tempo; an instrument's transposition; a `rit.` line made
longer or shorter by hand; a fermata's or a ritardando's non-default strength. Sibelius's Opus and
staves hidden where empty are refused with a message.

## Finale's Maestro, and PDFs printed through Microsoft Print to PDF

Finale's Maestro (and Petrucci, Engraver, Jazz, Broadway Copyist) is older than SMuFL: its symbols sit
on ordinary character codes (the black notehead is 0xCF, the sharp `#`). `legacy_fonts.py` turns each
into its SMuFL character, so the rest of the reader is unchanged. A PDF printed through Microsoft
Print to PDF renames every font (`CIDFont+F1`) and moves the codes to U+F020-U+F0FF; the font is then
known by what it draws (nearly all of it in that range, with noteheads). Such a printer also hides what
the font names said and joins texts, so for a renamed font: a small digit (under two staff spaces) is
read as an italic tuplet number, standing over its bracket or, with no bracket or beam, over the middle
of its notes; the words are split into syllables by their spacing, not by the texts that wrote them; a
row of capitals (`INTRO`, `VERSE 1`) is a section's name, not words. Finale draws barlines as thin as
stems: a line from the bottom to the top line of a staff with no notehead at either end is one. A duplet
of quarters is two in the time of three eighths in Finale, so a `2` is read that way when only that fills
the bar (MusicXML `normal-type`).

## Fixing what was read

What the PDF does not settle (a word two voices could sing, a note with no word under it, a missing
tempo) is corrected in MuseScore, never guessed. *Open Score to Fix* in the window (or
`barbershop-tracks fix SCORE`) writes what BLT read as `Name (from PDF).musicxml` beside the PDF, opens
it in MuseScore with the PDF to compare, and watches for the corrected score being saved (beside the
copy, or in MuseScore's Scores folder; a `.mscz` first). The window then offers to use it, and the
learning tracks are made from the corrected music (`core/musicxml/fixing.py`).
