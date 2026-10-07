# M5 plan: deterministic MIDI handoff

Status: **approved architecture (review 1 incorporated).** M5a is implemented first, then M5b;
each stops before commit for review. M5 does **not** automate OpenUtau: v1 stays semi-automatic
(`docs/openutau-integration.md`): we write a handoff package, the user imports the MIDI into
OpenUtau, renders stems, and M6 ingests them.

## 1. Scope and non-goals

In: performed score → exact tick conversion → four-track format 1 MIDI → manifest →
transactional package on disk → `export` CLI → manual-step instructions.

Out: OpenUtau automation, MIDI lyric events and every OpenUtau-specific lyric form (`+`, `+~`,
syllable transformation, phonemizer behavior), lyric propagation to harmony voices, dynamics,
program changes, audio, FFmpeg, UI. The core stays GUI-free.

Three names stay conceptually separate: the **capability** (`MIDI_QUARTET`: can this performed score
be exported as the quartet MIDI handoff), the **backend** (OpenUtau, M6) and the **package format**
(`barbershop-tracks.handoff/1`).

## 2. Architecture

```
core/midi/      (M5a)  pure, in memory: ticks, tempo, meter, plan, build, encode, read-back verify
core/handoff/   (M5b)  manifest, layout/naming, package verifier, transactional writer
cli.py          (M5b)  `export` subcommand
```

M5a knows nothing about file names, directories or the filesystem. Its result is an immutable
`MidiExport`: PPQ, the deterministic event representation (`MidiPlan`), the encoded bytes, the
export warnings and the per-event tempo/meter records M5b needs for the manifest.

The exporter consumes a `PerformedSong` and `RoleAssignments`, never a `Song` directly. Two layers:

1. **Readiness** (M5b CLI/pipeline): `assess_readiness(parsed, assignments, MIDI_QUARTET)` must be
   ready or no package is produced. `MIDI_QUARTET` is a public capability requiring TENOR, LEAD,
   BARITONE and BASS, all musical lines accounted for, assigned lines sound, monophony, integral
   MIDI pitch, the MIDI range, tempo at position zero and **no lyrics** (`LyricPolicy.NONE`; it
   does not inherit any vocal lyric requirement). It is the test-only `QUARTET_STRUCTURE` promoted
   (CLI target `quartet-midi`, fitting the existing `--target` syntax).
2. **Defensive exporter checks (M5a)**: the exporter independently rejects input that would corrupt
   or misrepresent the file. It does not re-run the M4 framework; it checks the invariants the
   serializer itself relies on:
   - the four roles resolve to four distinct present lines;
   - each voice is monophonic (no overlap, no chord, no zero/negative duration);
   - integral MIDI pitch within 0..127, from the performed **sounding** pitch;
   - exact tick representability of every timing-relevant position (§3);
   - valid PPQ (§3) and valid tempo encoding (§6);
   - non-negative, in-range deltas; no event after the song end;
   - tempo present at position zero.

Errors are typed (`MidiExportError` with a stable `code`), raised before any byte is produced.

## 3. Exact timing and PPQ

- Every position/duration is a quarter-note `Fraction`. `ticks = position * ppq` must be an `int`.
  Otherwise export fails with `MIDI_TICK_NOT_INTEGRAL`, naming the event kind, the performed
  position and the PPQ. **Never rounded.** This applies to **all** timing-relevant positions: note
  starts, note ends, tempo events, meter events and the final end-of-track position (the performed
  song end). All are checked before writing.
- **PPQ** is a configured *ticks-per-quarter* division, default **480** (the selected v1 handoff
  resolution). It must be an `int` (not `bool`) in `1..32767`: the SMF division field is 16 bits and
  a set top bit selects SMPTE time code, so metrical PPQ is 15 bits. SMPTE division is not supported.
  Anything else is `MIDI_PPQ_INVALID`.
- **No automatic PPQ selection** in M5. Exactness is guaranteed *in the MIDI file itself*.
- **OpenUtau's import grid is not asserted.** The idea that OpenUtau rescales to a 480 grid and
  rounds comes from reading its source and is **not verified by an import experiment**, so no M5
  correctness depends on it and the manifest does **not** expose `openutau_grid_exact`. M6 hands-on
  work decides whether import adds another representability constraint.
- Tick conversion lives in one function (`to_ticks`); nothing else multiplies.

## 4. MIDI structure (deterministic bytes)

