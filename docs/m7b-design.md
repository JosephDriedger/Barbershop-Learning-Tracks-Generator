# M7b design: synthesis plan, USTX writer, runtime layout, staging contract

Status: implemented but **uncommitted, awaiting architectural review**. M8 is not started.

## Module layout

```
core/synthesis/            engine-neutral; imports no OpenUtau concept
  plan.py                  immutable SynthesisPlan and its parts
  build.py                 PerformedSong + voice assignments -> SynthesisPlan
  errors.py                SynthesisPlanError, PlanNotReadyError
  openutau/                the only place that knows USTX
    target.py              pinned target (OpenUtau 0.1.565, USTX 0.7, resolution 480)
    ustx.py                write_ustx(plan) -> UstxDocument
    yaml_emit.py           deterministic emitter for exactly the shapes USTX needs
    expressions_0_7.py     verbatim static block from a 0.1.565 save
core/runtime/              layout.py (directories), staging.py (transactional staging)
```

## SynthesisPlan contract

`SynthesisPlan(source, voices, tempo, meter, engine_refs, output)`, frozen dataclasses throughout.

* `source`: `SourceIdentity` (display name, SHA-256, title) of the performed score.
* `voices`: exactly four `VoicePlan`s, in Tenor, Lead, Baritone, Bass order. Each note carries
  `index`, exact `Fraction` `start`/`duration` (quarter notes), integer sounding `midi_pitch`
  and a `NoteLyric`.
* `tempo`, `meter`: events with exact positions.
* `engine_refs`: per role a `VoiceEngineRef(singer, phonemizer, renderer)`, three opaque non-empty
  strings. The plan never interprets them; renderer, singer and phonemizer are separate fields.
* `output`: `OutputRequirements` (performed length, stem roles) for later padding and verification.
* `review_items` / `is_ready` are derived, never stored. `write_ustx` raises `PlanNotReadyError`
  for a plan that is not ready.

## Lyric states

| State | Meaning | Decided? |
|---|---|---|
| `SCORE_LYRIC` | text from the score, with provenance (line, analysis role, source text, syllabic) | yes |
| `SCORE_CONTINUATION` | melisma continuation from the score, with the origin note | yes |
| `ABSENT` | no lyric (also humming, laughing, elision, conflicts, unsupported material) | **no**: blocks readiness |
| `INFERRED_PROPOSAL` | a suggested text with its basis | **no**: blocks readiness |
| `USER_APPROVED` | explicit approval (text, approver, proposal basis) | yes |

An approval beats a proposal for the same note; neither may override a score lyric
(`PLAN_APPROVAL_OVERRIDES_SCORE`). Nothing copies Lead lyrics into harmony voices. State/field
consistency is enforced at construction. The review reasons are `LYRIC_ABSENT`,
`LYRIC_PROPOSAL_UNAPPROVED`, `LYRIC_CONFLICT`, `LYRIC_UNSUPPORTED_SOURCE`.

## USTX writer (OpenUtau 0.1.565, USTX 0.7 only)

Deterministic text (same plan, same bytes; LF, fixed key order, no timestamps). Four tracks named
by role, tempo and time-signature lists, per-note `position`/`duration`/`tone`/explicit `lyric`
(always JSON-quoted), flat pitch curve, explicit `singer`, `phonemizer`, `renderer_settings`.
Voice part duration is the last note end; stems therefore end at the last note and the mixer (M9)
pads to the performed length.

* Continuation notes are written as `+`. `+~` and `-` are never emitted and are refused as lyric
  text, as is anything starting with `+`. `ContinuationToken` has a single member so any other
  semantics must be added deliberately. A continuation with no preceding lyric is
  `USTX_CONTINUATION_ORPHAN`; one that does not start exactly where the previous note ends is
  `USTX_CONTINUATION_GAP` (see the experiment below for why).
* Unknown target version, renderer outside the 0.1.565 list, or malformed singer/phonemizer
  strings are errors. No future version is assumed compatible.

### Timing

