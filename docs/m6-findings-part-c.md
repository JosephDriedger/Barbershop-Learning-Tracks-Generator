# M6 Part C findings: USTX and the automation boundary

Tested and read: OpenUtau `0.1.565+a60ca5830b9064556157245d4bf8f5920d93e5f8` (Windows 11) for the
empirical parts; the `stakira/OpenUtau` repository (master, as read on the day of research) and its
wiki for documentation and source evidence. Structured records: `tests/fixtures/openutau/observations/C0*.json`.
Statements about OpenUtau are about those versions, not timeless.

Two questions are kept apart throughout: **project-file compatibility** (can a project file we write be
loaded and rendered by OpenUtau?) and **unattended rendering** (can the render run with no GUI
interaction?). Only the first has evidence in favour so far.

| Experiment | Classification | One line |
|---|---|---|
| C01 USTX structure | MATCH | saved structure matches the wiki's field descriptions |
| C02 stability | UNKNOWN | documented, but no stability promise found; version drifts |
| C03 round trip | MATCH | OpenUtau reopens its own file; a script-edited file loads and renders |
| C04 minimality | UNKNOWN | not tested |
| C05 singer portability | WORKFLOW_REQUIREMENT | singer is the voicebank folder-name id; installation-specific |
| C06 phonemizer portability | BENIGN_DIFFERENCE | a fully qualified class name, not a path |
| C07 automation | NOT_FOUND | no documented or stable interface for unattended render |

## USTX (project-file compatibility)

- YAML (UTF-8). `resolution: 480`. Tempo is `tempos: [{position, bpm}]` in ticks; meter is
  `time_signatures: [{bar_position, beat_per_bar, beat_unit}]` (bar index, not ticks). Root `bpm`,
  `beat_per_bar` and `beat_unit` are legacy (the wiki calls them deprecated).
- Track: `singer` (a string id, absent when none), `phonemizer` (class name string),
  `renderer_settings.renderer`, `track_name`, `mute`, `solo`, `volume`, `pan`, and others.
- Part: `name`, `track_no`, `position`, `duration`, `notes`. Note: `position`, `duration`, `tone`
  (MIDI number), `lyric`, `pitch`, `vibrato`, `phoneme_expressions`, `phoneme_overrides`. No velocity.
- **Version drift:** the wiki documents `ustx_version` 0.6, release 0.1.565 saves 0.7, the repository
  source is at 0.10. The loader upgrades older projects and rejects projects newer than the software.
  This is source behaviour, not a promise.
- **Compatibility evidence (C03):** a project saved by OpenUtau reopened with singer, renderer and
  phonemizer intact. A copy edited by script (tempo 120 to 90, all lyrics `a` to `la`) loaded and
  exported stems ending at exactly the 90 BPM positions (2.0, 2.667, 3.333, 4.0 s). The GUI was still
  used to open and export, so this is not evidence of unattended rendering.
- **Singer reference:** the folder name inside the singers directory (`alys-db-002-fra`). A missing
  singer is not an error in the GUI export path: it writes an empty WAV (A15).
- **Phonemizer reference:** a class name (`OpenUtau.Core.DefaultPhonemizer`). The Phonemizer API is
  documented as "Experimental. Subject to change", so names are only as stable as that.
- Saving the singer also set the track renderer to `WORLDLINE-R` in this case (A13).

## Automation surfaces (evidence and classification)

| Surface | Class | Notes |
|---|---|---|
| `OpenUtau.exe` command line / headless | NOT_FOUND | `Program.Main` hands args to the UI lifetime; nothing parses them; a second instance exits; no wiki page documents it |
| USTX file format | DOCUMENTED_EXPERIMENTAL | wiki page; no stability promise; version drift |
| Phonemizer API | DOCUMENTED_EXPERIMENTAL | README: experimental; for plugin authors |
| Editing macros API | DOCUMENTED_EXPERIMENTAL | in-GUI macros, not a render path |
| Resampler / wavtool protocol | DOCUMENTED_STABLE | long-standing UTAU convention; one stage only (per-note resampling) |
| DAW integration TCP API v1.2 | DOCUMENTED_EXPERIMENTAL | OpenUtau is the client of a plugin server; needs a running GUI; no render-to-file command; not verified present in 0.1.565 |
| `IRenderer` / singer type interfaces | DOCUMENTED_EXPERIMENTAL | for engine authors; silent on stability and headless use |
| `OpenUtau.Core` as an embedded library | UNDOCUMENTED | exists, MIT licensed, no UI dependency, driven headlessly by the repository's own tests; render code (`PlaybackManager.RenderToFiles`, `RenderEngine`) depends on the `DocManager` singleton and a `TaskScheduler` (`DocManager.Initialize(Thread, TaskScheduler)`); not offered as an API |

`NOT_FOUND` means the sources listed were searched and no stable interface was found; it does not
prove none exists.

## Not established

C04 (what a project may omit); whether released 0.1.565 and master behave the same for any internal
API; whether `OpenUtau.Core` runs headlessly on this machine (no .NET SDK is installed here, so no
spike has been run; this needs approval to install one).