- **Format 1**, PPQ division, **five tracks**: track 0 conductor, then fixed order Tenor, Lead,
  Baritone, Bass (never source order). Track names are stable ASCII: `Conductor`, `Tenor`, `Lead`,
  `Baritone`, `Bass`.
- Conductor: track name, time-signature and tempo events, end of track, no notes. Voice tracks carry
  track name, notes, end of track only.
- **Channels:** Tenor 0, Lead 1, Baritone 2, Bass 3. An import-time assertion rejects channel 9
  (General MIDI percussion, "channel 10") from the mapping so a later policy change cannot
  accidentally enter percussion semantics.
- **Program changes:** none. The handoff carries pitch and timing, not timbre.
- **Velocity:** one documented constant, note-on **80** for every attack (`NOTE_ON_VELOCITY`). No
  dynamics are inferred from MusicXML. Note-off velocity is the constant **64**.
- **Note-off:** a real `note_off` event; never note-on with velocity 0.
- **End of track:** every track (conductor and all four voices) ends at **exactly the performed song
  end tick**, so a voice may carry trailing silence before its end-of-track, and all five tracks are
  equally long. No event may exceed that tick.
- **Total event priority at one tick** (a fixed sort key; container/input order never decides):

  | priority | event |
  |---|---|
  | 0 | track name |
  | 1 | time signature |
  | 2 | tempo |
  | 3 | note off (ties broken by pitch) |
  | 4 | note on (ties broken by pitch) |
  | 9 | end of track |

  So at a tick where one note ends and the next begins on the same voice, the note-off always
  precedes the note-on (no transient overlap or stuck-note ambiguity), and meta events precede
  notes.
- **Writer:** `mido`, fed absolute-tick events converted to deltas by us. Events are built as
  explicit messages (no library defaults for anything the file contains). Determinism is pinned by
  golden **hex** for tiny files and **SHA-256** for larger cases (no `.mid` committed), plus
  semantic read-back tests so that a changed hash points at which representation changed.

## 5. Note semantics

- Pitch is the performed **sounding** pitch (`PerformanceNote.pitch`, transform applied), never
  written pitch; a test with a transposed line pins this.
- MIDI number from `absolute_semitones` with C4 = 60; non-integral or outside 0..127 is an error.
  Rests emit nothing. A tie-merged attack is one note-on/off pair. Repeats and endings arrive
  already expanded (M3d/M3e): the MIDI is the *performed* timeline.

## 6. Tempo (a different representability problem)

Tick timing must stay exact; tempo **encoding** is inherently approximate: the set-tempo payload is
an integer number of microseconds per quarter note in 24 bits, while MusicXML BPM is an exact
`Fraction`.

- `exact_us = Fraction(60_000_000) / bpm` (exact rational). The encoded value is
  `round(exact_us)` on `Fraction`, i.e. **round half to even**, with no binary floating point
  anywhere in the decision.
- Valid encoded range is `1 .. 16_777_215` (0xFFFFFF), checked by us (not left to mido). Outside it:
  `MIDI_TEMPO_UNREPRESENTABLE`. A non-positive BPM is also rejected defensively
  (`MIDI_TEMPO_INVALID`).
- Per exported tempo event the record holds: exact BPM (string), exact µs/QN (string, a rational),
  encoded integer µs/QN, and the signed error `encoded - exact` in µs/QN (string); optionally the
  derived BPM error `60e6/encoded - bpm` (exact string). The warning `MIDI_TEMPO_QUANTIZED` is
  advisory when the error is non-zero.
- Quantization changes wall-clock time only, never tick positions.
- Only explicit performed tempo events are exported. **No default 120 BPM.** No tempo at position
  zero is an error `MIDI_TEMPO_MISSING`.
- **Same tick:** two tempo events at the same tick with identical encoded value are emitted once
  (deduplicated deterministically, the first by performed order); conflicting values are
  `MIDI_TEMPO_CONFLICT`. Identical tempo at *different* ticks is preserved (explicit declarations,
  e.g. a repeat replaying them).

## 7. Meter

- Export **performed explicit meter events** only (`PerformedSong.meter_events`). Nothing is
  synthesized from `effective_meter_at`. A score with no explicit meter emits no time-signature
  event; the record `METER_NONE_EMITTED` (advisory) says MIDI readers assume 4/4.
