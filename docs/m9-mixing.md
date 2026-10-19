# M9: the 13-track learning package

Four validated TTBB stems (M8) go in; thirteen synchronized tracks, a manifest and optionally MP3
copies come out. Nothing is re-rendered: each voice is synthesised once and reused by every mix.
The mixer (`core/mixing/`) knows nothing about OpenUtau. FFmpeg is needed only for MP3 and is never
bundled.

## Modules

```
core/mixing/
  specs.py     GainProfile (the only place gains are chosen), MixSpec, standard_mix_specs()
  timeline.py  exact seconds from the tempo map; duration_frames()
  audio.py     load_stem, fit_stem (pad / trim), mix_float, quantize, wav_bytes
  package.py   build_learning_tracks(): the transaction, the manifest, verification
  mp3.py       FfmpegMp3Encoder, inspect_mp3, find_ffmpeg
  errors.py    MixError and its subclasses
```

## The mix matrix and default gains

Gains are linear (1.0 leaves a stem unchanged) and always listed per voice in the order Tenor, Lead,
Baritone, Bass. They come from `GainProfile` (`DEFAULT_PROFILE`); nothing else contains a gain.

| # | Identifier | File | Tenor | Lead | Baritone | Bass |
|---|---|---|---|---|---|---|
| 1 | `full_quartet` | `01_Full_Quartet` | 0.25 | 0.25 | 0.25 | 0.25 |
| 2 | `tenor_predominant` | `02_Tenor_Predominant` | 0.50 | 0.15 | 0.15 | 0.15 |
| 3 | `lead_predominant` | `03_Lead_Predominant` | 0.15 | 0.50 | 0.15 | 0.15 |
| 4 | `baritone_predominant` | `04_Baritone_Predominant` | 0.15 | 0.15 | 0.50 | 0.15 |
| 5 | `bass_predominant` | `05_Bass_Predominant` | 0.15 | 0.15 | 0.15 | 0.50 |
| 6 to 9 | `tenor_solo` … `bass_solo` | `06_Tenor_Solo` … `09_Bass_Solo` | 0.5 for the one voice, 0 for the others | | | |
| 10 to 13 | `without_tenor` … `without_bass` | `10_Without_Tenor` … `13_Without_Bass` | 0.33 for each remaining voice, 0 for the muted one | | | |

Filenames are `NN_Label_With_Underscores.wav` / `.mp3`; the order and numbers never change.

Rationale (conservative, clipping-averse):

* **Headroom.** Every default mix's gains sum to at most 1.0 (full quartet 1.00, predominant 0.95,
  without 0.99, solo 0.5). Stems are at most full scale, so no default mix can exceed full scale, whatever
  the stems contain. Tested with full-scale stems.
* **Predominant** is 3.3 times (10.4 dB) louder for the focus voice than for each other voice, enough to
  follow a part while still hearing the chord.
* **Solo at 0.5** equals the focus voice in a predominant mix, so a voice is about equally loud in
  those two tracks. It leaves 6 dB of headroom.
* **Without 0.33 each** keeps three voices at roughly the level the quartet gives each of four plus 2.4 dB, so
  removing a voice does not make the track much quieter.
* **No loudness normalisation** is applied anywhere. Loudness therefore follows the stems and the
  gains; a quiet voicebank gives a quiet package. Normalisation would need to be added explicitly and tested.

A profile (or a hand-built `MixSpec`) may use any gains from 0 to 4; a mix that would exceed full scale
raises `MixClippingError`. Profile validation: finite, in range, focus above others (and above zero).

## Alignment and duration

* The package length is derived from the score: the exact performed length (quarter notes) through
  the exact tempo map (`Fraction` BPM) gives exact seconds; **frames = ceil(seconds x 44100)**.
  Rounding up never cuts performed time and overshoots by less than one frame (23 microseconds).
  Never from the longest stem (tested: 4.8 s of package from sub-2.4 s stems at 50 BPM).
* Every stem is placed at frame 0 and padded with exact zeros at its end up to that length. Nothing is
  shifted: leading silence, late entrances and the roughly 50 ms preutterance before a note
  (M8 measurement) are preserved sample for sample (tested).
