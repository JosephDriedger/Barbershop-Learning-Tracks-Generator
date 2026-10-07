# M6 plan: OpenUtau interoperability research

Status: **research plan (revised after review).** No production code is written in M6's research
phase. The single question:

> What does the current OpenUtau release actually do with the artifacts and musical semantics
> BLT Music Generator needs?

M6 gathers evidence before any backend is implemented. It does not modify the M5 production MIDI
exporter and does not implement the production OpenUtau backend.

## 1. Rules

- **Pin the version.** Findings are written as "OpenUtau `<version>` did X in this experiment", never
  as timeless statements. Later versions may differ.
- Original, tiny synthetic material only. No commercial arrangements, voicebanks, rendered vocals or
  copyrighted audio in the repository. A voicebank is used only where an experiment truly needs
  phonemization, synthesis or rendered output, and only one the researcher is licensed to use; it is
  never committed.
- Generated `.mid`, `.ustx` and `.wav` files are never committed. Research output goes to a
  git-ignored directory; what is committed is structured observations.
- No GUI automation. No promotion of an undocumented flag or internal API into the architecture.
- The research tooling lives in `scripts/research/openutau/`, not in `src/`. Production `src/` is not
  changed during the research phase unless a small neutral extraction is unavoidable.
- Research tooling and findings are committed separately from any later implementation.
- Source of truth for a baseline comparison is **what the MIDI actually contains**, not the
  pre-quantised MusicXML value: source exact BPM, then MIDI-encoded value, then OpenUtau imported
  value are three different numbers and are recorded separately.

## 2. Ordering and dependencies

- **Part A** tests the exact artifact the M5 code already produces: no lyrics, no USTX, nothing
  changed to please OpenUtau. It is the baseline.
- **Part B** uses deliberately tiny *experimental* MIDI files (not M5 output) to discover lyric
  import semantics.
- **Part C** inspects OpenUtau-created projects and documented automation only after A and B show
  what MIDI can and cannot safely carry. USTX is not presumed to be preferable.

## 3. Observation schema (fixed before any experiment is run)

One JSON file per experiment, schema `barbershop-tracks.research.openutau/1`:

```
schema, experiment_id, part ("A"|"B"|"C"),
environment {openutau_version, openutau_build, platform, import_method, relevant_settings,
             blt_version, blt_commit (where the artifact came from BLT)},
input {description, recipe_id, artifact_sha256 (of the generated file) | null},
expected {summary, events: [...]},          # the expected MIDI/event table
observed {summary, events: [...]},          # what OpenUtau actually showed or saved
classification (see below), classification_note,
details {numeric/event details that back the classification},
evidence_method ("project_file" | "ui_numeric" | "ui_visual" | "documentation" | "source"),
requires {voicebank: bool, manual_openutau: bool},
notes
```

No local absolute paths, no user identity, no voicebank redistribution, no timestamps unless
genuinely needed. If a singer/voicebank affects a result, record only the minimum identity/version
needed to reproduce it. `ui_visual` evidence is the weakest and is never enough for a timing claim.

**Classification** (per finding, never one pass/fail boolean):
`MATCH` (behaviour matches the handoff contract), `BENIGN_DIFFERENCE` (different representation, no
musical corruption), `WORKFLOW_REQUIREMENT` (a manual action is required),
`INTEROPERABILITY_PROBLEM` (the artifact cannot safely carry required semantics), `UNKNOWN`
(the experiment could not establish it). Part C automation evidence additionally uses
`DOCUMENTED_STABLE`, `DOCUMENTED_EXPERIMENTAL`, `UNDOCUMENTED`, `NOT_FOUND`.

## 4. Experiment reproducibility

Each experiment has a stable ID (for example `A06_TIMING_TRIPLET`), an exact synthetic input recipe
(code, deterministic), the expected event table, the manual OpenUtau steps, the fields to observe and
the classification criteria, so someone else with OpenUtau can repeat it without the original
machine. Voicebank-free experiments (import and project structure) never require one.

