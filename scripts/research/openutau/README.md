# M6 OpenUtau research tooling (throwaway, not production)

Plan: `docs/m6-plan.md`. The catalog (`catalog.py`, or `observe.py list`) is the operational source
of truth for every experiment's steps, fields to observe and criteria; this README is the loop.
Nothing here drives the OpenUtau GUI, and nothing changes the M5 exporter. Generated files go to the
git-ignored `research-output/`; only structured observations (JSON) are committed, to
`tests/fixtures/openutau/observations/`.

Setup: the development environment (`pip install -e ".[dev]"`) includes everything, PyYAML for
`ustx-summary` included. PyYAML is a development dependency only, not a runtime one.

## The loop (one experiment at a time)

```powershell
python scripts/research/openutau/generate.py                      # 1. inputs + expected tables + index.json
python scripts/research/openutau/observe.py list                  # 2. pick an experiment
python scripts/research/openutau/observe.py template A06_TIMING_GRID --out my.json   # 3. blank observation
#  4. perform the experiment's steps in OpenUtau (see catalog.py for steps and fields)
#  5. record what you observed in my.json (environment, observed, classification, evidence method)
python scripts/research/openutau/observe.py validate my.json      # 6. strict; --allow-template for blanks
python scripts/research/openutau/observe.py compare my.json       # 7. expected vs observed events
python scripts/research/openutau/observe.py ustx-summary project.ustx   # Part C: structured facts
```

An untouched template never passes `validate`. An observation is bound to the input hash it was
recorded against: if the recipe later generates a different file, `validate` and `compare` report it
as stale. `compare` is factual (expected value versus observed value); the classification is a
judgement against the experiment's criteria and stays yours.

## What the inputs are

- **Part A** inputs are real M5 handoff packages built by the production code from tiny synthetic
  scores (`recipes_part_a.py`). Expected tables keep three values apart where they differ: the score
  value, the MIDI-encoded value (for tempo: exact BPM, exact and encoded microseconds per quarter) and
  what OpenUtau shows.
- **Part B** inputs are *experimental probe* MIDI files with lyric events (`recipes_part_b.py`),
  written with `mido`. They are not BLT output: a finding such as "`+~` imported as X" does not mean
  BLT emits `+~` (it does not).
- **Part C** has no generated input; `ustx-summary` reads a project OpenUtau itself saved, with
  `yaml.safe_load` only, and reports absent keys as `<not present>` rather than inventing defaults.

## Rules

- Experiment IDs are stable. One ID is one exact input and one question; if an experiment needs
  refining, add a new variant ID instead of changing the meaning of a recorded one.
- Record the OpenUtau version, platform and import method; never local paths, user names or
  timestamps (the validator rejects obvious path leaks and those keys). `blt_commit` may be `null`
  when git is unavailable.
- `ui_visual` evidence cannot support an exact `MATCH`; an `UNKNOWN` needs a reason.
- Voicebank-dependent experiments are flagged in `observe.py list`; do not use a voicebank for the
  rest.
- Generated `.mid`, `.ustx` and `.wav` files are never committed.