* A stem longer than the target raises `MixDurationError` unless the excess is both short (at most
  0.05 s) and nearly silent (peak at most -60 dBFS); then it is trimmed and the manifest records
  `trimmed_frames`. Both limits are in `TailPolicy`.
* All 13 WAVs have the same frame count; this is verified after writing and again by re-reading.

## Audio processing and quantisation

* Input: 44.1 kHz, 16-bit PCM, mono WAV, as M8 validates. Anything else is a `MixInputError`.
* Samples are decoded as `int16 / 32768` into float64; the weighted sum is accumulated in float64 in
  fixed voice order. There is exactly one quantisation, at the end.
* **Quantisation:** `rint(x * 32768)` (round half to even), no dither, so output is deterministic.
* **Clipping:** a quantised value outside -32768..32767 (including a float of exactly +1.0) is
  `MixClippingError`, naming the mix, the peak and the first frame. Nothing is ever clamped.
* WAV files are canonical 44-byte-header PCM; the same input gives the same bytes (tested).

## MP3

* FFmpeg is an external, configurable command (`FfmpegMp3Encoder([path])`; `find_ffmpeg()` checks an
  explicit path, `BLT_FFMPEG`, then `PATH`). It is probed on construction (`-version`, `libmp3lame`).
* Settings: `libmp3lame`, VBR quality 2 (about 190 kbit/s), mono, 44.1 kHz, metadata stripped, ID3v2
  off, bit-exact flags. Quality is configurable (0 to 9). The same name, with `.mp3`.
* **Not sample-exact.** MP3 adds encoder delay and pads to a 1152-sample frame; a player that ignores
  gapless information will start the audio late. The WAV is the timing reference. The manifest records
  the difference between the decoded length and the WAV (`decoded_minus_wav_samples`).
* Validation of every MP3 before publication: a Python frame walk (MPEG-1 Layer III, 44.1 kHz, mono, valid
  headers, frames exactly filling the file, ID3 tags tolerated), length within 3 frames (3456 samples) of
  the WAV, and a full FFmpeg decode that must succeed without any message and land within the same tolerance.
  The encoder has a timeout; cancellation ends the FFmpeg process tree.
* Output choices: WAV only, MP3 only (the WAVs live only in staging) or both.

## Publication and rollback

`build_learning_tracks(source, stems, destination, settings, cancel=, on_progress=, replace=)`:

1. Check formats, encoder, stems and destination; compute the length; load and place the stems.
2. Staging in `staging/.staging-<job>-<pid>` (the M8 infrastructure, with pid-reuse-safe ownership).
3. Mix and write 13 tracks (and MP3s); cancellation is checked between tracks and ends FFmpeg.
4. Verify: the directory holds exactly the expected files, every WAV re-reads as 44.1 kHz/16-bit/mono with
   the common frame count, nothing is empty; write `manifest.json`.
5. Publish with one rename. A failure, cancellation or invalid file anywhere discards staging.

An existing destination is an error (`PUBLISH_DESTINATION_EXISTS`) unless `replace=True`, and
replacement is only allowed for a folder that contains one of our manifests (`MIX_DESTINATION_FOREIGN`
otherwise), so an unrelated folder is never touched. A failed replacement keeps the previous package.
Two concurrent jobs for one destination publish exactly one.

## Manifest (`manifest.json`, schema `blt.learning-tracks/1`)

Sorted keys, no timestamps, no absolute paths (tested), so equal inputs give an equal manifest.

```
schema, generator{name,version}
source{display_name, sha256, title}
audio{sample_rate, bit_depth, channels, frames, duration_exact_seconds ("12/5"), duration_seconds}
settings{gain_profile{name, full_quartet, predominant_focus, predominant_others, solo, without_each},
         formats[], duration_policy, quantization, normalization, tail_policy{...}, mp3{...}|null}
stems[]{voice, sha256, frames, padded_frames, trimmed_frames}
tracks[]{id, number, label, kind, focus, voices[], gains{tenor,lead,baritone,bass},
         worst_case_gain_sum, peak,
         files[]{format, name, bytes, sha256, sample_rate, channels,
                 wav: bit_depth, frames | mp3: mp3_audio_frames, average_kbps, decoded_samples,
                 decoded_minus_wav_samples}}
```

