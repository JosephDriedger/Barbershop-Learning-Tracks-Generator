# M8: unattended rendering backend

M8 turns a ready `SynthesisPlan` into four validated vocal stems with no GUI, no manual MIDI/USTX
opening and no manual WAV export. Layout and host: `docs/m8-runtime-layout.md`. This document covers
the Python backend (M8b) and the stem validation (M8c). It does not mix tracks (M9), has no GUI (M11)
and bundles no voicebank. It makes no claim that the application is ready for distribution: the
dependency licensing audit (`docs/dependency-audit.md`) is incomplete.

## Modules

```
core/rendering/
  backend.py   OpenUtauRenderBackend.render(plan, destination, cancel=, on_event=, replace=)
  process.py   OwnedProcess: one child + its descendants in a Windows job object
  stems.py     validate_and_collect(): checks the host output, then names the stems by role
  wav.py       strict RIFF/WAVE reader (no third-party audio library)
  errors.py    RenderError and its six subclasses
  cancel.py    CancelToken
core/runtime/
  host_install.py     per-version writable copy of the host binaries
  staging.py          .staging-<job>-<pid> directories, stale recovery, atomic publication
  process_identity.py (pid, process start time) so a recycled pid is never mistaken for its owner
```

## One render is one transaction

1. Check the singers directory; install/reuse the host runtime copy.
2. `write_ustx(plan)`: a plan that is not ready, or a timing/meter/lyric the writer refuses, is a
   `ProjectValidationError` before anything is created.
3. Remove staging directories whose owner is gone (never an active one), then create
   `staging/.staging-<job>-<pid>/` (marker written before the directory gets its final name).
4. Run `blt-render-host --project … --out <staging>/host-out --base stem --singers-dir …` as an owned
   process; stdout events are parsed and forwarded to `on_event` as they arrive; stderr is kept.
5. Interpret the exit code and the final `result` event.
6. Validate the stems (below); move them to `<staging>/stems/<Role>.wav`.
7. Publish `stems/` to `destination` with one rename. Always remove the staging directory.

A failed, cancelled or timed-out attempt never touches `destination`; with `replace=True` a
successful attempt moves the previous result aside and restores it if the final rename fails. Two
jobs for one destination: one wins, the other gets `PUBLISH_DESTINATION_EXISTS`.

## Typed errors

