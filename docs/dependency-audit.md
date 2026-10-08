# Dependency audit ledger (M7b)

Status: **working ledger, not a legal review. Nothing here claims the application is ready to
distribute.** Evidence is what was read from NuGet metadata (`.nuspec`), the license files inside the
cached packages, and the pinned OpenUtau checkout (release 0.1.565, commit
`a60ca5830b9064556157245d4bf8f5920d93e5f8`) on 2026-10-07. Where nothing was read, the entry says
`UNKNOWN`. NuGet `licenseUrl`-only entries are metadata claims, not verified licence texts.

BLT does **not** bundle any voicebank (ALYS or otherwise) and this ledger must stay true to that.
The spike host and all packages below live only in the git-ignored `research-output/`; nothing in
this table is currently shipped by the BLT repository.

Intended use: "host" = linked into the BLT-owned render host (M8) that runs OpenUtau.Core headlessly.
Redistribution means shipping the DLL/native file inside the Windows installer (M12).

## OpenUtau and its native code

| Component | Version | Licence evidence | Intended use | Redistribution notes |
|---|---|---|---|---|
| OpenUtau.Core, OpenUtau.Plugin.Builtin | 0.1.565 (`a60ca58…`) | `LICENSE.txt` in the checkout: MIT, "Copyright (c) 2014 StAkira" (read) | host references it | MIT: keep notice. Plugin.Builtin carries many per-language phonemizers; per-file licence headers were **not** audited: UNKNOWN |
| worldline.dll (native resampler) | built from `cpp/worldline` of the same commit; the prebuilt `runtimes/win-x64/native/worldline.dll` is what the spike copied | the OpenUtau MIT licence covers the worldline sources; the prebuilt binary's build provenance is **not verified**: UNKNOWN | host, beside the exe | needs the third-party notices below before any redistribution |
| world | `mmorise/World` @ `f8dd5fb…` (WORKSPACE.bazel) | UNKNOWN (not read) | linked into worldline | UNKNOWN |
| libpyin | `Sleepwalking/libpyin` @ `b381353…` | UNKNOWN | linked into worldline | UNKNOWN |
| libgvps | `Sleepwalking/libgvps` @ `2f1b410…` | UNKNOWN | linked into worldline | UNKNOWN |
| spline | `ttk592/spline` @ `5894bea…` | UNKNOWN | linked into worldline | UNKNOWN (a copyleft licence would matter; must be read) |
| libnpy | `llohse/libnpy` v1.0.1 | UNKNOWN | linked into worldline | UNKNOWN |
| miniaudio | `mackron/miniaudio` 0.11.21 | UNKNOWN | linked into worldline | UNKNOWN |

## Packages OpenUtau.Core pulls in (versions as resolved by the spike build)

