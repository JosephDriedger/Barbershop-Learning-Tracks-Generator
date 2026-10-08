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
