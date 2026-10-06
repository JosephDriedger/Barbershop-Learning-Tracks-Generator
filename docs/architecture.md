# Architecture

> Placeholder (M1). Filled in as each milestone lands.

## Layers

| Package | Responsibility | May import |
|---|---|---|
| `models` | Pure domain data: Song, Part, Note, ValidationResult, MixProfile, TrackPlan | stdlib only |
| `core` | MusicXML parsing, validation, synthesis backends, FFmpeg, pipeline | `models`, `config` |
| `config` | Settings and defaults (platformdirs) | `models` |
| `workers` | Qt adapters running core stages off the UI thread | `core`, `models`, Qt |
| `ui` | PySide6 views; no parsing or audio logic | `workers`, `models`, Qt |

Rules: `core` and `models` never import Qt. Musical time is `fractions.Fraction` in
quarter-note units; MIDI ticks exist only inside the exporter, and the exporter's PPQ
is a parameter, not a domain concept.

## Synthesis backends

`SynthesisBackend` protocol with `ManualOpenUtauBackend`, `ExternalStemsBackend` (a
first-class workflow, not only a fallback) and `TestToneBackend`. `AutomatedOpenUtauBackend`
is reserved. MIDI is the v1 interchange format but must not be assumed to be the only one
(USTX is a possible future exporter).

## Milestones

See the project plan; M1 is the scaffold.