| Class | Codes (examples) | When |
|---|---|---|
| `RenderConfigurationError` | `SINGERS_DIR_MISSING`, `HOST_BINARIES_MISSING`, `HOST_INSTALL_FAILED`, `STAGING_UNAVAILABLE`, `HOST_LAUNCH_FAILED`, `HOST_UNRESOLVED` (host exit 4: singer, phonemizer or renderer), `HOST_ENVIRONMENT` (exit 8: native library…), `HOST_USAGE` (exit 2), `PUBLISH_*` | the environment cannot render this plan |
| `ProjectValidationError` | `PLAN_NOT_READY`, `USTX_*`, `HOST_PROJECT_REJECTED` (exit 3) | the plan/project is not renderable |
| `SynthesisError` | `HOST_FAILED` (exit 5 and 10), `HOST_NO_RESULT`, `HOST_INCONSISTENT` | the host ran and failed, or crashed |
| `RenderCancelledError` | `RENDER_CANCELLED` | the caller's `CancelToken` fired |
| `RenderTimeoutError` | `RENDER_TIMEOUT` (BLT's limit), `HOST_PHONEMIZE_TIMEOUT`, `HOST_RENDER_TIMEOUT` | time limits |
| `OutputValidationError` | `STEM_*` | exit 0 but the files are not acceptable |

Every error carries `.code`, `.message` and `.details` (exit code, stderr tail, the host's final
result when there was one).

## Process ownership, cancellation, timeouts

The host runs inside its own Windows job object (kill-on-close). Cancellation or timeout terminates
the job: the host and anything it started, and nothing else, whatever their pids are. A clean exit also
closes the job, which kills stragglers. Cancellation is polled every 50 ms; the host has no cooperative
cancel (OpenUtau 0.1.565 has none). Tests with the fake host start a grandchild and write a partial WAV,
cancel or time out, and assert the grandchild is gone, the staging directory is removed and nothing
was published; the same with the real host asserts no `blt-render-host` process remains.

## Staging ownership and stale recovery

The marker records pid and process start time. A directory is stale when no process with that pid
exists, or one exists that started at a different moment (a recycled pid). A marker that cannot be
read counts as stale only after 120 s. `find_stale`/`cleanup_stale` never list the calling process's
own directories or any other live job's. Cleanup runs at the start of every render.

## Stem validation (M8c)

Checked before publication, in this order, with the defaults of `StemPolicy`:

1. Exactly the expected files `stem_<Role>.wav` for the voices that have notes: none missing, none
   unexpected (files or directories).
2. Decodable RIFF/WAVE (truncated data, bad header, unknown format are `STEM_NOT_DECODABLE`).
3. At least one frame (`STEM_EMPTY`; this is how OpenUtau's silent rendering of an unsupported alias
   appears: a 46-byte WAV).
4. Format: 44.1 kHz, 16-bit PCM, mono: exactly what OpenUtau.Core 0.1.565 writes
   (`STEM_FORMAT_UNSUPPORTED` otherwise; the policy can widen it).
5. Not silent: peak above −80 dBFS (`STEM_SILENT`).
6. Duration within −0.05 s / +0.5 s of the end of the voice's last note under the plan's tempo map
   (`STEM_DURATION`). Measured on real output: exact to the millisecond.
7. Global origin: the first sample above 2 % of the peak lies within −0.25 s / +0.5 s of the first
   note's start (`STEM_ORIGIN`). Nothing is shifted to compensate. Measured: OpenUtau's sound begins
   about 50 ms before a note with the synthetic voicebank's 50 ms preutterance, so a leading rest is
   preserved but not sample-exact.
8. Every note of 60 ms or longer carries at least −60 dBFS RMS in its middle half
   (`STEM_NOTE_SILENT`, naming the note indices). This catches a single unsupported alias among good
   ones.

What this does not establish: a stem that passes is audible, the right length and starts in the right
place. It is **not** evidence of correct pronunciation, note accuracy or lyric accuracy. A voice
with no notes cannot occur (`SynthesisPlan` forbids it); if one ever did, the validator expects no
file for it and refuses one that appears, rather than demanding non-silence from it.

## Reproducibility and performance (this machine, Windows 11)

* Two cold renders are bit-identical; two warm renders are bit-identical; warm differs from cold by
  at most 1 LSB (the render cache stores 16-bit audio).
* Synthetic voicebank, 4 voices: 16 notes each (10 s of audio per stem): cold 4.8 s, warm 0.8 s;
  64 notes each: cold 7.3 s, warm 0.8 s; peak host memory 80 to 180 MB. ALYS, 4 notes each:
  cold about 4 s, warm about 0.6 s. These are small scores and a sine-wave voicebank, not a full
  song with a real voicebank; scaling to a full arrangement is unmeasured.
* The runtime copy took under 0.1 s to install on this machine (about 94 MB).

## Tests

* Unit (fake host, WAV fixtures, no OpenUtau): `tests/unit/core/rendering/`,
  `tests/unit/core/runtime/`: exit-code mapping, success exit with missing/corrupt/truncated/empty/
  silent/short/long/wrong-format/extra files, origin, cancellation and timeout with a grandchild and
  a partially written WAV, previous result kept, concurrent jobs, one destination two jobs, stale
  and recycled-pid recovery, permission failures (ACL-denied staging root and destination).
* Host (real `blt-render-host`, generated voicebank; built and run in CI): `test_render_host.py`.
* Backend (real host, generated voicebank; CI): `test_render_backend.py`: four-stem render, leading
  silence, missing singer, missing phonemizer, missing native library, unsupported alias (all
  voices, one note), cancellation, timeout, three concurrent jobs, repeated cold/warm runs, failed
  second attempt keeps the first result.
* Opt-in with a real voicebank: `test_alys_rendering.py` (`BLT_TEST_SINGER`,
  `BLT_TEST_SINGERS_DIR`), including the `+` continuation experiment through the production backend.

## Known limits

* Windows only (job objects, `worldline.dll`).
* One runtime copy is shared by concurrent jobs of the same host version, including its cache; three
  simultaneous real renders were clean, but heavy parallelism with real voicebanks is untested.
* The per-version runtime copies are never pruned.
* A phonemizer other than `OpenUtau.Core.DefaultPhonemizer` has not been exercised with a real
  voicebank; English phonemization (and therefore lyric correctness) is outside M8.
* The MIDI-less path means the 0.1 s early onset first seen in M6 is only bounded, not explained.