## 5. Part A: the exact M5 artifact (no lyrics)

Use packages produced by the current `export` command. Record BLT version/commit, OpenUtau
version/build, operating system, import method and relevant import settings.

| ID | Question | Evidence needed |
|---|---|---|
| A01_FILE_ACCEPTANCE | Does the MIDI import? Errors or dialogs? Do all five tracks appear, or is the conductor special? | success/failure, dialogs, track list |
| A02_VOICE_TRACKS | For Tenor/Lead/Baritone/Bass: imported name, order, distinct track, did channel affect import, note count | expected vs observed per track |
| A03_CONDUCTOR | What happens to the meta-only track: ignored, empty track, global metadata only, other | observed behaviour |
| A04_PITCH | Expected MIDI note numbers vs imported pitches: chromatic, octave boundaries, a transposing-fixture case (the comparison is against M5's *sounding* MIDI; written-pitch semantics are not retested) | per-note numbers |
| A05_TIMING_BASIC | Exact-grid notes: expected start/duration/end vs imported, numerically | project/numeric values |
| A06_TIMING_GRID | Quarter, eighth, triplet/tuplet at PPQ 480, a nontrivial exactly representable tick. OpenUtau's internal resolution; are ticks copied, scaled or transformed; is scaling exact; any rounding? Not inferred from snapping | numeric, inspect the saved project if needed |
| A07_TEMPO | Tempo at zero; one later change; two distinct tempos; one tempo that needed M5 µs rounding. Source BPM, MIDI value, OpenUtau value | imported tempo map |
| A08_METER | 4/4; another power-of-two meter; a meter change; explicit M5 events vs imported state (omitted meter is not expected to reappear) | imported meter state |
| A09_PICKUP | Pickup score: note timing correct? Separately, what happens to the notation-level pickup (a loss of "implicit measure" identity is not timing corruption) | timing and structure |
| A10_PERFORMED_REPEATS | A score M3 has already expanded: note count, repeated material at the expected performed positions; no repeat semantics expected from OpenUtau | positions |
| A11_ADJACENT_NOTES | note-off at tick X then note-on at tick X: two notes, no overlap, truncation, dropped attack or unintended merge | per-note timing |
| A12_VELOCITY | What happens to constant note-on velocity 80: preserved, mapped, ignored. The production velocity is not changed unless it causes an actual problem | observed |
| A13_SINGER | After plain import: singer assigned automatically or none; depends on application defaults? Distinguish OpenUtau/user defaults from anything in the MIDI (M5 encodes no singer) | observed |
| A14_PHONEMIZER | Likewise: assigned? which? from singer, default or application state? An environment default is not information imported from BLT | observed |
| A15_RENDER_WORKFLOW | The manual workflow to get Tenor/Lead/Baritone/Bass WAVs: menu/action, one operation for all tracks?, output naming, mute/solo effect, does rendering require a singer/phonemizer; sample rate and start alignment | recorded steps and outputs |

A13 to A15 need a licensed voicebank; A01 to A12 do not. A15 informs the production
`ManualOpenUtauBackend`. Benign differences do not cause production changes.

## 6. Part B: MIDI lyrics (experimental files, never M5 output)

Question: can MIDI lyric events faithfully express the performed lyric semantics OpenUtau needs?
Record, for each case, the exact MIDI lyric text and the exact imported lyric per note.

| ID | Case |
|---|---|
| B01_SYLLABLES | one syllable per note; a multisyllable word across notes; a repeated word/syllable; punctuation |
| B02_MISSING_LYRIC | a note with no lyric event between lyric-bearing notes: what does OpenUtau assign (not assumed blank/previous/default/rest) |
| B03_PLUS | literal `+` in the continuation position |
| B04_PLUS_TILDE | literal `+~`, separately (not assumed equivalent to `+`) |
| B05_MELISMA | a word extended across several notes with candidate encodings as isolated alternatives (for example first syllable then `+`, first syllable then `+~`); M3 lyrics and M5 export are not touched |
| B06_PITCH_CONTINUATION | continuation across the same pitch, a changed pitch, a repeated adjacent pitch; does behaviour depend on pitch movement as well as tokens |
| B07_FOUR_TRACKS | lyric events independently on all four voice tracks: does each track get its own |
| B08_ONE_SOURCE_TRACK | lyrics on one track only: what happens to the others (propagation is not assumed) |
| B09_TEXT | apostrophe, hyphen, comma, period, question/exclamation: only tiny original text, and no arbitrary "bad character" policy from isolated observations |

Outcome questions (answered, not implemented): (1) can MIDI lyric events faithfully carry the
semantics we need; (2) if so, what exact deterministic transformation from M3 performed lyrics;
(3) is it singer/phonemizer/language dependent; (4) does lyric export belong in the generic MIDI
handoff or in an OpenUtau backend; (5) what information is lost. B01 to B09 inspect imported lyric
text and need no voicebank; any claim about how a lyric *sounds* needs one.

## 7. Part C: USTX and the automation boundary

Use OpenUtau itself to create and save tiny synthetic projects and inspect them. `.ustx` files are
not committed; extracted structured observations are.

| ID | Question |
|---|---|
| C01_USTX_STRUCTURE | OpenUtau version; USTX version/schema indicator; representation of tracks, note timing, tempo, meter, lyrics, singer, phonemizer, and the expressions/settings relevant to basic synthesis |
| C02_STABILITY | what the current file contains versus what OpenUtau promises is stable: documented compatibility/versioning evidence if available; readable YAML is not a stability promise |
| C03_ROUND_TRIP | OpenUtau creates a tiny project, saves, we inspect, OpenUtau reopens it. A script-generated or modified project is a *separate* later experiment; production USTX generation is not the first test |
| C04_MINIMALITY | can a useful project omit singer, phonemizer, expressions, renderer settings, voicebank metadata (does generic USTX generation improve on MIDI at all) |
| C05_SINGER_PORTABILITY | how singer identity is stored: stable id, path, display name, installation-specific; machine dependence materially affects whether BLT should generate projects |
| C06_PHONEMIZER_PORTABILITY | the same analysis for phonemizers; a phonemizer name is not assumed portable between installations |
| C07_AUTOMATION | research documentation, source and release behaviour for a documented, stable mechanism to open/import a project, select singers, render and export stems without GUI interaction. Classify each finding `DOCUMENTED_STABLE`, `DOCUMENTED_EXPERIMENTAL`, `UNDOCUMENTED` or `NOT_FOUND` |

If no stable interface exists, `ManualOpenUtauBackend` remains the correct v1 backend; that is not a
failure of M6. GUI clicks are not automated and undocumented internals are not promoted.

## 8. Research tooling (written after this plan is committed)

`scripts/research/openutau/`: generators for the controlled experimental MIDI (deterministic, output
to the git-ignored `research-output/`), expected-event-table extraction, observation schema,
template and validator, a USTX summariser that extracts structured fields (research only), and an
expected-versus-observed comparer. The scripts do not drive the OpenUtau GUI. Generated binaries are
never committed (`.gitignore` plus the existing audio/binary guard, which already refuses `.wav` and
`.ustx`; `.mid` output stays under the ignored directory).

## 9. Stop points

1. This plan is committed on its own ("Document M6 OpenUtau interoperability research plan"),
   pushed, CI green.
2. The research tooling and observation templates are written; **stop before committing them** and
   report (scripts, experiment IDs, artifact types, schema, which need a voicebank, which need manual
   OpenUtau work, how binaries are excluded from Git, gate results). Wait for review.
3. The experiments are run by someone with OpenUtau; observations are committed as structured files,
   separately from any implementation.
4. The findings report recommends the backend contract (MIDI notes only, MIDI with lyrics, USTX,
   other), lyric propagation/escaping rules for harmony voices, and an OpenUtau version support
   policy. Nothing is implemented before that review.
