# Production backend recommendation and the M7–M12 plan

Status: **proposal for review.** The goal changed: BLT Music Generator must generate all 13 learning
tracks from a MusicXML score with minimal interaction. No production OpenUtau code exists yet;
M1–M5 contracts are unchanged. Evidence base: `docs/m6-findings-part-a.md`, `-part-b.md`,
`-part-c.md` and `tests/fixtures/openutau/observations/`.

## 1. Requirement that decides the backend

Unattended: score in, 13 WAV/MP3 files out, with only a one-time voicebank/engine setup. Per voice a
stem is rendered once and mixed deterministically. Missing singer, phonemizer, failed render or empty
audio must be an error. The GUI-driven workflow measured in A/B (File > Open, per-track singer,
Export Wav Files To) is correct but manual; fragile mouse automation is excluded.

## 2. Candidates compared

Evidence tags: **[obs]** observed here, **[src]** read in source/docs, **[web]** web search, **[none]**
not verified.

| Candidate | Unattended | Windows | English choral/lyrics | 4 stems | Pitch/timing | Licence / redistribution | Setup | Maintenance risk | PyInstaller |
|---|---|---|---|---|---|---|---|---|---|
| **A. OpenUtau GUI automation** | no: single-instance GUI, focus fights [obs] | yes | yes | yes [obs A15] | exact [obs] | MIT; voicebank per user | high, brittle | very high | n/a |
| **B. BLT sidecar on `OpenUtau.Core` (headless, pinned)** | **yes if the spike passes** [none: not run] | yes (.NET) | per voicebank + built-in phonemizers [obs] | yes (per-track render exists [src]) | exact in OpenUtau import/render [obs A/C03] | MIT code [src]; voicebank user-installed, not shipped | medium: .NET SDK to build only, self-contained publish | medium-high: undocumented API, mitigated by pinning and our A-series contract tests | sidecar exe next to the PyInstaller app (subprocess) |
| C. Own UTAU-compatible engine in Python (oto.ini + WORLD) | yes | yes | yes | yes | we own it | WORLD BSD-like; voicebank per user | low runtime, **very large build** | very high (reimplements phonemizing, overlaps, curves) | yes |
| D. Classic resampler/wavtool protocol driven by BLT | yes | yes | needs our own phoneme/oto layer | yes | we own timing | protocol documented [src]; resamplers separately licensed | medium | high (same reimplementation as C) | yes |
| E. Sinsy | CLI is a client of a web service [web]; local build BSD [web] | partial | limited English HTS voice [web] | per file | HMM quality, fixed voices | BSD/GPL mix [web] | medium | medium | possible | 
| F. NEUTRINO | yes (batch, MusicXML in) [web] | yes | Japanese-oriented [web] | per file | NN timing | freeware, terms unverified [none] | low | medium | possible |
| G. Synthesizer V Studio | **no CLI/headless** (scripting inside GUI only) [web] | yes | good | yes | good | proprietary | n/a | n/a | n/a |
| H. DiffSinger models run by BLT directly (ONNX) | yes | yes | per model | per voice | model-defined | per model licence | high build | high | heavy |
| I. VST host of a proprietary engine (e.g. Alter/Ego) | possible [none] | yes | per bank | per track | host-defined | proprietary | high | medium | heavy |
| J. OpenUtau DAW-integration TCP API | no: needs a running GUI [src] | yes | as OpenUtau | yes | as OpenUtau | MIT | high | n/a | n/a |

Rejected for v1: A (fragile), C/D/H (reimplementation scale), G (no headless), J (GUI-bound), I (per-bank
proprietary), E/F (voices and language do not fit English barbershop; unverified licences).

## 3. Recommendation

**Candidate B: a small BLT-owned .NET console host ("render host") that references `OpenUtau.Core`
at one pinned release tag, loads a USTX that BLT generates, renders per-track stems, writes WAVs and a
machine-readable result.** It reuses OpenUtau's phonemizers and renderers (the same code that produced
the stems measured in A15/A16/C03), which is the only route that gives real singing from ordinary
UTAU voicebanks without re-implementing them. BLT stays a Python application; the render host is a
separate executable launched as a subprocess with JSON in and JSON out.

Why this is defensible, and what it is not:

- It is **not** adopting an undocumented API as a promise. `OpenUtau.Core` is MIT licensed, has no
  UI dependency and is run headlessly by OpenUtau's own tests [src], but it is classified
  UNDOCUMENTED as an embedding API. The risk is contained by: pinning one tag (0.1.565 is net8 and
  self-contained, master is on net10 and drifting); a thin adapter around the few calls we use;
  the A-series observations kept as **contract tests** that re-run against any new pinned version;
  and an explicit go/no-go spike before any further investment.
- Project-file compatibility has evidence (C03). Unattended rendering has **none yet**; that is
  the spike's job.
- Fallbacks if the spike fails: (1) contribute a headless render entry point upstream (MIT, active
  project) and wait; (2) keep the existing manual-assisted workflow with corrected steps (File >
  Open, per-track singer, Export Wav Files To) so the product still works, only not unattended.

Needs your decisions before the spike: approval to install the .NET SDK on this machine (build time
only); the OpenUtau tag to pin; and an English voicebank with terms that permit OpenUtau use (ALYS
is French and was used only for workflow tests). BLT will not ship or auto-download voicebanks.

## 4. Architecture (preserve M1–M5)