| Package | Version | Licence evidence (nuspec / file) | Intended use | Redistribution notes |
|---|---|---|---|---|
| NetMQ | 4.0.1.13 | `licenseUrl` → `COPYING.LESSER` (LGPL, version not read) | pulled by OpenUtau.Core (inter-process messaging, unused by the host) | LGPL obligations (relinking/replaceability) apply if shipped: **UNKNOWN whether removable**; needs a decision |
| AsyncIO | 0.1.69 | nuspec has no licence field; repo https://github.com/somdoron/AsyncIO | transitive of NetMQ | UNKNOWN |
| NaCl.Net | 0.1.13 | nuspec licence expression `MPL-2.0` | transitive of NetMQ | MPL-2.0 file-level copyleft; keep notice and source availability for modified files |
| UTF.Unknown | 2.5.1 | `licenseUrl` → `MPL-1.1.txt` in upstream repo (metadata only) | text-encoding detection | MPL-1.1 notices; verify |
| Microsoft.ML.OnnxRuntime (managed) | 1.16.3 | `LICENSE.txt` in package: MIT | neural renderers (unused by our CLASSIC/WORLDLINE-R path, but loaded by Core) | MIT |
| Microsoft.ML.OnnxRuntime.DirectML | 1.16.3 | `LICENSE` in package: MIT | same | MIT; native `onnxruntime.dll` third-party notices (`ThirdPartyNotices`) not read: UNKNOWN |
| Microsoft.AI.DirectML | 1.12.1 | `LICENSE.txt`: "MICROSOFT SOFTWARE LICENSE TERMS, DIRECTX MACHINE LEARNING (DIRECTML)" (proprietary terms, headline read only) | transitive of the DirectML package | **Redistribution terms not analysed: UNKNOWN**; could be avoided only by not shipping it |
| Concentus / Concentus.OggFile | 2.2.1 / 1.0.6 | Concentus: package `LICENSE` lists several holders (Skype, Xiph, Microsoft…); OggFile: nuspec `MS-PL` | audio decode | notices required; terms of the first not fully read |
| BunLabs.NAudio.Flac | 2.0.1 | nuspec `MS-PL` | audio decode | MS-PL |
| NAudio, NAudio.Core/Asio/Midi/Wasapi/WinMM/WinForms | 2.2.1 | nuspec `MIT` (`license.txt` in NAudio: Mark Heath) | audio IO | MIT |
| NAudio.Vorbis / NVorbis | 1.5.0 / 0.10.4 | nuspec `MIT` / `LICENSE` MIT (Andrew Ward) | decode | MIT |
| NLayer / NLayer.NAudioSupport | 1.15.0 / 1.4.0 | nuspec `MIT` | MP3 decode | MIT (the MP3 format's patent status is not assessed) |
| NWaves | 0.9.6 | nuspec `MIT` | DSP | MIT |
| NumSharp | 0.30.0 | package `LICENSE`: Apache-2.0 text | numerics | Apache-2.0 |
| Melanchall.DryWetMidi | 7.2.0 | nuspec `MIT` (also ships native libs `Melanchall_DryWetMidi_Native*`) | MIDI | MIT |
| Newtonsoft.Json | 13.0.3 | nuspec `MIT` | JSON | MIT |
| Serilog | 4.1.0 | nuspec `Apache-2.0` | logging | Apache-2.0 |
| SharpCompress | 0.38.0 | nuspec `MIT` | archives | MIT |
| YamlDotNet | 15.1.2 | package `LICENSE.txt`: MIT-style (Antoine Aubry) | YAML | MIT |
| csharp-kana, csharp-pinyin | 1.0.2 / 1.0.0 | nuspec `Apache-2.0` | phonemizer helpers | Apache-2.0 |
| WanaKana-net | 1.0.0 | nuspec `MIT` | phonemizer helper | MIT |
| Ignore | 0.1.50 | nuspec has no licence field; repo goelhardik/ignore | gitignore-style matching | UNKNOWN |
| K4os.Hash.xxHash | 1.0.8 | `licenseUrl` only (upstream `LICENSE`, not read) | hashing | UNKNOWN |
| Vortice.DXGI / DirectX / Mathematics, SharpGen.Runtime(.COM) | 2.4.2 / 2.4.2 / 1.4.25, 2.0.0-beta.13 | nuspec `MIT` | DirectX interop | MIT |
| ZstdSharp.Port | 0.8.1 | nuspec `MIT` | compression | MIT |
| Microsoft.* / System.* (BCL packages) | various | nuspec `MIT` (Microsoft.Bcl.*, runtime packs) | runtime | MIT; .NET runtime redistribution terms to be confirmed at M12 |

## Python side (for completeness)

| Package | Use | Status |
|---|---|---|
| PySide6 | GUI | LGPL-3.0 / commercial; obligations analysed at M12: UNKNOWN until then |
| defusedxml, mido, platformdirs | runtime | permissive; not re-audited here |
| FFmpeg | external, user-configured (never bundled before the M12 evaluation) | UNKNOWN (build-dependent: LGPL vs GPL) |

## Not shipped, by policy

ALYS DB002 FRA and every other voicebank: user-installed, user-licensed (ALYS terms permit UTAU,
OpenUTAU and Plogue use; forbid redistribution here). BLT neither bundles, copies per render, nor
commits any voicebank.

## Open items before any distribution decision (M12)

1. Read the licences of world, libpyin, libgvps, spline, libnpy and miniaudio (or rebuild worldline
   from audited sources and record the build).
2. Decide how NetMQ (LGPL) is handled: replaceable-DLL compliance, or exclude the messaging code path.
3. Resolve the DirectML redistribution terms or avoid shipping that package.
4. Audit Plugin.Builtin per-file licences.
5. Re-run this ledger from the actual published host output, not from the spike's package cache.