## Errors

`MixConfigurationError` (profile, formats, encoder, FFmpeg, destination, staging), `MixInputError`
(missing, malformed, wrong-format or empty stems), `MixDurationError`, `MixClippingError`,
`MixEncodingError` (launch, failure, timeout, invalid or wrongly sized MP3), `MixOutputError` (a produced
file failed verification), `MixCancelledError`. Each has `.code`, `.message`, `.details`.

## Performance and memory (this machine, synthetic stems, WAV only)

Since M10 the mixer streams (`streaming.py`): each mix is produced in blocks of 262144 frames
(about 6 s), reading the stems it needs from disk for that block. Output is **bit-for-bit
identical** to the whole-array implementation (`audio.py`, kept as the reference; compared by SHA-256
over all 13 files at 30 s, 3 min and 8 min, and by unit tests at block sizes from 1 frame up).

| Score | Whole-array (M9) time / peak memory | Streaming (M10) time / peak memory |
|---|---|---|
| 30 s | 0.27 s / 113 MB | 0.42 s / 44 MB |
| 3 min | 1.6 s / 491 MB | 2.4 s / 52 MB |
| 8 min | 4.5 s / 1248 MB | 6.6 s / 77 MB |

Memory no longer grows with the song (a tracemalloc test shows the same peak for 20 s and 10 minutes);
the figures include roughly 40 MB of the measuring script's own hashing of the output. Cost: about
1.5 times the time, because each mix re-reads and decodes the stems it needs. Clipping is still
checked over the whole mix and reports the global peak, count and first frame; cancellation is
checked every block. MP3 time depends on FFmpeg and was not measured here.

## Tests

`tests/unit/core/mixing/` (specs, timeline and rounding, audio, package transaction, MP3 with a fake
FFmpeg): identities, voice inclusion, gain relationships, common frame counts, leading silence, late
entrances, short stems, early preutterance, clipping and overflow, quantisation, missing/malformed/
incompatible stems, name collisions, encoder failure, cancellation, concurrency, rollback, repeatable
bytes. `tests/integration/test_mixing_pipeline.py` renders four stems with the real host and the
generated voicebank, deletes the host runtime, and builds the 13-track package from the stems alone;
its MP3 test uses a real FFmpeg when one is available (CI installs one).

## Tune-up note and count-in (optional)

Two options put audio before the music of **every** track (`--tune-up`, `--count-in`; two checkboxes in the app). They are
off by default, and the music itself is never changed: it only starts later, and `manifest.json` says where
(`audio.music_starts_at_frame`, with the details in `audio.prelude`). `audio.frames` is the whole file;
`audio.duration_exact_seconds` is still the music's own length.

* **Tune-up note**: three seconds of a plain sine tone at the tonic of the score's **first** key signature (major keys,
  minor keys and the church modes are understood; the mode defaults to major), in the octave nearest the Lead's first note,
  followed by one second of silence. A score with no key signature (or one in a mode with no tonic) is refused before any
  singing is rendered: BLT does not guess a key.
* **Count-in**: one bar of metronome clicks (not spoken numbers), the first one higher, at the score's first tempo and
  time signature, one click per notated beat (6/8 gives six clicks). The music starts one beat after the last click. It is
  not repeated during the song.

## Known limitations

* Mono output only (the stems are mono); no panning, reverb, EQ or loudness matching.
* Disk space: 13 WAVs of 16-bit mono 44.1 kHz audio (about 5 MB per minute each) in staging and in the package.
* MP3 timing is approximate by nature; MP3 validation assumes MPEG-1 Layer III mono from `libmp3lame`.
* Real-FFmpeg behaviour was verified only where an FFmpeg was available (see CI), not on every build.
* The tail policy trims at most 0.05 s of near-silence. Measured with the real host (generated
  voicebank and ALYS): a stem that fills the whole score is exactly one frame longer than the exact
  duration, which the policy trims (the manifest records `trimmed_frames: 1`). A longer or louder
  release tail will be refused until the policy is widened deliberately.
* Licensing: numpy (BSD-3-Clause) is a new runtime dependency; FFmpeg's licence depends on the build and is
  UNKNOWN until M12. See `docs/dependency-audit.md`.
