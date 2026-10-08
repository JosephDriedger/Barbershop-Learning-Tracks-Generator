# M7a spike report: unattended synthesis feasibility

Status: **report for review; recommendation GO (with conditions).** The host is throwaway research code
(`spikes/m7a/`), not production, not built in CI.

## Environment (recorded)

- OpenUtau release 0.1.565, source commit `a60ca5830b9064556157245d4bf8f5920d93e5f8` (verified with
  `git rev-parse HEAD`); `OpenUtau.Core` and `OpenUtau.Plugin.Builtin` are built from that commit
  (netstandard2.1), referenced by a .NET 8 console host.
- Microsoft .NET SDK 8.0.425 (runtime 8.0.31), per-user install from Microsoft's Authenticode-signed
  `dotnet-install.ps1`; no system-wide install, no other dependency installed.
- Windows 11, ALYS DB002 FRA (user-provided research voicebank; not bundled), input: the project
  OpenUtau 0.1.565 saved for the A16 stem-alignment experiment.
- Everything downloaded, built or rendered is in git-ignored `research-output/spike/`.

## Acceptance criteria and results

| Criterion | Result |
|---|---|
| Starts without the OpenUtau GUI | Yes: a console host; `MainWindowHandle` is 0; no window appears |
| Loads the known-good USTX | Yes (`Ustx.Load`) |
| Resolves the installed ALYS singer | Yes, after mirroring the GUI initialisation (see below) |
| Resolves the stored phonemizer | Yes, checked explicitly (OpenUtau would otherwise fall back silently) |
| Four nonempty decodable WAV stems | Yes: mono, 16-bit, 44.1 kHz; 66151, 88201, 110251, 132301 frames (1.5, 2.0, 2.5, 3.0 s) |
| Track identity and order | Yes: files `<base>_Tenor/Lead/Baritone/Bass.wav`, same names as the GUI export |
| Global timeline origin preserved | Yes: first audio at 0.0, 0.4, 0.9, 1.4 s, identical to the GUI stems (A16) |
| Timing and pitch consistent with the GUI | Yes: equal format and frame counts; equal onsets; samples bit-identical to the GUI export when OpenUtau's render cache is warm, and within 1 LSB (16-bit) of it on a cold cache |
| No visible OpenUtau window | Yes |
| Missing singer is a nonzero failure | Yes: exit 4, no stems; same for no singer stored (`(none stored)`) and for an unresolvable phonemizer |
| Cancellation | Process-level only, see below; clean-up by staging directory works |
| Reproducible | Yes: cold cache, 4 runs bit-identical; warm cache, 6 runs bit-identical; a 4-minute project, 2 runs bit-identical |
| Packaging dependencies identified | Yes, see below |
| Startup time, memory, output size measured | Yes, see below |

## What had to be discovered (all in the host, none in OpenUtau)

1. The GUI splash initialises `ToolsManager` (registers the `worldline` resampler), `SingerManager`,
   then `DocManager.Initialize(thread, scheduler)`; without `ToolsManager` the render fails with
   `KeyNotFoundException: 'worldline'`.
2. `DocManager` posts work to a "main thread"; headless, the host owns a work queue and pumps it while
   waiting (a naive "run it inline" post recurses until a stack overflow).
3. `Encoding.RegisterProvider(CodePagesEncodingProvider.Instance)` is required first: voicebank text
   files are Shift-JIS and the singer is silently missing otherwise.