- MIDI time-signature: numerator 1..255, denominator a power of two encoded as its exponent. A
  meter MIDI cannot represent exactly (denominator not a power of two or beyond 2^255, numerator out
  of range, composite/additive forms) is **omitted**, never altered to a nearby value: warning
  `MIDI_METER_NOT_REPRESENTABLE`, and the manifest lists it under omitted meters with the reason.
  Meter does not affect note timing, so this does not invalidate `MIDI_QUARTET`.
- **Auxiliary fields** are written explicitly and are *not MusicXML facts*: clocks per metronome
  click = **24**, notated 32nd notes per MIDI quarter = **8**. These are the conventional values
  (`METER_CLICK_CLOCKS`, `METER_32NDS_PER_QUARTER`), identical for every meter, never derived from
  the source and never inherited from a library default; the manifest states this.
- A pickup measure has no MIDI representation; time zero is tick zero. Documented limitation.

## 8. Lyrics

No MIDI lyric events in M5, and none of the OpenUtau-specific forms (`+`, `+~`, syllable
transformation) until M6 pins the real import contract. MusicXML/M3 analysis remains the lyric
authority. The manifest reserves `lyrics` with explicit semantics:
`{"status": "not_exported", "reason": "awaiting OpenUtau lyric-import validation"}`. It must not
imply lyrics were validated for OpenUtau because M4 assessed lyric readiness for another capability.

## 9. Manifest (`barbershop-tracks.handoff/1`)

JSON, UTF-8, fixed key order, exact fractions as strings. **No timestamps, no absolute or temporary
paths.** Contents:

- `schema` (`barbershop-tracks.handoff/1`), `package_type` (`barbershop-tracks.handoff`), `generator`
  {name, version when reliably available}
- `source` {`display_name` (display only, not identity), `sha256` of the source bytes (identity)}
- `midi` {`file`, `sha256`, `bytes`, `format` 1, `ppq`, `tracks` [name, channel]}
- `timing` {`performed_length_quarters`, `end_tick`}
- `roles` [{role, track, channel, line_id, part_name, attacks, lowest_midi, highest_midi}]
- `tempo` {events: [{position, bpm, exact_us_per_quarter, encoded_us_per_quarter, error_us}],
  policy}
- `meter` {written: [...], omitted: [{position, written, reason}], auxiliary_fields_note}
- `lyrics` (§8), `readiness` {capability, counts, finding codes}, `warnings`, `limitations`

## 10. Package layout and transactional writing (M5b)

Package directory `<out>/<name>.handoff/` holding exactly: the deterministic quartet MIDI, the
deterministic manifest, and (only if useful) one short deterministic instructions text. No copy of
the source MusicXML, no voicebanks, no OpenUtau files, no audio.

Names: `--name` or the source stem, sanitized (ASCII letters/digits/`-`/`_`, others to `_`), Windows
reserved device names and trailing dot/space rejected, length-capped; empty result is a usage error.

Sequence: build everything in memory (MIDI bytes, read-back verification, manifest, package
validation) → only then write into a temporary sibling directory on the **same volume** → re-read and
verify from disk → finalize by rename. The final name never exists half-written. On failure the
temporary directory *we created* is removed; nothing else is ever removed.

**Ownership (D8).** An existing destination is refused (`HANDOFF_EXISTS`) unless `--overwrite` and the
directory is positively identified as ours: it holds a manifest that parses, has the expected
`schema`, a supported version and the `package_type`, **and** its contents are exactly the files that
manifest lists (plus the manifest). A directory with no manifest, a malformed manifest, another
application's manifest, an unsupported schema, or extra files is refused; nothing is deleted. We
never `rmtree` arbitrary content: only the known files are removed, then the directory with `rmdir`.
Symlinks and Windows reparse points (junctions) at the destination, the temporary directory or inside
are refused rather than followed.

**Replacement sequence** (never delete-then-rename, which loses the old package on failure):
validated existing package → renamed to a unique backup name → new package renamed into the final
name → backup removed. If finalization fails, the backup is renamed back (rollback) and the new
temporary directory removed. Directory rename is atomic only where the platform guarantees it; on
Windows two renames are not one atomic step, so there is a brief window where neither name exists.
The guarantee we document is "no state in which the final name holds a half-written package, and a
failed replacement restores the previous one", not full atomicity. Bounded retry on transient
`PermissionError` (indexers, antivirus), then a clear error. Stale `.tmp-*`/`.bak-*` directories left
by a hard crash are inert and reported by name, never auto-deleted.

## 11. CLI (M5b)

```
barbershop-tracks export SCORE --assign ROLE=LINE ... --out DIR
    [--ignore LINE]... [--name NAME] [--ppq 480] [--overwrite] [--strict] [--format text|json]
```

