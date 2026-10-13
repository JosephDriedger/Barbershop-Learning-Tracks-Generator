# M12e: musical acceptance with a real English voicebank

> **Superseded for execution by [acceptance/english-voicebank-acceptance.md](acceptance/english-voicebank-acceptance.md) (M15)**, which a
> tester other than the developer can follow and whose result feeds the release gate. This page keeps the background.

**Status: NOT VERIFIED.** No English-compatible voicebank is installed on the development machine, and
none was downloaded: a voicebank is somebody else's licensed work and is only used here once the user has
legitimately obtained it. The generated sine-wave voicebank of the smoke tests is deliberately *not* used
as a stand-in. Until this protocol has been run and recorded, nothing in this repository claims that BLT
produces intelligible English singing.

What exists today:

* The only voicebank present is **ALYS DB002 FRA** (French, installed by the user; its licences
  `LICENCE.ALYS-1.0` and `CC-BY-NC-SA-4.0` are in its folder). Earlier milestones rendered through the real
  host with it (technical checks: audio is produced, validated, mixed). It is not an English voice and
  it is not used for acceptance.
* The supplementary packaged-build run with it is described in [m12-report.md](m12-report.md); it shows the
  installed program works with a real voicebank, and says nothing about English intelligibility.

## Protocol

Needs: the installed build under test, a voicebank legitimately obtained by the person running this
(record its name, version, author and licence terms; do not commit or redistribute it), a phonemizer that
matches it, and a representative four-part TTBB arrangement exported from MuseScore (do not commit a
copyrighted score; record only its title, source and licence).

Suggested voicebank / phonemizer pairings for English in OpenUtau 0.1.565 (check the voicebank's readme):
ARPAsing-style banks with `OpenUtau.Plugin.Builtin.ArpasingPhonemizer`; X-SAMPA banks with `EnXSampaPhonemizer`; VCCV English banks with
`OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer` (class names checked against the 0.1.565 sources). Arpasing+ and English C+V are not in BLT's build since M15 (docs/g2p-plus-provenance.md); a C+V-only bank cannot be accepted with this release. The renderer is WORLDLINE-R (CLASSIC is rejected by the mix check, see KNOWN-LIMITATIONS); neural
renderers are not part of this build.

Score requirements: all four parts with lyrics under every note (so every voice is rendered), at least one
melisma/slur, at least one section where the parts enter at different times, at least one tempo that is
not the default, ordinary barbershop ranges (Bass low, Tenor high).

Run the GUI path (Start menu, load, assign TTBB, choose the singer, resolve lyrics, generate, open the folder)
and also `blt generate` once with the same inputs, then judge the 13 files by ear:

| # | Criterion | How to judge | Result |
|---|---|---|---|
| 1 | All four voices are present in the Full Quartet track | Listen; soloing each part's file | NOT RUN |
| 2 | Lyrics are intelligible in each part | Read the lyric sheet along with a Solo file per part | NOT RUN |
| 3 | Melismas hold one vowel across the notes, no re-articulated syllables | Listen at the melisma bars | NOT RUN |
| 4 | Pitches are right, including the highest and lowest notes | Compare with the score (a keyboard or tuner) | NOT RUN |
| 5 | Entrances and releases fall on the same beat in all parts; no drift over the whole song | Line up the four Solo files in an editor | NOT RUN |
| 6 | Predominant tracks: the focus part is clearly audible and the other parts are quiet but present | Listen to each Predominant | NOT RUN |
| 7 | "Without" tracks omit exactly one voice (the one named) | Listen; compare with the Full Quartet | NOT RUN |
| 8 | WAV files play in a normal player; MP3 (with an FFmpeg you installed) plays and matches the WAV | Open each in two players | NOT RUN |
| 9 | `manifest.json` lists 13 tracks, hashes match | `blt` writes them; spot-check one SHA-256 | NOT RUN |

## Record to keep with the result

Fill in and store beside the output (not in the repository):

```
Date / tester:
BLT version and installer SHA-256:
Windows version:
Voicebank: name, version, author, licence terms, where obtained:
Phonemizer:                 Renderer:                 (Advanced settings or config)
Score: title, source, licence; tempo; number of measures; melismas present:
Mix settings: gain preset, format (WAV/MP3), FFmpeg version if MP3:
Observations per criterion above; defects (with the bar numbers):
Verdict: accepted / accepted with known issues / rejected
```

Known open questions this protocol must answer, because the synthetic bank cannot: how well the default
phonemizer handles English consonant clusters with the chosen bank; whether the default renderer sounds
good enough for the bank; whether the predominant gain preset gives enough clarity for a learner; whether
note-length handling at fast tempi is acceptable.
