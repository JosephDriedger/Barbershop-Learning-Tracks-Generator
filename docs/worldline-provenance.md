# worldline.dll: provenance of BLT's own build

Status: **blocker stays open** until an independent source/licensing review of the replacement spline is documented
(owner decision, M14). Everything below is evidence for that reviewer, not a conclusion.

## What the problem was

OpenUtau's prebuilt `worldline.dll` statically contains `tk::spline` (Tino Kluge, GPL-2.0-or-later). A GPL
component inside a DLL that BLT distributes would make the combined DLL GPL-licensed; BLT (Apache-2.0) cannot ship that
unreviewed. The rest of the DLL is permissive (World, libpyin, libgvps, libnpy, miniaudio, xxHash, Abseil, OpenUtau's MIT
glue). See `docs/m13-compliance.md`.

## What BLT builds now

`host/native/build.ps1` (called by `host/build.ps1`) builds `worldline.dll` from the same sources OpenUtau's own CMake/Bazel
files pin, with MSVC + CMake + Ninja and `/Brepro` (reproducible):

| Source | Pin | SHA-256 of the archive |
|---|---|---|
| OpenUtau `cpp/` (worldline glue, MIT) | commit `6958d68b648bdd734d1eafa9e49b02657ca9d18e` (last change of the shipped DLL) | from the OpenUtau checkout |
| World | `f8dd5fb2…` | `2054f12a…` |
| libgvps | `2f1b4106…` | `eacc4ae7…` |
| libpyin | `b3813539…` | `0510a68a…` |
| libnpy 1.0.1, miniaudio 0.11.21, xxHash 0.8.2, Abseil 20240116.1 | tags | see `host/native/prepare.py` |
| tk::spline | `5894beaf…` | `0d42b77d…`: **fetched only for the parity test; not on the product's include path and not compiled** |

`host/native/prepare.py` verifies every hash, applies OpenUtau's own patches and BLT's
`host/native/effects-natural-spline.patch`, which replaces the single use of `tk::spline` in OpenUtau's `effects.cpp`
(natural cubic spline through the tension control points) with `host/native/patched/natural_spline.h`.

## The replacement

`natural_spline.h` is a plain natural cubic spline (second derivative zero at both ends) solved with the Thomas algorithm
for the tridiagonal system, 92 lines, `Copyright 2026 Joseph Driedger`, Apache-2.0.
A natural cubic spline is textbook mathematics (Burden & Faires, *Numerical Analysis*; Press et al., *Numerical Recipes*).
What it must reproduce is a *function* (the interpolated value at a point), not code.

**Disclosure for the reviewer (corrected in M15).** The replacement was written by an AI coding assistant (Claude Code) in a session directed by the owner, and it was **not** a clean-room implementation: about 25 seconds before the file was created, the assistant had printed large parts of `tk::spline`'s `spline.h` (the equation-system set-up, the boundary-condition branches and `operator()` with its extrapolation) to see which behaviour OpenUtau relies on. The code was then written from the mathematics (second derivatives and the Thomas algorithm rather than `tk::spline`'s coefficient formulation and band-matrix solver), but a reviewer must not take that on trust. Full account, the specification, the evidence and the options (including a clean-room rewrite, or removing the interpolation because BLT never sets tension) are in [review/worldline-spline-review-packet.md](review/worldline-spline-review-packet.md).

## Evidence that it behaves the same

* `host/native/parity/main.cpp` and `compare.py`: the original `tk::spline` and the replacement are compiled into two
  programs and fed the same inputs; maximum difference 1.6e-14, tolerance 1e-12 (exactly 1.0 for tension 0).
* `host/native/parity/spec_test.cpp` + `spec_check.py` (M15): the replacement against the mathematical definition, with a dense NumPy solve as reference, 360 cases / 20,840 values including both extrapolation sides; involves no GPL code and runs in `host/native/build.ps1`.
* `tests/integration/test_selftest_e2e.py` compares the SHA-256 of all 13 rendered WAVs (`tests/golden/selftest_audio.json`)
  with those made by the stock OpenUtau DLL: byte-identical.
* `host/native/verify_dll.py` fails the build if the linker map or the DLL mentions `tk::spline` (`@spline@tk@`), if the
  exports differ from what `OpenUtau.Core` calls, or if the DLL imports anything but kernel32, msvcp140, vcruntime140 and the
  UCRT api-sets.
* `host/verify-host.ps1` fails if the host's `worldline.dll` is not the one recorded in `blt-host-build.json`.

## What is still open

1. Independent review (see above). Who: someone who has not read `tk::spline`, with the two files and this page.
2. PLATINUM files in World carry only "Copyright 2012-2015 Masanori Morise. All Rights Reserved." and ship in World's
   BSD-3-Clause archive; low residual risk, noted in `packaging/components.json`.
3. The native build is reproducible on this machine (`/Brepro`); a second-machine rebuild has not been compared.

To audit the claim yourself: `powershell -File host/native/build.ps1 -OpenUtauSrc <checkout> -Out <dir>`, then
`python host/native/verify_dll.py <dir>/worldline.dll`.
