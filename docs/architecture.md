# Architecture

Status: M1 scaffold and M2 domain model are implemented. Everything under `core`,
`config`, `workers` and `ui` beyond entry points arrives in later milestones.

## Layers

| Package | Responsibility | May import |
|---|---|---|
| `models` | Pure domain data (see below) | stdlib only |
| `core` | MusicXML parsing, validation rules, synthesis backends, FFmpeg, pipeline | `models`, `config` |
| `config` | Settings and defaults (platformdirs) | `models` |
| `workers` | Qt adapters running core stages off the UI thread | `core`, `models`, Qt |
| `ui` | PySide6 views; no parsing or audio logic | `workers`, `models`, Qt |

Rules: `core` and `models` never import Qt. `models` imports nothing from `ui`, `workers`,
`core`, `config`, FFmpeg or OpenUtau code, or any MusicXML parser. A test enforces this by
importing the package in a subprocess and inspecting `sys.modules`.

## Domain model (`barbershop_tracks.models`)

Common conventions: frozen, slotted, keyword-only dataclasses; invariants checked in
`__post_init__` so invalid objects cannot be built; collections stored as tuples or
read-only mappings.

### Musical time (`timing.py`)

All positions and durations are `fractions.Fraction` in **quarter-note units** (quarter = 1,
eighth = 1/2, triplet eighth = 1/3, half = 2). `int` is normalized to `Fraction`;
`float` and `bool` raise `TypeError`. MIDI ticks never appear in the domain model. The
future MIDI exporter converts `Fraction -> ticks` at a configurable PPQ (480 for v1),
verifies the result is an exact integer, and reports a validation ERROR otherwise.

`TempoChange(position, bpm)` (quarter-note BPM, exact) and
`TimeSignature(position, beats, beat_type)` (with `measure_length` in quarters) form the
tempo and meter maps.

### Pitch (`pitch.py`, `pitch_transform.py`)

- `Pitch(step, octave, alter)` is a **spelled pitch**: `Step` letter, scientific octave
  (C4 = middle C), and a `Fraction` alteration in semitones (+1 sharp, -1 flat, +-2
  double, fractions for microtones). C#4 and Db4 are unequal values that share a
  `midi_note` (`sounds_like`). B#3 stays octave 3. A microtonal alteration is
  representable but `midi_note` raises rather than rounding.
- `PitchTransform(diatonic, chromatic, octave_change)` is the **musical concept** of
  "what must be added to a written pitch to get the sounding pitch". It mirrors the
  semantics of the MusicXML `<transpose>` element without referencing XML: identity is
  `PitchTransform()`; a part notated an octave above where it sounds (tenor voice on a
  treble clef) is `octave_change=-1`; a B-flat instrument is `diatonic=-1, chromatic=-2`.
  `apply(written)` derives the sounding `Pitch` deterministically, preserving spelling
  wherever the interval allows and keeping fractional alterations fractional. Components
  that point in opposite directions are rejected, and results that cannot be spelled (more
  than a double sharp/flat) or fall outside MIDI range raise `ValueError`.

### Note (`note.py`)

A note stores the pitch **as written in the source** (`written_pitch`) and its
`transform` (identity by default). `sounding_pitch` and `midi_note` are derived
properties; there is no second stored pitch, so they cannot contradict each other.
A rest has `written_pitch=None`, no lyrics, no ties and only the identity transform.
Other fields: `start`, `duration` (positive), source `measure` (0 allowed for a pickup),
1-based `beat` in quarter notes, `tied_to_next`, `tied_from_previous`, and `lyrics`.

Open item for M3: whether MusicXML `<clef-octave-change>` (used for tenor treble-8vb
clefs) alters the values in `<pitch>` is not stated by the MusicXML 4.0 reference. M3 must
determine it from the specification and real MuseScore exports, then populate
`PitchTransform` accordingly or report ambiguity. The model supports either outcome.

### Lyrics (`lyric.py`)

`Lyric` keeps the **source** lyric: exact `text`, `syllabic` (single/begin/middle/end),
`verse`, `melisma` state (none/start/continue/stop) and `elided` segments. Extension-only
lyrics (a melisma line with no text) are built with `Lyric.extension`. OpenUtau
conventions (`+`, `+~`) are never created or interpreted in the model; the strings `+`,
`+~`, `-` and `[...]` are plain text here. The MIDI exporter derives its own
representation and reports every transformation.

### Part and Song (`part.py`, `song.py`)

`Part` has a source `part_id`, `name`, ordered `events` (notes and rests, non-decreasing
start; simultaneous events are allowed so a validator can report them) and an optional
`role`. Roles are assigned explicitly (`with_role`) and never inferred from the name.
`VoiceRole` is exactly TENOR, LEAD, BARITONE, BASS.

`Song` holds title, composer, arranger, parts, tempo map, time-signature map and
`SourceMetadata`. It only enforces structure (unique part ids, ordered maps). Musical
correctness is the validator's responsibility.

### Validation (`validation.py`)

`Severity` (INFO < WARNING < ERROR); `ValidationIssue` with an UPPER_SNAKE_CASE `code`,
message and optional role, part id, measure and beat (identifiers only, never references
to `Song`/`Part`/`Note`); `ValidationResult`, an immutable ordered collection with
`has_errors`, `errors`/`warnings`/`infos`, `by_severity`, `at_least`, `by_code`,
`with_issue` and `merged`.

### Mixing (`mix.py`)

Data only; no audio processing. `TrackKind` is FULL, PREDOMINANT, SOLO, MINUS.
`MixProfile` defaults to target 0 dB, background -12 dB, centered, with optional per-role
panning. `StemMix(role, gain_db, pan)` and `TrackPlan(kind, inputs, target, speed)`
describe one output file; `speed` is an exact `Fraction` so practice-speed variants can
be added without changing the mixer. `TrackPlan` rejects inconsistent combinations (for
example a MINUS track that includes its target).

### Jobs (`jobs.py`)

Qt-independent `JobRequest` (paths, explicit part-to-role assignments, `MixProfile`,
backend name, optional stem paths) and `JobResult` (`JobStatus`: COMPLETED, FAILED,
CANCELLED, AWAITING_STEMS; validation result; output files; error message).

## Synthesis backends

`SynthesisBackend` protocol with `ManualOpenUtauBackend`, `ExternalStemsBackend` (a
first-class workflow, not only a fallback) and `TestToneBackend`.
`AutomatedOpenUtauBackend` is reserved. MIDI is the v1 interchange format and must not be
assumed to be the only one (USTX is a possible future exporter). See
[openutau-integration.md](openutau-integration.md).

## Milestones

M1 scaffold (done), M2 domain models and validation framework (this document), M3
MusicXML parsing, M4 validation rules and CLI report, M5 FFmpeg layer, M6 MIDI bundle and
stem ingest (after the OpenUtau hands-on checks), M7 pipeline, M8 UI, M9 packaging.