```
MusicXML ─ M3 performed score ─ M4 readiness ─ [role + lyric assignment] ─ SynthesisPlan (engine-neutral)
   ─ OpenUtauPreparer (USTX) ─ RenderHost subprocess ─ stems ─ StemVerifier ─ Mixer ─ 13 tracks
```

- `core/` stays GUI-free. The synthesis contract is engine-neutral: a `SynthesisPlan` holds, per
  voice, exact performed notes (M3), explicit lyric tokens, tempo and meter; an `Engine` protocol has
  `prepare`, `render`, `cancel`.
- Engine-specific policy lives in the OpenUtau preparer only: explicit lyric on every sounding note,
  literal `+` / `+~` (never `-`; choice to be settled by a synthesis test), PPQ 480 positions (exact
  on OpenUtau's 480 grid), tempo as the MIDI-encoded value, File-Open-equivalent project state.
- The MIDI handoff (M5) is kept as the manual/diagnostic path and as a cross-check, not the main path.
- Timing: never alter notes, tempo, lyrics or assignments; stems keep the global origin; the mixer pads
  ends to the performed duration, never trims leading silence, never shifts for onset (A16).
- Verification before mixing (A15 requirement): exists, decodes, nonzero frames, expected format
  (mono 16-bit 44.1 kHz), duration plausible vs the plan, correct voice, global alignment.

## 5. Milestones (each: tests, review, green CI, stop for review)

- **M7a: unattended synthesis feasibility spike (bounded proof of concept).** A throwaway .NET console
  host under an isolated spike directory, referencing the pinned OpenUtau source
  (`a60ca5830b9064556157245d4bf8f5920d93e5f8`) and loading a known-good USTX saved by OpenUtau 0.1.565.
  GO only if it renders four nonempty decodable stems with correct identity, order and global origin,
  consistent with the GUI baseline within stated tolerances, with no visible window, a nonzero failure
  for a missing singer, working cancellation, bounded reproducibility, identified packaging
  dependencies and measured startup time, memory and output size. Not production code; no USTX writer,
  no mixer, no GUI.
- **M7b: engine-neutral synthesis plan, lyric mapping and version-pinned USTX adapter.**
  `SynthesisPlan` (exact performed notes, lyric states, tempo, meter), the lyric model below, and an
  OpenUtau USTX adapter pinned to the version the pinned release writes, with round-trip tests against
  the observation corpus.
- **M8: production render host and Python subprocess backend.** Hardened host (from the spike's
  findings), JSON in/out, exit codes, voicebank discovery and validation, progress, cancellation,
  logs, error mapping, contract tests from the A-series observations.
- **M9: WAV verification and 13-track mixing.** `StemVerifier` and the deterministic mixer (pad to
  performed length, per-voice gain, no leading-silence trimming, no onset compensation); presets for
  Full Quartet and Predominant, Solo and Minus for each voice; WAV and MP3 output through an external,
  configurable FFmpeg.
- **M10: integrated generation pipeline and CLI.** `generate` producing all 13 outputs with structured
  results and the M4/M5 exit-code convention.
- **M11: PySide6 desktop GUI.** Full control list from the product goal; the UI never touches audio.
- **M12: Windows packaging, installer, documentation and release validation.** PyInstaller app plus
  render host; evaluate the exact FFmpeg build's licensing and redistribution terms before any
  bundling; licence notices; no voicebank shipped.

Repository rules hold throughout: no generated audio, voicebanks, real scores, OpenUtau projects or
downloaded/source-built binaries in Git; tests use synthetic material.

### Lyric model (decided; implemented in M7b, not before)

The application must keep these states distinct for every sounding note of every voice:

1. explicit lyrics supplied by the score;
2. explicitly marked melisma continuation;
3. absent lyrics;
4. proposed lyrics inferred from another part;
5. user-approved lyric assignments.

Inferred alignment is always shown for review before synthesis. The Lead's syllables are never copied
into harmony voices by default and never substituted silently.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Undocumented `OpenUtau.Core` API changes | pin a tag; thin adapter; A-series contract tests; upstream contribution; manual-assisted fallback |
| Spike shows render needs UI-thread or singleton state we cannot supply | no-go; fall back to upstream CLI or assisted workflow; nothing else built on it |
| Silent empty stems (no singer) | StemVerifier plus a pre-render singer check; both are errors |
| Early audio onset about 0.1 s (A16) is voicebank-specific | do not compensate; surface in logs; revisit with evidence |
| Lyric propagation to harmony voices is musically ambiguous | explicit policy and preview; never silent |
| English voicebank licence | user supplies; BLT only checks it is installed and renders; no legal claims |
| Size and cold start of a self-contained .NET host | measured in M7a |

## 7. Decisions (updated after review)

1. .NET 8 SDK: approved for the M7a spike; keep downloaded binaries and builds out of Git.
2. Pinned source: OpenUtau release 0.1.565, commit `a60ca5830b9064556157245d4bf8f5920d93e5f8`.
3. English voicebank: ALYS (French, already installed) for M7a; a clearly licensed English bank is
   chosen only after M7a passes, for pronunciation and melisma tests.
4. Harmony-voice lyrics: no default copy of the Lead; see the lyric model above.
5. Output formats: WAV and MP3. FFmpeg stays an external, configurable dependency during development;
   its build's licence is evaluated at M12 before any bundling.