4. The native `worldline.dll` (from the source tree's `runtimes/win-x64/native`) must sit beside the host;
   warm-cache runs hide its absence (nothing needs resampling).
5. Windows data-path rule: `installed.txt` next to the **process executable** selects the per-user data
   directory, otherwise data (singers, cache) lives beside the executable. Launching through
   `dotnet host.dll` looks beside `dotnet.exe` instead.
6. `PlaybackManager.RenderToFiles` is the only public render entry point at this commit; it swallows
   exceptions into `ErrorMessageNotification`; `RenderEngine` is internal.
7. An unknown singer becomes a "missing" placeholder and an unknown phonemizer becomes the default one,
   silently; the host checks both and exits 4.

## Measurements

| | warm cache (per-user data) | cold cache (portable layout) |
|---|---|---|
| 4-bar quartet, process wall time | 0.55 s | 1.55 s |
| Render phase | about 0.28 s | about 1.3 s |
| Peak working set | 79 to 88 MB | 102 MB |
| 60 x 4-bar repeats (about 4 minutes per stem) | 0.95 s, 205 MB | 1.96 s, 205 MB |
| Output | 4 stems, 794 KB | 4 stems of about 20 MB each |

Initialisation is about 20 ms, singer search about 100 ms, project load about 30 to 130 ms.
Cache: the render cache lives in the data directory; 4 entries, 0.5 MB for the test project.

## Cancellation

OpenUtau 0.1.565 exposes no public cancellation for export rendering (the cancellation token is a
private field of `PlaybackManager`, and `StopPlayback` only stops audio output). Cancellation is
therefore process termination plus staging: stems are rendered into `OUT/.staging-<pid>/` and moved to
`OUT` only when all exist. Killing the host at 350, 450, 550 and 650 ms (mid-phonemize and mid-render)
left zero stems under final names, a staging directory with 0 to 4 partial WAVs, no child processes and
no leftover host process. The orchestrator must delete the staging directory. A cooperative cancel
would need either reflection on a private field (rejected) or an upstream change.

## Packaging

- Framework-dependent build: 91 files, 92.7 MB; needs a .NET 8 runtime.
- **Self-contained publish (win-x64): 257 files, 125.4 MB**, runs with no .NET installed (0.82 s warm).
  Trimming and size reduction were not attempted.
- Needed at run time: the host and the `OpenUtau.Core` / `OpenUtau.Plugin.Builtin` assemblies, their
  NuGet dependencies (122 packages incl. the framework), native `worldline.dll`, ONNX Runtime /
  DirectML natives (pulled in by Core; unused for classic UTAU banks but part of the dependency set), the
  user-provided voicebank, and a writable data directory (singers, cache).
- Layout choice for production: portable (data beside the host, BLT-owned `Singers/`) is the cleaner
  fit; it needs the singer copied or linked there and a cold render cache the first time.

## Licensing

- OpenUtau is MIT (`LICENSE.txt`, checked in the pinned source). The host adds no code from it.
- Runtime NuGet packages (read from the packages' own nuspec files): predominantly MIT, Apache-2.0,
  BSD or MS-PL. Items needing a real review before any redistribution: **NetMQ 4.0.1.13 (LGPL)** and
  **AsyncIO (no licence declared in its nuspec)**, both used for OpenUtau's ENUNU/DAW networking and
  pulled in by Core; **NaCl.Net (MPL-2.0)**; **UTF.Unknown** (licence URL only); the Microsoft
  **ONNX Runtime / DirectML** redistribution terms; and the native `worldline` library, built from the
  repository's `cpp/` with third-party code (WORLD, libpyin, libgvps, miniaudio, spline) whose licences
  were not individually audited here. None blocks the spike; all block "ship it" until audited.
- **ALYS is not redistributed**; its licence permits UTAU, OpenUTAU and Plogue Alter/Ego use and forbids
  redistribution. A dependency's permissive licence does not cover voicebanks, and BLT will make no
  such claim.

## Caveats and what the spike does not show

- Only the classic UTAU path (`WORLDLINE-R`) with one French voicebank was exercised; DiffSinger,
  ENUNU, Vogen and VOICEVOX renderers were not.
- The headless render uses undocumented internals (`OpenUtau.Core` is UNDOCUMENTED as an embedding API);
  the host depends on the initialisation order and singletons above, which can change between releases.
  Mitigation: one pinned tag, a thin adapter, and the A/B/C observations rerun as contract tests.
- Cold-cache output differs from GUI-cached output by at most 1 LSB. Cause not isolated (probably
  quantisation in the render cache); bounded and deterministic (4 cold runs identical).
- Lyric tokens `+` / `+~` and English pronunciation were not tested (not an M7a question).

## Recommendation

**GO.** All required criteria are met with measured evidence: unattended, windowless, deterministic,
GUI-equivalent stems, failure surfaced as nonzero exits, and clean cancellation by process end plus
staging. Conditions for M7b/M8: pin 0.1.565 (commit above); package the portable layout; treat
cancellation as process termination; run the licence audit listed above before any distribution;
keep the A-series observations as contract tests; and keep the manual-assisted workflow as the fallback
if a future OpenUtau release breaks the embedding.
