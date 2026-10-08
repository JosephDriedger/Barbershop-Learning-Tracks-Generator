# M6 Part A findings (phase A1: A01-A12)

Tested: OpenUtau `0.1.565+a60ca5830b9064556157245d4bf8f5920d93e5f8` on Windows 11, no singer
selected, inputs from the production M5 path (PPQ 480, plus one PPQ 960 discriminator). Every
statement below is about that version. Evidence: temporary projects saved by OpenUtau and read
back numerically; the structured records are in `tests/fixtures/openutau/observations/` (A13-A15
are pending a research voicebank).

| Experiment | Classification |
|---|---|
| A01 file acceptance | MATCH |
| A02 voice tracks | MATCH (MIDI-channel effect: UNKNOWN, not observable) |
| A03 conductor | BENIGN_DIFFERENCE |
| A04 pitch | MATCH |
| A05 basic timing | MATCH |
| A06 grid, PPQ 480 | MATCH |
| A06 grid, PPQ 960 | INTEROPERABILITY_PROBLEM (sub-grid positions only) |
| A07 tempo | WORKFLOW_REQUIREMENT |
| A08 meter | WORKFLOW_REQUIREMENT |
| A09 pickup | BENIGN_DIFFERENCE |
| A10 performed repeats | BENIGN_DIFFERENCE |
| A11 adjacent notes | MATCH |
| A12 velocity | BENIGN_DIFFERENCE |

## Consequences recorded for later (nothing in production has been changed)

- **Import workflow.** With `File > Open` on the `.mid`, OpenUtau 0.1.565 imported the tempo map and
  the meter events (positions exact; the 666667 microseconds-per-quarter tempo appears as
  60,000,000 / 666667 BPM, the MIDI-encoded value). With `File > New` followed by `File > Import
  Midi` it applied neither (the project stayed 120 BPM, 4/4). The current `OPENUTAU-STEPS.txt`
  describes the second workflow, which is unsafe for any score whose tempo is not 120. This is a
  correctness fix for a later change (the manual-backend instructions), deliberately not made in the
  research commits.
- **Timing grid.** OpenUtau 0.1.565 imports MIDI musical timing into a project with resolution 480.
  PPQ 960 positions that map exactly onto that grid were preserved exactly (a rescale, not a copy of
  ticks); tested positions needing fractional project ticks were not (some truncated downward, a 7.5
  tick duration became 10; a minimum-duration rule is suspected but not isolated). The generic MIDI
  serializer keeps its own contract (requested PPQ, exact or an error); the OpenUtau handoff will
  need its own policy, for example PPQ 480 with every position integral at 480. That decision waits
  for the end of M6.
- **Defaults that are OpenUtau's, not BLT's.** Notes with no lyric event receive the lyric `a`; the
  phonemizer is `OpenUtau.Core.DefaultPhonemizer`; no singer is stored. Part B must test lyric
  behaviour with this in mind.
- **Pickup.** Musical timing survives; the notation-level pickup does not, so OpenUtau barlines sit
  one beat away from the score's. Benign; no count-in is invented.
- **Repeats.** OpenUtau deduplicated the equivalent tempo and meter declarations M3 replays at a
  repeat; M3's semantics are unchanged.
- **Velocity.** MIDI velocity 80 is not preserved as a stored note value or as the `vel` expression
  in the imported state. Rendering was not tested, so no audible claim is made.

# Phase A2 (A13-A15): singer, phonemizer and WAV export

Research voicebank: ALYS DB002 FRA v1.0.0 (an UTAU French bank), from
`https://labs.phundrak.com/ALYS/ALYS-DB-002-FRA`, installed with Tools > Install Singer. Its
bundled `LICENCE.ALYS-1.0` explicitly permits UTAU, OpenUTAU and Plogue Alter/Ego and forbids
redistribution, so it is used locally for research only: not committed, not a dependency, not shipped.
A different voicebank (LIEE) was considered first and rejected because its bundled and published terms
did not make OpenUtau use clear enough; this is not a project feature, and BLT makes no legal
statement about third-party singers.

| Experiment | Classification |
|---|---|
| A13 singer | WORKFLOW_REQUIREMENT |
| A14 phonemizer | BENIGN_DIFFERENCE |
| A15 render workflow | WORKFLOW_REQUIREMENT |

Facts, as separate statements about OpenUtau 0.1.565:

- Installing a singer does not change what MIDI import assigns: no singer is stored until one is
  selected, per track. The stored reference is the installation folder name (`alys-db-002-fra`),
  which is installation-specific.
- Selecting the singer set the track renderer to `WORLDLINE-R` automatically. That is observed
  behaviour for this bank, not a statement that the renderer is required for every voicebank.
- The phonemizer stayed `OpenUtau.Core.DefaultPhonemizer` after import and after singer selection (this
  bank defines none) and sufficed to render the research notes. That does not make it appropriate for
  English lyrics; that was not tested.
- `File > Export Audio > Export Wav Files To...` writes one WAV per track in one operation,
  `<base>_<TrackName>.wav` (mono, 16-bit, 44.1 kHz), each as long as its own part. A muted track is not
  exported; soloing exports only the soloed track; a track with no singer silently exports an empty
  46-byte WAV with zero frames and no error.

## Future requirements recorded (nothing implemented in M6)

- **Validate every expected stem before mixing.** At least: the file exists; it is a decodable WAV;
  it has nonzero audio frames; its sample format is expected or convertible; its duration and timeline
  position are plausible; and it maps to the intended voice role. A valid WAV header alone is not
  enough (the singer-less export is a valid header with no audio).
- **Manual workflow checks** the eventual handoff instructions must state: before exporting, confirm
  all four voice tracks are enabled and none is soloed, and that every track has a singer.
- **Stem durations** differ per part; whether end padding alone suffices depends on A16 (do stems
  share the global timeline origin). The eventual mixer must preserve the performed timing and not
  merely concatenate or normalise independent recordings.

## Still UNKNOWN

Sample-level alignment of each stem with the MIDI timeline (A16); suitability of the default
phonemizer for real lyrics; the effect of a manually selected phonemizer; the `Export Wav Files` and
`Mixdown To Wav File` items; and whether the MIDI channel influences import.
