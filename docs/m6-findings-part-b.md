# M6 Part B findings: MIDI lyric import into OpenUtau

Tested: OpenUtau `0.1.565+a60ca5830b9064556157245d4bf8f5920d93e5f8` on Windows 11, each experimental
MIDI opened with `File > Open`, no singer selected. The inputs are experimental probes written with
`mido` (a lyric meta event at the note's own tick, placed before its note-on); they are **not** BLT
output, and BLT does not emit lyric events today. Evidence: the `lyric` of every note in the project
OpenUtau saved, compared with the strings sent (`tests/fixtures/openutau/observations/B*.json`).
All statements are about that version; they concern **import**, not synthesis.

| Experiment | Classification | Sent → imported |
|---|---|---|
| B01 syllables | MATCH | words, punctuation and a repeated syllable kept literally (repeats are not merged) |
| B02 missing lyric | WORKFLOW_REQUIREMENT | a note with no lyric event becomes `a`, even between lyric-bearing notes |
| B03 `+` | MATCH | `la + +` kept |
| B04 `+~` | MATCH | `la +~ +~` kept |
| B05 melisma, `+` / `+~` / mixed | MATCH | kept literally; `+` and `+~` stay distinct strings |
| B05 melisma, `-` | BENIGN_DIFFERENCE | a lyric that is exactly `-` becomes `+` (not `+~`) |
| B06 pitch continuation | MATCH | tokens unchanged after the same, changed and repeated adjacent pitches |
| B07 four tracks | MATCH | lyrics stay on the track that carried them |
| B08 one source track | WORKFLOW_REQUIREMENT | no propagation: the other tracks' notes all become `a` |
| B09 text | MATCH | apostrophe, trailing hyphen, comma, period, `?` and `!` kept |

## What is established (for the tested version)

- A lyric event at a note's tick attaches to that note, and positions and pitches are unchanged.
- Strings are preserved literally except a lyric that is exactly `-`, which becomes `+`.
- A missing lyric event is not "empty": OpenUtau substitutes its default `a`. The `a` is OpenUtau's,
  never an intentional BLT lyric.
- Lyrics are track-local. OpenUtau never copies them between voices.
- `+` and `+~` import as different strings. **This says nothing about whether they behave the same
  when synthesised**; they must not be treated as equivalent.

## Implications for a future policy (not implemented)

For an OpenUtau-specific preparation step: send an explicit lyric event for every sounding note on its
own track; use `+` or `+~` literally (never `-`), chosen only after a synthesis test; decide lyric
propagation to harmony voices in BLT (M3 analysis), not in OpenUtau; keep text ASCII-simple until
non-ASCII is tested. Whether this belongs in the generic MIDI export or in an engine-specific backend
is an architecture decision.

## UNKNOWN

The synthesis meaning of `+` versus `+~`; whether synthesis differs by pitch movement; non-ASCII,
empty, whitespace-only and bracketed lyrics; and behaviour when the lyric event is not at the same tick
or follows the note-on at that tick (only "lyric before note-on" was tested).
