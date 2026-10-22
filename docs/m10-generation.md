# M10: generating the learning tracks (`barbershop-tracks generate`)

One command takes a MusicXML score to the 13 learning tracks without opening OpenUtau, MuseScore
or a DAW. It connects the existing modules; nothing is re-implemented.

```
MusicXML -> parse (M2/M3) -> readiness (M4) -> SynthesisPlan (M7b) -> USTX check ->
voicebank check -> render host: four stems (M8) -> validate stems (M8c) ->
mix 13 tracks + optional MP3 (M9) -> verify -> publish
```

## Quick start

Install a voicebank in OpenUtau's `Singers` folder (BLT never ships or copies one), find the lines
in your score, and generate:

```powershell
# PowerShell
barbershop-tracks config                          # what BLT found: singers, host, FFmpeg
barbershop-tracks lines "C:\Scores\song.musicxml" # the source lines and their ids
barbershop-tracks generate "C:\Scores\song.musicxml" `
    --out "C:\Tracks" `
    --assign TENOR=P1/s1/v1 --assign LEAD=P2/s1/v1 `
    --assign BARITONE=P3/s1/v1 --assign BASS=P4/s1/v1 `
    --singer my-singer
```

```bat
:: Command Prompt
barbershop-tracks generate "C:\Scores\song.musicxml" --out "C:\Tracks" ^
    --assign TENOR=P1/s1/v1 --assign LEAD=P2/s1/v1 ^
    --assign BARITONE=P3/s1/v1 --assign BASS=P4/s1/v1 ^
    --singer my-singer --audio-format both --ffmpeg "C:\Tools\ffmpeg\bin\ffmpeg.exe"
```