Supported: quarter positions/durations whose tick value `q * 480` is an exact integer, notes of at
least 10 ticks. Refused: `USTX_TIMING_NOT_ON_GRID` (e.g. 1/960 offsets, exact quintuplet remainders)
and `USTX_NOTE_TOO_SHORT`. Reason: observation showed a PPQ-960 import of off-grid ticks is floored
and a 7.5-tick duration became 10; the writer will not silently round. The generic M5 MIDI exporter
is unchanged and not restricted to 480.
#### Meter (blocking)

The meter is evidence, not a default. `USTX_METER_MISSING`: the plan has no meter at position
zero (so no 4/4 is ever assumed). `USTX_METER_UNSUPPORTED`: a beat unit that is not a power of two,
or a change that is not on a bar line of the preceding meter (pickup, irregular measure). Neither
is warned about and carried on; the write fails. Meter does not change the audio, but a score whose
barlines cannot be represented faithfully is not written at all. Consequently a score with a
pickup bar followed by a meter change is refused until the plan can express it. The test builders
state 4/4 explicitly because their hand-built scores carry no meter event; the plan builder itself
never invents one.

#### Tempo tolerance

Tempo is stored as a double. The writer measures, per tempo segment, the difference in seconds
between the exact timeline (`quarters * 60 / exact_bpm`) and the stored one (`quarters * 60 /
double(bpm)`), sums these over the whole performed score (to the larger of the performed length and
the last note end) and records the total as `UstxDocument.tempo_drift_seconds`.

* Limit: `MAX_TEMPO_DRIFT_SECONDS` = 1 microsecond total, about 1/23 of one 44.1 kHz sample.
  Exceeding it is `USTX_TEMPO_DRIFT`; a non-finite or non-positive double is
  `USTX_TEMPO_UNREPRESENTABLE`. The limit can be tightened per call (`tempo_tolerance_seconds`).
* Position of every tempo event must still be on the tick grid (no rounding).
* Honest scale: a double's relative error is about 1e-16, so ordinary scores drift by picoseconds
  (a 10^7-quarter score still stays inside the limit, tested). The limit exists to fail loudly
  on absurd input, not because typical scores come close. `USTX_TEMPO_QUANTIZED` is still emitted
  as a warning for every inexact value.
* Not covered: OpenUtau's own internal tick-to-time arithmetic (not audited here), and rendering
  latency/onset effects (the early-onset question is separate and unresolved).

## Experiment: does `+` continue the syllable? (review item 3)

Setup: OpenUtau.Core 0.1.565 through the M7a host, WORLDLINE-R, the default phonemizer, the
user-installed ALYS singer, 100 BPM, Tenor only audible (the other three voices carry the same
short alias). Notes: E4 for two quarters (1.2 s) then G4 for two quarters. Scratch script and audio
stay out of Git; the repeatable check is the opt-in integration test
`test_plus_continues_the_syllable_where_a_repeated_lyric_restarts_it`.

| Case | Notes | Quietest 10 ms near the 1.2 s boundary / peak | f0 before, after |
|---|---|---|---|
| A | `la`, then `+` (a continuation) | 0.75 (energy carries across) | 329 Hz, 394 Hz |
| B | `la`, then `la` | 0.15 (energy drops, new onset) | 329 Hz, 390 Hz |
| C | one `la` held four quarters | 0.86 | 329 Hz throughout |
| D | A with a one-quarter gap before `+` | the `+` note is silent; the stem ends at 0.6 s | n/a |

Findings:

1. A `+` note immediately after a note continues that note's sound with no new onset, and the pitch
   follows the `+` note (E4 to G4). It behaves as melisma continuation.
2. It does so only when the previous note ends exactly where the `+` note starts. This matches
   `UPart.Validate` in the pinned source (`Prev.End == position && lyric.StartsWith("+")`).
   After a gap the `+` note is its own note with no matching alias, and rendered as silence. The
   writer therefore refuses a gap (`USTX_CONTINUATION_GAP`).
