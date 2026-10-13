# Troubleshooting

First, two quick checks that answer most questions:

* **Help > Copy diagnostics** in the app, or `blt.exe diagnostics` in a terminal: shows where BLT found
  its singing engine, your voices folder, FFmpeg and its settings. Paste it into any support request.
* `blt.exe selftest`: builds a tiny score with a built-in test voice and makes the 13 files. If it prints
  "selftest passed", the installation is fine and the problem is with the score, the voicebank or the settings.

(`blt.exe` is in the install folder, by default `%LOCALAPPDATA%\Programs\BLT Music Generator`.)

## The installer

**"Windows protected your PC" (SmartScreen).** The installer is not code-signed, so Windows does not know
who made it. Check that the file's SHA-256 matches the checksum published with it
(`Get-FileHash .\BLT-Music-Generator-<version>-Setup.exe -Algorithm SHA256`), then choose *More info* and
*Run anyway*. If you cannot verify where it came from, do not run it.

**Antivirus quarantines BLT or reports a threat.** Programs built with PyInstaller are sometimes flagged
heuristically. Compare the checksum, and if you trust it, restore it and add the install folder and
`%LOCALAPPDATA%\BarbershopLearningTracks` to the antivirus exclusions. Report the false positive to the vendor.

**Setup asks for administrator rights.** Only if you chose "install for all users". Choose "only for me".

**Nothing happens when I start it from the Start menu.** Run `blt.exe selftest` and read what it prints. If
the GUI will not open but selftest works, run `"BLT Music Generator.exe" --smoke-test` and send the diagnostics.

## Voices

**No voices are listed.** BLT looks in `Documents\OpenUtau\Singers` unless you chose a folder in the Voices
section. The folder must contain voicebank folders (each with `character.txt` or `oto.ini`). Press *Refresh*.
BLT does not download or include voices.

**"A singing voice was not found".** The voice you chose was removed or renamed, or the voices folder moved.
Fix the folder, press *Refresh*, choose the voice for each part again.

**"A voice came out silent or wrong" / audio checks failed.** The voicebank could not sing one of the
syllables (often a lyric it has no sound for, or a language mismatch with the pronunciation engine). Open
*technical details* to see which part and notes, change those lyrics in *Review lyrics…*, or try another voice
or a different pronunciation engine in *Advanced…*. Nothing is saved from a failed run.

## Score and lyrics

**Generate is disabled.** The window says why, next to the button: parts not assigned, a voice not chosen,
lyrics still to review, no output folder, or MP3 selected without FFmpeg.

**Lyrics need review.** A part's notes with no lyric follow the Lead automatically where the Lead is singing. What is
left (the Lead rests or is itself missing words, humming, elisions, or conflicting lyrics) needs a decision. Use
*Review lyrics…*; each choice is remembered with the package so the result can be reproduced. If a part should
not follow the Lead, type its own words in the review, or switch the convention off in *Advanced…* (command line:
`--no-follow-lead`; environment: `BLT_FOLLOW_LEAD=0`).

**Not four parts / parts not recognised.** BLT needs exactly four lines for Tenor, Lead, Baritone, Bass. Use
*Suggest voices*, or assign each line yourself; ignore extra lines (piano reductions).

## Output

**MP3 needs FFmpeg.** BLT does not include FFmpeg. Install it yourself and choose *Choose FFmpeg…*, or pick WAV.

**"That package already exists" / "A folder with that name already exists".** Tick *Replace existing tracks* for
a package BLT made earlier, or change the package name or output folder. A folder BLT did not make is never
overwritten.

**It is slow the first time.** The first generation copies BLT's singing engine to your user folder (a few
seconds); long songs take proportionally longer to sing. Later runs reuse the copy.

## "Microsoft Visual C++ runtime is missing"

BLT needs Microsoft's Visual C++ Redistributable (x64), version 14.44 or newer, and does not contain it. If Setup or BLT
says it is missing or too old, install the current `vc_redist.x64.exe` from Microsoft
(https://aka.ms/vc14/vc_redist.x64.exe, or on another PC for offline use: see [INSTALL.md](INSTALL.md)), then start BLT again.
`blt.exe diagnostics` prints the *vc runtime* line with the version it found. An error such as "DLL load failed while
importing QtWidgets" at start-up on a freshly set-up PC is the typical symptom of a missing or damaged runtime.

## "A BLT component is missing" / the singing engine cannot start

Run `blt.exe diagnostics`. The line *render host* must name a folder; if it says NOT FOUND, or `blt-render-host.exe`
is missing, reinstall BLT. If *runtime copy* is fine but generation still fails to start the engine, security
software may be blocking `%LOCALAPPDATA%\BarbershopLearningTracks\runtime\...\blt-render-host.exe`. Allow it.

To reset BLT's private working files (safe; they are rebuilt on demand), close BLT and delete
`%LOCALAPPDATA%\BarbershopLearningTracks\runtime`, `\staging` and `\Cache`. Your voices, tracks and settings are
not in those folders.

## Where things are

| | |
|---|---|
| Program | `%LOCALAPPDATA%\Programs\BLT Music Generator` (or the folder you chose) |
| Private working files | `%LOCALAPPDATA%\BarbershopLearningTracks` (`runtime`, `staging`, `Cache`) |
| Settings | Windows registry, `HKCU\Software\BarbershopLearningTracks`; optional `config.json` in the folder above |
| Your tracks | the output folder you chose |
| Third-party notices | `NOTICES.txt` in the program folder (Start menu: *Third-party notices*) |

When reporting a problem include: the diagnostics text, what you did, the on-screen message and the
*technical details*; never attach scores or voicebanks you may not share.