The result is `C:\Tracks\song_learning_tracks\`.

## Options

| Option | Meaning |
|---|---|
| `SCORE` | `.musicxml`, `.xml` or `.mxl` |
| `--out DIR` | the folder that will contain the package folder (or `output_dir` / `BLT_OUTPUT_DIR`) |
| `--assign ROLE=LINE` | all four voices, explicitly; `lines` lists the ids. Never guessed |
| `--ignore LINE`, `--verse V` | as in `check` |
| `--singer [ROLE=]ID` | the voicebank (required; per voice with `ROLE=ID`). Never chosen for you |
| `--phonemizer`, `--renderer` | default `OpenUtau.Core.DefaultPhonemizer` and `WORLDLINE-R` |
| `--audio-format wav\|mp3\|both` | default `wav`; MP3 needs FFmpeg |
| `--mp3-quality N` | LAME VBR quality 0 to 9 (default 2) |
| `--gain-profile NAME` / `--gain-profile-file F` | preset (`default`, `strong-focus`, `gentle-focus`) or a JSON file with `name` and any of `full_quartet`, `predominant_focus`, `predominant_others`, `solo`, `without_each` |
| `--name N` | package name (default: the score's file name) |
| `--replace` | replace a previous package, only if it is one of ours |
| `--approve-lyrics F`, `--review-report F` | lyric review (below) |
| `--keep-stems`, `--keep-project` | also publish `stems/*.wav` and `project/project.ustx` |
| `--timeout S` | render time limit in seconds (default 900) |
| `--progress text\|json\|none` | human progress on stderr (default), JSON lines on stdout, or nothing |
| `--singers-dir`, `--host-dir`, `--dotnet-root`, `--ffmpeg`, `--data-dir`, `--config` | configuration (below) |

## Exit codes and error categories

| Exit | Category | Meaning |
|---|---|---|
| 0 | | the package was published |
| 1 | `source` | the score or the voice mapping is not ready (the findings are listed) |
| 2 | `configuration` | invocation, config, singers, host, FFmpeg, output location |
| 3 | `synthesis` | the render host failed |
| 4 | `audio` | stems did not validate, or mixing/encoding failed |
| 5 | `timeout` | a time limit was exceeded |
| 6 | `review` | lyrics need an explicit decision (report written) |
| 130 | `cancelled` | Ctrl+C or Ctrl+Break; nothing was published |

Errors print `error[CODE] (category): message` (JSON mode: an `error` event). Codes come from the
pipeline (`SOURCE_NOT_READY`, `LYRICS_NEED_REVIEW`, `SINGER_NOT_CHOSEN`, `SINGER_NOT_FOUND`,
`SINGERS_DIR_MISSING`, `HOST_NOT_FOUND`, `FFMPEG_NOT_CONFIGURED`, `OUTPUT_EXISTS`, `OUTPUT_FOREIGN`,
`NO_VOICE_MAPPING`, `NO_OUTPUT`, `BAD_ASSIGN`, `CONFIG_*`, `APPROVALS_*`, `GAIN_PROFILE_*`,
`STAGING_UNAVAILABLE`, `CANCELLED`) and are passed through from the layers below (`PLAN_*`,
`USTX_*`, `HOST_*`, `STEM_*`, `MIX_*`, `PUBLISH_*`; see `m7b-design.md`, `m8-rendering.md`,
`m9-mixing.md`). Missing tempo or meter (`TEMPO_*`, `TIME_SIGNATURE_MISSING`) is a source error: BLT
never assumes a tempo or a 4/4.

## Lyrics that need review

### Parts follow the Lead (default)

Barbershop scores usually write the words once, under the Lead; the other parts sing them unless they
are written separately. So a note of Tenor, Baritone or Bass that the score leaves **without any
lyric** takes what the Lead sings at that moment (`generate --no-follow-lead` or `BLT_FOLLOW_LEAD=0`
turns this off; the GUI has a switch in Advanced settings):

* the Lead must be singing a decided syllable there; if the Lead rests, or has no lyric there itself,
  the note stays a review item;
* a note that starts together with the Lead's syllable sings it; a note that starts while the Lead
  still holds the syllable (the part moves under a held word) **sustains the vowel** (an OpenUtau `+`
  extender) if the part's previous note ends exactly where it starts, and re-sings the syllable after
  a gap;
* a lyric the score gives, a melisma continuation, humming, an elision, a conflict, a proposal and
  any explicit approval are never replaced (an approval overrides the rule for its note).

The plan records each such note as `lead_syllable` / `lead_sustain` with the Lead note it follows; the
GUI lists them in the lyric review as "Follows the Lead", never blocks on them and lets you override any.

### What still needs review

A note without a decided lyric stops the run before anything is rendered: parts whose notes cannot follow the
Lead (the Lead rests or lacks words there), humming, elisions, conflicting verses, or an unapproved
proposal. BLT never substitutes a default syllable.

1. `generate` exits 6, prints which voices and notes are affected, and writes next to the package
   location: `<name>_learning_tracks.lyric-review.json` (schema `blt.lyric-review/1`) and
   `<name>_learning_tracks.lyric-review.approvals-template.json` (`blt.lyric-approvals/1`). Use
   `--review-report FILE` to choose the location. Files that are not ours are never overwritten.
2. Each review item has `voice`, `note_index`, `start` and `duration` (quarter notes, exact
   fractions), `midi_pitch`, `reason` (`lyric_absent`, `lyric_conflict`, `lyric_unsupported_source`,
   `lyric_proposal_unapproved`), `detail`, and any `proposal`.
3. Fill in `text` and `approved_by` for each note of the template and rerun with
   `--approve-lyrics FILE`. A template line left with `"text": null` stays undecided. The file carries
   the score's SHA-256; approvals made for another version of the score are rejected
   (`APPROVALS_WRONG_SCORE`). An approval may only target a note without a score lyric.
4. The text is used verbatim, so it must be an alias the chosen voicebank can sing; BLT cannot judge
   pronunciation. A syllable the voicebank lacks renders as silence and is caught at stem validation.

The PySide6 GUI (M11) will provide the review interface on the same report format.

## Progress events

`--progress json` writes one JSON object per line on stdout (`stage`, `progress`, `host`, `warning`,
then `result` or `error`). Stages, in order: `source_loading`, `score_analysis`,
`readiness_validation`, `ustx_preparation`, `voicebank_discovery`, `stem_rendering`,
`stem_validation`, `mixing`, `mp3_encoding`, `package_publication`. `progress` events carry
`completed`/`total` only where work is really counted (13 mixes, 13 MP3 files); the render host's
phases are reported as `host` events without a percentage. Mixing and MP3 encoding are interleaved
per track, so their stages overlap.

## Configuration

Precedence per setting: command line, then environment, then the config file, then discovery that cannot
be ambiguous. `barbershop-tracks config [--format json]` shows each resolved value and its origin.

| Setting | Option | Environment | Config key | Discovery |
|---|---|---|---|---|
| singers folder | `--singers-dir` | `BLT_SINGERS_DIR` | `singers_dir` | `Documents\OpenUtau\Singers` if it exists |
| render host | `--host-dir` | `BLT_HOST_DIR` | `host_dir` | `host` next to the application, or a source checkout's build |
| .NET runtime | `--dotnet-root` | `DOTNET_ROOT` | `dotnet_root` | the system's |
| FFmpeg | `--ffmpeg` | `BLT_FFMPEG` | `ffmpeg` | `ffmpeg` on `PATH` |
| data folder | `--data-dir` | `BLT_DATA_DIR` | `data_dir` | `%LOCALAPPDATA%\BarbershopLearningTracks` |
| output folder | `--out` | `BLT_OUTPUT_DIR` | `output_dir` | none |
| singer, phonemizer, renderer, gain profile | options above | | `singer`, `phonemizer`, `renderer`, `gain_profile` | phonemizer and renderer have the defaults shown above |

The config file is `%LOCALAPPDATA%\BarbershopLearningTracks\config.json` (or `BLT_CONFIG`), a flat JSON
object of the keys above; an unknown key is an error. The voicebank itself is never discovered: the
singer is named explicitly and checked against the folders under the singers folder (a folder is a
voicebank if it holds `character.txt`, `character.yaml` or `oto.ini`). No voicebank is copied for a
job; the host reads them where they are (`m8-runtime-layout.md`).

## Output package

```
song_learning_tracks\
    01_Full_Quartet.wav            02_Tenor_Predominant.wav ... 05_Bass_Predominant.wav
    06_Tenor_Solo.wav ... 09_Bass_Solo.wav     10_Without_Tenor.wav ... 13_Without_Bass.wav
    (the same names with .mp3 for MP3 output)
    manifest.json                  (schema blt.learning-tracks/1, see m9-mixing.md)
    stems\*.wav, project\project.ustx    only with --keep-stems / --keep-project
```

Nothing else is published: no temporary USTX, render cache or intermediates.

## Transactions, temporary files, cancellation

* Each job has a job-scoped working directory `staging\.staging-job-<id>-<pid>` (the render's own
  staging, the four stems, MP3 intermediates). It is removed on every exit path; a crashed job's
  directory is recognised as stale (pid and process start time) and removed by the next run, never
  while its owner is alive.
* Publication is one rename of a fully verified folder. A failure at any stage leaves an existing
  package exactly as it was; `--replace` only replaces a folder containing our manifest.
* Ctrl+C or Ctrl+Break asks for cancellation once ("cancelling..."); the render host is ended through
  its job object (with everything it started), FFmpeg likewise, staging is removed, exit 130. A second
  Ctrl+C interrupts immediately and the same cleanup runs. Tested with a real console process group.
* Concurrent generations get separate job directories. They take turns at the render host stage (one
  host at a time per data folder) because hosts share OpenUtau's render cache and collided on cache files
  when run together; mixing, encoding and publication still overlap. Waiting is cancellable.

## Memory

Mixing is chunked (see `m9-mixing.md`): memory is bounded by the block size, not the song length
(77 MB peak for an 8 minute score instead of 1.2 GB), with byte-identical output.

## Known limitations

* Windows only. The voicebank must be one OpenUtau 0.1.565 can render with the chosen phonemizer;
  English phonemization quality is outside BLT's control and is not verified.
* A warm render cache changes stems by up to 1 LSB compared with a cold one; outputs are
  byte-identical for equal inputs and equal cache state (tested), not across cache states.
* Per-note lyric silence is detected after rendering, not before: an unsupported alias costs a render.
* The package name is derived from the score's file name unless `--name` is given.
* Not distribution-ready: the dependency licensing audit (`dependency-audit.md`) is incomplete.

## Where the syllables of a long word fall

The English dictionary engines (Arpasing, English VCCV, X-SAMPA) take the whole word on its first note and put
one vowel on each following note that **starts a syllable**, in order. A note whose lyric is `+` starts the next
syllable; a note whose lyric is `+~` only **holds the vowel** of the syllable before it (this is how the pinned
OpenUtau decides: `PhonemeBasedPhonemizer` and `SyllableBasedPhonemizer` skip the notes starting with `+~` or `+*`
when they hand out vowels). BLT writes the notes of an assembled word accordingly: a note that carries a syllable of
the score is `+`, and a note that only continues the syllable before it (a melisma or a slur) is `+~`. So the last
syllable of a word sung over several notes sounds on **the note the score gives it**, normally the last, and the
notes between hold the syllable before. Written `+` on every note, as it was before, the last syllable of
`to-geth-er` with `geth` held over two notes sounded on the second of them, one note early.

### A held word's closing consonant and a short last note

Arpasing puts a word's closing consonants at the very end of the whole group of notes the word is sung over (60 ticks each
before the end, at 480 per quarter). Over a word held on several notes whose last note is short, such as the dotted eighth and
sixteenth of "babe", the closing "b" (its quiet lip closure comes first) then takes about half of the sixteenth, and the new
pitch is hardly heard: measured on a render, the sixteenth was sung at its own pitch for 10 to 50 ms of its 238 ms. For such a
word (Arpasing only, held over two or more notes, last note no longer than a dotted eighth minus a sixteenth, ie 180 ticks,
and followed without a gap) BLT moves the closing consonants 50 ticks later with OpenUtau's per-phoneme `offset`
(`phoneme_overrides`, `tails.py`), as late as the engine allows, and gives a held note of a sixteenth or less a 15 ms pitch
transition instead of 40 ms each side of its start, so a semitone step is a step. This needs the word's phonemes, which the
render backend asks the host's dictionary for (only for those words); a word the dictionary lacks, any other engine, a word
on one note and the last word of a voice are left exactly as the engine places them. Measured the same way the sixteenth is
now sung at its own pitch for 80 to 90 ms. That is the most these controls give: the voicebank's own closure for the "b"
takes about 0.1 s however late the consonant is put.

Not covered: a whole word typed on one note and slurred over several (no hyphens in the score). The score does not
say where its later syllables go, and BLT would need the word's syllable count from the dictionary to choose; such a
word is still written `word`, `+`, `+`, with the syllables falling on the first notes.