Reuses the M4 assignment grammar and parser unchanged (no second grammar), runs `MIDI_QUARTET`
readiness first; not ready means no package. Exit codes keep the `check` meaning (public `check`
codes are unchanged): **0** exported; **1** the score/configuration cannot be exported (readiness
blocking, or exporter errors such as non-integral ticks or tempo out of range; the report/diagnostics
are printed, nothing is written); **2** usage, input, load or filesystem/package failure (destination
exists, not ours, I/O error). The two can be told apart by the printed code and, in JSON, by a
`failure` category. Decision **D9**: an extra exit code 3 for filesystem failures is possible but not
proposed. `--strict` refuses before writing when advisory findings exist. JSON stdout is exactly one
document (machine-clean rule as in `check`).

## 12. Milestones

**M5a: MIDI core (pure, in memory).** MIDI data model, PPQ validation, exact tick conversion,
deterministic ordering, note serialization, tempo conversion, meter representability, byte
encoding, semantic read-back verifier, pure tests. **Stop before commit for review.**

**M5b: package.** `MIDI_QUARTET` public capability, manifest, deterministic layout, package
verifier, transactional writer, conservative overwrite, `export` CLI, integration tests, manual
OpenUtau instructions. **Stop before commit for review.**

Test plan highlights: tick exactness (triplets, quintuplets, a 7-tuplet failing at 480, all event
kinds incl. end tick), PPQ bounds, no rounding, sounding vs written pitch, pitch range/microtonal,
overlap/chord rejection with readiness bypassed, tied and repeated/ending scores, tempo
exact/half-even/out-of-range/duplicate/conflict/missing, meter representable/omitted/none/no
synthesis/auxiliary fields, same-tick ordering, EOT == song end for all five tracks, golden hex and
SHA-256, byte-identical repeated runs, semantic read-back (format, PPQ, five tracks, names, order,
channels, pitches, absolute ticks, tempo, meter, EOT), no lyric events, no program changes.

## 13. Decisions

Approved: D1 no MIDI lyrics, D2 configured PPQ default 480 without auto-selection and without
`openutau_grid_exact`, D3 half-even tempo with recorded error, D4 omit unrepresentable meter, D5
conductor plus four voices (channels 0..3, velocity 80/64, real note-off), D6 public `MIDI_QUARTET`
capability, D7 no timestamps or absolute paths, D8 overwrite only over a positively identified
package. Open for M5b: D9 export exit-code semantics (§11).

## 14. Hands-on checks (user-run, before M6, not blocking M5)

OpenUtau version; tempo import for non-integral µs and mid-song changes; PPQ 480 vs other
resolutions and any internal rescaling or rounding; part naming from track names; behavior for notes
without lyrics; whether the end-of-track tick sets part length; whether meter events matter.

## 15. M5a status notes (implemented, not committed)

- `core/midi/`: `ticks`, `tempo`, `meter`, `model`, `build`, `encode`, `verify`, `export`.
  `export_midi(performed, assignments, *, ppq=480) -> MidiExport` is pure and in memory.
- **Deviation from §4:** the SMF bytes are written by our own small encoder (`encode.py`), not by
  `mido`. That fixes every byte (no running status, no inserted events, no library defaults) and
  makes `mido` an *independent* reader for `verify.py`, so writer and verifier cannot share a bug.
- The `Song` model already forbids duplicate tempo positions and non-power-of-two meter
  denominators, so the exporter's same-tick conflict and denominator checks are defensive; they
  are tested by building a `PerformedSong` directly.
- `Pitch` already refuses integral pitches outside MIDI 0..127; the exporter's range check is
  defensive and tested with a stand-in.
- The readiness registry scan skips `core/midi`: export failures are typed `MidiExportError` codes,
  not `ValidationIssue`s.
- **Implemented, VLQ policy:** delta times use the canonical variable-length quantity, at most four
  bytes (`0x0FFFFFFF`); a larger or negative delta is `MIDI_DELTA_OUT_OF_RANGE`, never truncated.
  Limits apply to each event-to-event delta (including the gap to end of track), not to absolute
  ticks. Pinned in `test_midi_vlq.py`.
- **Implemented, exit codes (D9 approved):** 0 success, 1 score not suitable, 2 usage/load/export/
  package/filesystem failure, with stable textual error codes (`MidiExportError.code`) instead of
  more exit codes. Applies to M5b.
