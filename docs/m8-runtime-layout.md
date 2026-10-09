# M8a: runtime layout and production render host

## Decision

**A BLT-owned writable copy of the host binaries per host version, run in OpenUtau "portable" mode,
with the user's voicebanks supplied through `--singers-dir`.** No voicebank is copied; nothing
writable lives under the install directory; no OpenUtau GUI is needed or disturbed.

```
<install dir>\host\...              read-only (Program Files is fine): the shipped host build
%LOCALAPPDATA%\BarbershopLearningTracks\
    runtime\host-<fingerprint>\     writable copy of the host (Cache\, prefs.json, ... appear here)
    staging\.staging-<job>-<pid>\   per-render scratch (M8b)
    outputs\...                     published, validated stems
<user's singers directory>          wherever the user keeps voicebanks; passed as --singers-dir
```

`core/runtime/host_install.ensure_host_runtime` makes the copy (built under a temp name, renamed
into place, completion marker, one directory per fingerprint so a running job's directory is never
modified by an upgrade).

## What was measured (OpenUtau.Core 0.1.565, Windows 11, ALYS singer, 4 tracks of 4 notes)

| Layout | Singer discovery | Render | Writes | From a read-only host dir |
|---|---|---|---|---|
| 1a. Portable host + junction `Singers` to the user's singers | found | ok, cold 4.3 s, warm 0.6 s | `Cache\`, `prefs.json`, `notepresets.json` beside the exe | **fails (exit 8, `UnauthorizedAccessException` creating `Singers`)** |
| 1b. Portable host + `--singers-dir` (`Preferences.AdditionalSingerPath`) | found; without the flag, none found and the host exits 4 | ok, cold 4.0 s, warm 0.6 s | same as 1a | **fails** (same writes) |
| 2. Installed mode (`installed.txt`), user's `Documents\OpenUtau` | found | ok, 1.9 s (the user's cache was already warm) | into the user's OpenUtau data (cache, prefs, logs), shared with the OpenUtau GUI | **works** |

Also measured: a host directory with spaces and a non-ASCII name works (portable); the host copy is
about 94 MB and 79 files.

Reasoning:

* Portable mode needs a writable host directory, so the shipped (read-only) host cannot be run in
  place. Hence the per-version runtime copy. Copying binaries once is cheap; copying voicebanks per
  render is never done.
* Installed mode runs from a read-only directory but mixes BLT's cache and prefs into the user's
  OpenUtau data, cannot be given a cold cache without deleting the user's own cache, and would race a
  running OpenUtau GUI over logs and prefs. That fails "keep runtime data separate".
* Junction versus `--singers-dir`: both worked. The preference is OpenUtau's own supported setting,
  needs no filesystem tricks (junctions follow cloud-synced folders badly and can dangle), and is
  explicit in the host's command line, so it is the chosen mechanism. No private reflection is used.
* The GUI was not running during these measurements, so GUI coexistence is argued from the separate
  data directories, not tested.

## Production host

`host/BltRenderHost/` (net8.0, builds `blt-render-host.exe`) promotes the M7a spike. It references
the exact pinned OpenUtau source (release 0.1.565, commit `a60ca58…`, verified by `host/build.ps1`;
the commit is also baked into the assembly and reported in every result).

* Arguments: `--project`, `--out` (existing, empty, owned by the caller), `--base`, optional
  `--singers-dir`, `--phonemize-timeout-ms`, `--render-timeout-ms`. Unknown options are an error.
* Output: one JSON object per stdout line (`start`, `phase`, `progress`, `error_notification`, last
  `result`); stderr is for humans.
* Exit codes: 0 ok, 2 usage, 3 project load, 4 singer/phonemizer/renderer unresolved, 5 render
  failure (including any error notification OpenUtau raised while rendering, which the render method
  does not throw), 6 reserved, 7 phonemize timeout, 8 environment (native library, singers
  directory, initialisation), 9 render timeout, 10 internal.
* Explicit validation: every track with notes must have its singer found, its phonemizer resolved to
  the stored class and its renderer unchanged; OpenUtau's silent substitutions become exit 4.
* The host writes stems straight into `--out`; it never moves, deletes or publishes. Cancellation is
  by terminating the process (OpenUtau 0.1.565 has no public cancel).
* The host build is not part of the Python wheel; `host/build.ps1` needs a .NET 8 SDK and network
  for the pinned clone, and CI builds it.

## Reproducibility (measured)

Two cold renders are bit-identical, two warm renders are bit-identical, and a warm render differs
from a cold one by at most 1 LSB (the render cache stores 16-bit audio). Consumers must not compare
cold output with warm output byte for byte.

## Limits and unknowns

* The per-version runtime copy is never pruned automatically.
* Portable mode writes `prefs.json`/`notepresets.json` into the runtime copy; their influence on
  rendering was not found, but they are not read-only inputs.
* Concurrent hosts sharing one runtime copy (and its cache): tested in M8b.
* Windows only (`worldline.dll` win-x64).