3. Side observation: the voices whose lyrics were not aliases in the voicebank (`one`, `two`, ...)
   rendered 46-byte empty WAVs without any host error. A missing alias is silence, not a failure:
   M9's non-zero-audio verification is what catches it.

Limits of the claim: this shows a rendering-level continuation with an alias the singer has. It does
not show that any English lyric is phonetically correct for the French ALYS singer, that other
phonemizers treat `+` identically, or anything about `+~` and `-`, which stay refused.

## Singer, phonemizer, renderer configuration

No default singer exists; ALYS is not referenced anywhere in `src`. A missing reference is a
`PLAN_*`/`USTX_*SINGER_REF` error. The writer cannot know what is installed: existence checking is
host-side (M7a host exits 4 for an unknown singer or unresolvable phonemizer, because OpenUtau
otherwise substitutes a placeholder/default silently). Renderer choice is a separate field.

## Portable runtime layout

`core/runtime/layout.py` defines six roles, none created implicitly:

| Role | Default | Rule |
|---|---|---|
| binaries | where the app is installed | read-only |
| data | `platformdirs.user_data_dir("BarbershopLearningTracks")` | writable user state |
| singers | `<data>/singers` | user-installed voicebanks, never copied per render, never shipped |
| cache | `platformdirs.user_cache_dir(...)` | reproducible, safe to delete |
| staging | `<data>/staging` | per-job scratch, sibling of outputs |
| outputs | `<data>/outputs` | completed, validated results only |

### Limits of OpenUtau.Core path control (no private reflection used or planned)

`PathManager` chooses between "portable" (data beside the process executable) and "installed"
(`Documents\OpenUtau`) solely by the presence of `installed.txt` beside the executable. There is
no supported setting to point `Singers`, cache or plugins elsewhere. Consequences for M8:

1. Run a host copy inside a BLT-owned directory; with no `installed.txt` it reads
   `<hostdir>/Singers`. Make that a directory junction to BLT's `singers` (or to the user's
   existing OpenUtau `Singers`) so voicebanks are never duplicated. Junction creation and its
   behaviour with OpenUtau's singer search are **not yet tested**.
2. Or use `installed.txt` mode and accept `Documents\OpenUtau` as the singer location.
3. The render cache location follows the same rule; BLT's `cache` role is therefore informational
   until one of these is chosen in M8.

## Cancellation and transactionality contract (spec; the orchestrator is M8)

1. Each render job has its own `staging/.staging-<job>-<pid>/` containing `staging.json`
   (job, pid, creation time). Stems and intermediate files exist only there.
2. Cancel = terminate the owned host process **and its descendants** (process tree, not just the
   pid), wait for exit, then `remove_staging`. The M7a host has no cooperative cancel (exit 6 is
   reserved), so termination is the mechanism.
3. A stem set is published only after validation (existence, WAV decode, non-zero audio, format,
   duration, global alignment) by `publish`: an atomic same-volume rename that refuses an existing
   destination. No partial stem ever appears in `outputs`.
4. Failure or cancellation leaves no output; the staging dir is removed, or is left for stale
   cleanup if the process was killed.
5. Stale = marker pid not alive, or marker unreadable. `find_stale(root, is_alive)` lists them,
   `remove_staging` deletes only directories named `.staging-*`. Liveness checking itself
   (including pid reuse) is M8's job; the contract only requires the check be injected.

Implemented in M8 (see `docs/m8-rendering.md`): naming, pid-reuse-safe marker, stale detection, guarded removal, atomic publication, process-tree termination and the orchestrator.

## Tests

`tests/unit/core/synthesis` (plan, USTX writer, emitter) and `tests/unit/core/runtime` run without
OpenUtau or any voicebank. `tests/integration/test_openutau_host.py` is opt-in (marker
`integration`): it needs `BLT_M7A_HOST`/`DOTNET_ROOT` (defaults: the git-ignored spike build) and
`BLT_TEST_SINGER`; otherwise both tests skip.
