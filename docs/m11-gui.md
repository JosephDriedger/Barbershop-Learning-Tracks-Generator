# M11: the desktop application

`barbershop-tracks-gui` (or `python -m barbershop_tracks`) opens the BLT Music Generator window. It is
a front end for the M10 pipeline: it never re-implements parsing, planning, rendering or mixing, and
nothing musical is decided for the user.

## What a singer does

1. **Score**: *Choose score* (or drag a `.musicxml`, `.xml` or `.mxl` file onto the window). The title,
   file name and detected parts (with note counts) appear.
2. **Voice Assignment**: every part has a *Sings as* choice: Tenor, Lead, Baritone, Bass or *Ignore
   this part*. A voice that is already used by another part is greyed out in the other rows; incomplete
   choices are explained immediately. *Suggest voices* fills in likely voices from the part names, marks
   them *suggested*, and generation stays blocked until you confirm them (*Confirm suggestions*) or
   change the rows yourself. Your choices are kept if you reopen the same score during the session.
3. **Singing Voices**: a voices folder (found automatically in OpenUtau's default location if it
   exists, or chosen with *Browse*) is scanned in the background; each part has its own voice selector.
   Nothing is pre-selected, even when only one voice is installed. *Same voice for all parts* copies the
   Tenor's voice. A saved voice that is no longer installed is shown as "(not installed)" and blocks
   generation instead of being replaced. *Refresh* rescans. *Advanced...* holds pronunciation, voice
   engine, singing-engine folder, .NET runtime folder and time limit; empty means the default.
4. **Lyrics and Validation**: plain-language findings about the score (missing tempo, missing time
   signature, unassigned lines, undecided lyrics). *Show technical details* has the codes. If notes have
   no lyric, *Review lyrics (N notes)...* opens the lyric review.
5. **Output Settings**: output folder, package name (defaults to the score's file name), format (WAV,
   MP3, both), MP3 quality, FFmpeg location (MP3 only; BLT never ships FFmpeg), mix balance (three
   presets or *Custom* featured/other loudness, validated), keep the four recordings, keep the project
   file, and *Replace existing tracks*. The exact folder the tracks will be saved in is always shown.
6. **Generate learning tracks** is enabled only when everything is decided; otherwise the text beside it
   lists what is missing. **Generation Progress** shows the current step, a list of steps, elapsed time,
   a *Cancel generation* button and an expandable technical log. On success: how many tracks, in which
   formats, where, and *Open output folder*.

## Lyric review

The table lists exactly the notes with no decided lyric, so a lyric the score provides can never be
changed or hidden here. Columns: voice, where (bar and beat), pitch, length, why it needs a lyric, what
the Lead sings at that moment (reference only), BLT's suggestion if any, the lyric (editable), status.

* Typing a lyric makes a **draft**; only **Approve** makes it count. Changing an approved lyric makes it a
  draft again. Text the singing engine cannot take (`+`, `-`, brackets, non-ASCII, ...) is marked
  *Cannot be sung* and cannot be approved.
* Batch actions work on the selected rows and never on their own: *Approve selected*, *Approve all
  typed*, *Un-approve*, *Type one lyric for selected*, *Use suggested lyrics*, *Copy the Lead's words*
  (asks to confirm; the copies are still drafts), *Clear selected*.
* *Approved by* names who decided (default: the Windows user name).
* *Load/Save approvals* use the M10 file format (`blt.lyric-approvals/1`) and are bound to the score by its
  SHA-256: approvals made for another version of the score are refused; entries for notes that do not need
  a lyric are counted and ignored. *Export report* writes the M10 review report (`blt.lyric-review/1`).
* *Done* applies the approved lyrics; *Cancel* restores the decisions as they were.
* Approvals are never stored between runs and are dropped when the score or the voice assignment
  changes. A score with unresolved lyrics cannot start generation (the button is disabled and the controller
  refuses a stray call), so no audio is produced for it.

## Failures

The window explains each kind in its own words, with steps, and keeps the technical text one click away:
unreadable score; missing tempo; missing time signature; incomplete voice assignment; notes still needing
lyrics; missing singing voice or voices folder; invalid engine setting; FFmpeg missing or failing; existing
package; singing engine failure; silent or wrong recording; timeout; cancellation. Success is shown only
after the package has been published and verified by the pipeline.

## Architecture

```
ui/main_window.py   the window: wiring, drag and drop, close handling (no logic)
ui/sections.py      the six sections (display only; refresh from the controller)
ui/dialogs.py       lyric review dialog (table model), advanced settings
ui/controller.py    AppController: state, background tasks, blockers, request building
ui/background.py    Dispatcher: runs work on pool threads, delivers results on the GUI thread
ui/assignments.py   AssignmentState (pure)        ui/lyric_review.py LyricReviewState (pure)
ui/explain.py       PipelineError -> plain words  ui/formatting.py   bars, beats, note names
ui/preferences.py   QSettings (per user)          ui/prompts.py      file dialogs, open folder
core/pipeline       generate(), prepare(): the same code the command line uses
```

* **Threads.** Loading and validating a score, scanning voices and the whole generation run on a
  `QThreadPool`; results and every pipeline event come back through signals of a dispatcher that lives in
  the GUI thread (queued), so widgets are only touched from the GUI thread (tested). A newer validation
  supersedes an older one, so stale results never apply to a different score.
* **Cancellation.** The button sets the M10 `CancelToken`; it ends the render host's process tree and
  FFmpeg exactly as in the command line. Closing the window during a run asks first, then cancels and waits.
* **Duplicate clicks.** Generate is disabled while running, and the controller refuses to start a second
  run or any run that still has a blocker.
* **Progress.** A counted bar only for the 13 mixes (and MP3 files); other steps show a busy indicator,
  never an invented percentage.
* **Settings** (QSettings, per user): last score folder, output folder, voices folder, FFmpeg path, format,
  mix balance and custom gains, MP3 quality, keep options, advanced engine settings, chosen voices, window
  geometry and splitter. Not stored: staging paths, assignments, lyric approvals, anything about a score.
* **Look.** Fusion style on the system palette, sizes from the font (Windows display scaling and larger
  text carry through), two scrollable columns in a splitter, no fixed window size (minimum 780 x 540),
  mnemonics and accessible names on controls, keyboard navigation by the normal tab order.

## Tests

`tests/unit/ui` (about 160, pytest-qt, offscreen): the pure models, explanations, preferences, the
controller with the real parser and a fake pipeline, the window and the lyric dialog driven like a user
(startup, drag and drop, assignment, voices, output options, progress, cancellation, every error kind,
duplicate click, thread safety, persistence, reopening the folder, replace confirmation, lyric workflow).
`tests/integration/test_gui_e2e.py` runs the whole workflow against the real pipeline, host and a
generated voicebank (no ALYS): generate and open the folder, lyric review then generate, cancellation
leaving no package, and a voice that cannot sing a syllable. It runs in CI.

## Known limitations

* Windows only; no installer yet (M12), and the dependency licence audit is still incomplete: nothing here
  claims the application is ready to distribute.
* A syllable the voicebank lacks is found after rendering, not before; the lyric review cannot tell
  whether a typed lyric is pronounceable by the chosen voice.
* No playback or preview of the generated tracks, no editing of the score, no per-part singer presets.
* High-contrast and screen-reader behaviour rely on Qt's standard accessibility; they were reviewed by
  reading the widget tree, not with a screen reader.
* The window is laid out for roughly 1100 x 700 and up; smaller windows scroll rather than clip.
