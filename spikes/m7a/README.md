# M7a spike: headless OpenUtau.Core render host (throwaway, not production)

A bounded proof of concept for `docs/m7-m12-plan.md`. It is **not** production code, is not built in
CI, and must not be described as production-ready. Nothing here ships: the downloaded SDK, the
OpenUtau source checkout, build output, voicebanks and rendered audio all live in the git-ignored
`research-output/spike/` and are never committed. Results: `docs/m7a-spike-report.md`.

## Pinned inputs

- OpenUtau release **0.1.565**, commit `a60ca5830b9064556157245d4bf8f5920d93e5f8`
  (`git clone --branch 0.1.565 --depth 1 https://github.com/stakira/OpenUtau.git` into
  `research-output/spike/OpenUtau-src`; verify `git rev-parse HEAD`).
- Microsoft .NET SDK **8.0.425** (runtime 8.0.31), installed per user with Microsoft's signed
  `dotnet-install.ps1` into `research-output/spike/dotnet` (nothing system-wide).

## Build and run (Windows PowerShell)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File spikes\m7a\build.ps1
$env:DOTNET_ROOT = "$PWD\research-output\spike\dotnet"
research-output\spike\host-build\blt-spike-renderhost.exe `
    --project PROJECT.ustx --out OUTDIR --base NAME
```

stdout is one JSON document; exit codes: 0 ok, 2 usage, 3 project load failure, 4 singer or phonemizer
unresolved, 5 render or export failure, 6 reserved for cancellation, 7 phonemization timeout.
Stems are rendered into `OUTDIR/.staging-<pid>/` and moved to `OUTDIR` only after every expected stem
exists; a killed run leaves only the staging directory, which the caller removes.

## Layout notes learned the hard way

- OpenUtau decides between "portable" (data beside the executable) and "installed" (per-user data
  directory) by `installed.txt` next to the **process executable**; run the host's own `.exe`, not
  `dotnet host.dll`. `build.ps1` writes an `installed.txt` so the host sees the user's singers; for a
  portable layout, omit it and put singers in `Singers/` beside the host.
- The native `worldline.dll` must sit beside the host (the GUI's project copies it from `runtimes/`).
- Initialisation order must mirror the GUI splash window: code-page encoding provider, `ToolsManager`,
  `SingerManager`, then `DocManager` with a main-thread queue that the host pumps.
- `PlaybackManager.RenderToFiles` reports failures as notifications and does not throw; the host
  subscribes to them. An unknown singer or phonemizer is replaced silently by OpenUtau, so the host
  resolves both itself and exits 4.
