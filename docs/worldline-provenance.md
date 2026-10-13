# worldline.dll: provenance of BLT's own build (no spline)

Status (M16): **resolved by technical evidence.** BLT's `worldline.dll` contains no spline code of any kind: neither the GPL-licensed `tk::spline`
of OpenUtau's prebuilt DLL nor the replacement that M13-M15 had written. The one remaining concern is outside the binary: the replacement still exists
in the repository's git history (section 6).

## 1. Why there was a problem

OpenUtau's prebuilt `worldline.dll` statically contains **`tk::spline`** by Tino Kluge (`ttk592/spline`, **GPL-2.0-or-later**). It is used in exactly one
place: `GetTensionCoefficients` in `worldline/model/effects.cpp`, the "tension" voice effect (`exp()` of a spline through control points). A GPL component in
a DLL BLT distributes under non-GPL terms is not acceptable. M13-M15 replaced the library by a natural cubic spline written for BLT; its provenance was
not clean (it had been written seconds after `tk::spline`'s source had been displayed to the author, an AI assistant) and it needed a licensing review
(`docs/review/worldline-spline-review-packet.md`, now a closing record).

## 2. What BLT does now

BLT's projects never use tension. So the interpolation is **removed instead of replaced**:

* `host/native/effects-no-tension-spline.patch` (against OpenUtau's `effects.cpp` at the pinned commit): drops `#include "spline.h"` and turns
  `GetTensionCoefficients` into `return std::vector<double>(width, 1);`, the neutral envelope. (It adds `#include <algorithm>`, which the spline header had supplied.)
* `host/native/prepare.py` no longer downloads the spline library (its archive and its upstream patch are gone from the pins); `host/native/CMakeLists.txt` has no spline
  option and no spline include path.

## 3. Evidence that nothing supported is affected

| Claim | Evidence |
|---|---|
| **BLT only ever asks for tension 0** | `host/native/trace_tension.ps1` builds a throw-away DLL that logs every call and runs the whole integration suite through it. Measured on 2026-10-13 with the build that still contained the original code path: **45,624 calls, all with tension 0** (selftest, all host-contract tests, full pipeline). Why: BLT's `.ustx` files carry no curves (`"curves": []`) and `tenc`'s default is 0, so OpenUtau's WORLDLINE-R renderer passes `(0.5 - 0.5) * 200 = 0` to the native code (`WorldlineRenderer.cs`: `0.5 + 0.005 * x`, `phrase_synth.cpp`: `(tension - 0.5) * 200`) |
| **For tension 0 the original returns exactly 1.0 too** | With `value = 0` every control value is ±0, the spline through them is ±0 and `exp(±0) = 1`. So the stub is the same function on every input BLT can produce |
| **The host refuses a project that asks for tension** | `host/BltRenderHost/Program.cs` (`TensionRequested`): a part with a non-zero `tenc` curve, or a changed `tenc` default, ends with status `unsupported_tension` (exit 3, "project rejected") before anything is rendered, instead of rendering without it. Tests: `tests/integration/test_render_host.py` (three tests, including that an all-zero curve is accepted and renders byte-identically to no curve) |
| **The native effect is the neutral envelope for every input** | `host/native/tests/tension_test.cpp`, compiled with the product's `effects.cpp` by `host/native/build.ps1`: 7,800 calls over widths, sample rates, pitches and tension values (-100 ... 100), 6.3 million values, all exactly 1.0 |
| **No spline is in the binary** | `host/native/verify_dll.py` fails the build if the link map (every object file and symbol that survived linking) or the DLL's bytes contain "spline", "tk::" or "NaturalCubic" in any case. Result for the shipped DLL: "17 exports, no spline in the link map or the DLL". `blt-host-build.json` records `worldline_spline_free: true` and the release build copies it into `release-info.json`; `release_gate.py check --release` requires it |
| **The rest of the DLL is the upstream code** | the patch changes one function and one include (readable in `host/native/effects-no-tension-spline.patch`); everything else is OpenUtau's source at `6958d68` and the pinned third-party archives (SHA-256 checked) |
| **Audio is byte-identical on the regression test** | `tests/golden/selftest_audio.json`: SHA-256 of all 13 WAVs of the self-test, produced with OpenUtau's stock DLL; BLT's DLL reproduces them (`tests/integration/test_selftest_e2e.py`) |

### What the byte-identical audio does and does not prove

* **It proves**, for the self-test's score, voicebank and settings, that BLT's rebuilt DLL (without the tension effect, and with everything else rebuilt by BLT with MSVC)
  renders the same bytes as OpenUtau's prebuilt DLL: the rebuild, the compiler flags and the removal change nothing audible or inaudible *for those inputs*.
* **It does not prove** the same for other inputs (other voicebanks, pitches, lengths): for those the argument is the code diff (only the tension function changed) together
  with the call trace (that function only ever gets 0 and returns 1.0 for it).
* **It says nothing about the removed behaviour**: the self-test never uses tension, so the golden hashes could not detect a wrong tension effect. That is why the
  native test, the call trace and the host's refusal exist, and why a project with a tension curve is refused rather than rendered without it.
* Rendered phrases are cached by OpenUtau as 16-bit files; a cache hit differs from a fresh render by one least-significant bit. The tests therefore render in a fresh host
  copy, and since M16 the host discards cached phrases before it renders (see section 5).

## 4. Sources and build (reproducible)

`host/native/build.ps1` -> `prepare.py`: takes OpenUtau's `cpp/` at commit `6958d68b648bdd734d1eafa9e49b02657ca9d18e` (the last change of the shipped DLL), downloads the pinned
archives and **checks every SHA-256**, applies OpenUtau's own patches for World and libpyin and BLT's `effects-no-tension-spline.patch`, builds with MSVC + CMake + Ninja, Release, `/Brepro`
(the same sources give the same bytes).

| Source | Pin | Licence |
|---|---|---|
| OpenUtau `cpp/` (worldline glue) | commit `6958d68b…` | MIT |
| World | `f8dd5fb2…` (archive SHA-256 `2054f12a…`), with OpenUtau's patch | BSD-3-Clause (modified) |
| libgvps, libpyin | `2f1b4106…`, `b3813539…` | BSD-3-Clause |
| libnpy 1.0.1, miniaudio 0.11.21, xxHash 0.8.2, Abseil 20240116.1 | tags | MIT, public domain/MIT-0, BSD-2-Clause, Apache-2.0 |
| ~~tk::spline~~ | **not used: neither downloaded nor compiled nor on an include path** | |

The notices for what is statically linked ship in `NOTICES.txt` / `licenses/`.

## 5. A defect found while checking: re-running a score gave different bytes

While adding the "fresh host copy" requirement to the tests it turned out that **the same score generated twice gave different files**: OpenUtau caches each rendered
phrase in `Cache\wdl-<hash>.wav` as 16 bits and reuses it, and a reused phrase differs from a fresh render by one least-significant bit (measured: 105,832 of 105,841 samples of one stem differ by 1).
BLT promises reproducible tracks, so the host now deletes those cached phrases before it renders (`DiscardRenderedPhrases`, `rendered_phrases_discarded` in the result);
`tests/integration/test_render_host.py::test_the_same_project_renders_to_the_same_bytes_every_time` fails without that. Cost: a repeated generation re-renders every phrase.

## 6. What remains (source level, outside the binary)

1. **Git history.** The replacement spline (`host/native/patched/natural_spline.h`, committed in M13-M15, pushed to GitHub) is no longer in the tree but is
   in the history of `JosephDriedger/Barbershop-Learning-Tracks-Generator`, where anyone can read it under the repository's Apache-2.0 licence. If it is a derivative of `tk::spline`,
   its presence in public history is itself a distribution of GPL-derived text under the wrong licence, whatever the binary contains. Options for the owner: leave it and
   say so; or have counsel advise whether a history rewrite (removing the file from all commits, then force-pushing) is warranted. **Nothing was rewritten:** that is destructive and not approved.
2. World's PLATINUM files carry only "Copyright 2012-2015 Masanori Morise. All Rights Reserved." inside World's BSD-3-Clause archive: low residual.
3. The native build is reproducible on this machine (`/Brepro`); a second-machine rebuild has not been compared.

To audit the claims yourself: `powershell -File host/native/build.ps1 -OpenUtauSrc <checkout> -Out <dir>` (runs `verify_dll.py` and the native test), then
`host/native/trace_tension.ps1` (needs a published host).
