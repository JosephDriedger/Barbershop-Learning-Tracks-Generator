# Independent review packet: BLT's replacement for `tk::spline` in `worldline.dll`

For: a person qualified to judge software licensing and code derivation, who has **not** worked on this code.
From: the BLT project (owner: Joseph Driedger). Prepared 2026-10-13 (M15) from commit `HEAD` of the BLT repository; the exact
file hashes are in `MANIFEST.json` of the packet folder (`python packaging/review_packets.py`).

**Nothing in this packet says the licensing concern is resolved.** It is the material a reviewer needs to decide. The release gate
(`docs/release-gate.md`) keeps this item open until a signed review exists.

## 1. The question

OpenUtau's prebuilt `worldline.dll` (MIT, StAkira and contributors) statically contains **`tk::spline`** by Tino Kluge
(`ttk592/spline`, **GPL-2.0-or-later**), used in exactly one place. BLT (Apache-2.0) must not distribute that GPL code in a binary
under non-GPL terms. BLT therefore builds `worldline.dll` itself with its own natural cubic spline in place of `tk::spline`.

Please decide:

1. Is `host/native/patched/natural_spline.h` (92 lines) a *derivative work* of `tk::spline` (or otherwise carries its licence
   obligations)? Consider the disclosure in section 4, which is not favourable to a "clean room" claim.
2. If you consider the risk unacceptable, which of the options in section 8 do you advise?
3. Is anything else in the built `worldline.dll` (section 7) a concern?

## 2. What the replacement must do (mathematical specification)

Given strictly increasing knots `x_0 < … < x_{n-1}` and values `y_i`, let `h_i = x_{i+1} − x_i`, `s_i = (y_{i+1} − y_i) / h_i`.

* **Natural cubic spline.** The unique C² piecewise cubic through the points whose second derivative is zero at both ends
  (`M_0 = M_{n−1} = 0`). The inner second derivatives solve the tridiagonal system
  `h_{i−1} M_{i−1} + 2 (h_{i−1} + h_i) M_i + h_i M_{i+1} = 6 (s_i − s_{i−1})`, `i = 1 … n−2`.
  (Textbook: Burden & Faires, *Numerical Analysis*, natural spline algorithm; Press et al., *Numerical Recipes*, "cubic spline
  interpolation".) A tridiagonal system is solved by the Thomas algorithm (forward elimination, back substitution).
* **Evaluation** on interval `i` with `t = x − x_i`: `y_i + t (b_i + t (M_i/2 + t (M_{i+1} − M_i) / (6 h_i)))`,
  `b_i = s_i − h_i (2 M_i + M_{i+1}) / 6`.
* **Outside the knots** the curve continues as the tangent line of the end point (the end second derivative is zero).
* **Degenerate cases:** one point is a constant; two points are the straight line through them.

None of this is specific to `tk::spline`: it is the definition. Any correct implementation agrees to rounding.

## 3. How worldline uses it (the only call site)

`worldline/model/effects.cpp`, `GetTensionCoefficients(f0, fs, value, width)` builds knots at multiples of the pitch bin
`f0_bins = f0 / (fs/2) · width` with control values `s0 = −1.5 v` (first two knots), `s1 = 2v` or `4v` (knots up to bin 250) and `0`
(the rest, up to `width + f0_bins`), `v = value/100`, then evaluates the spline at the integers `0 … width−1` and takes `exp`.
It runs only when a render's *tension* curve is not flat.

Facts that matter for risk:

* The call site only evaluates **inside** the knots (first knot 0, last knot ≥ `width`), so the extrapolation branches are never
  reached by worldline.
* **BLT never sets tension.** The `.ustx` files BLT writes have no curves (`"curves": []`), so every render uses the default
  `tension = 0.5`, i.e. `value = 0`; then every control value is 0, the spline is identically 0 and the envelope is exactly 1.0.
  The spline therefore runs on every BLT render but with all-zero input. (`compare.py` asserts exactly 1.0 for `value = 0`.)

## 4. Provenance of the implementation (read this carefully)

* File: `host/native/patched/natural_spline.h`, header "Copyright 2026 Joseph Driedger, Apache-2.0", written 2026-10-12.
* **It was written by an AI coding assistant (Claude Code, Anthropic) working in a session directed by the owner**. The owner has declared
  themselves the copyright holder of BLT's original code; the owner's own review of this particular file is not recorded. Reviewers should take into account the open questions on the copyright status of
  machine-written code and on a model reproducing text it has seen.
* **The assistant had read `tk::spline`'s source seconds before.** The session record shows that at 22:44:29 and 22:44:37 (UTC, session log) the assistant
  printed to its terminal, from `spline.h` of the pinned archive: lines 215–262 (`set_coeffs_from_b`), the grep listing of boundary and
  extrapolation code, the body of `spline::operator()` (lines 478–501, including the left/right extrapolation formulas) and lines
  276–360 (the construction of the equation system for the classical cubic spline with its boundary-condition branches). The
  replacement file was created at 22:45:01. So the replacement was **not** written clean-room.
* Why the assistant read it: to find out which behaviour OpenUtau relies on (boundary condition, extrapolation) before replacing it.
* What differs structurally (assertions for you to check, not conclusions): `tk::spline` solves for the cubic coefficients `c_i` with
  a general band-matrix LU solver and stores `b, c, d` per knot; the replacement solves for the second derivatives `M_i` with a
  specialised Thomas elimination and no matrix class, computes `b, c, d` on the fly, evaluates interval-wise with
  `std::upper_bound`, and has its own extrapolation expressed through the end slopes. Names, comments and layout were written separately.
  What coincides is what the mathematics dictates (natural boundary, Horner-form cubic, linear continuation outside).
* The header comment says it "matches [tk::spline's] default behaviour used there". That is a statement of function, kept because
  it documents the compatibility requirement.

## 5. Source-comparison restrictions (how to do the review fairly)

* BLT does **not** include `tk::spline` in this packet and does not ask you to. You obtain it yourself from upstream:
  `https://github.com/ttk592/spline/archive/5894beaf91e9adbfdbe5c6c9a1c60770e380e8e8.zip`
  (SHA-256 of the archive `0d42b77d0f398c9ad2b7290587b625c49c39a2337f6cfa88b6a7930207d91a33`; licence terms of that file are the
  reviewer's to read: it is GPL-2.0-or-later with the author's own notes).
* Keep the two implementations separate in your own notes: compare structure, expressions, identifiers, comments and ordering; do
  not rely on the BLT author's account of differences.
* Anybody who worked on or has read the BLT replacement should not do the comparison for you. The BLT assistant and the owner are
  not independent.
* Prefer to judge the *specification first* (section 2) and check that nothing in the replacement goes beyond it.
* You may run the tests below without reading `tk::spline` at all (spec test). The parity test needs it compiled (it is compiled only
  inside that test harness, never shipped).

## 6. Evidence and how to re-run it

All commands run from the repository root on Windows with MSVC build tools (Visual Studio C++ workload), CMake, Ninja, git, Python 3.12.

| Claim | Evidence | Re-run |
|---|---|---|
| The replacement equals the mathematical definition | `host/native/parity/spec_test.cpp` prints 360 cases (n = 1 … 100 knots, uneven spacing, every knot, mid-points, random points, far outside both ends); `spec_check.py` recomputes them with a dense `numpy.linalg.solve`: 20,840 values, worst error 1.6e-5 of the tolerance (1e-9). **No GPL code is involved.** A negative control (one value changed by 1e-6) is rejected. | part of `host/native/build.ps1`, or compile `spec_test.cpp` with `/I host/native/patched` and run `spec_check.py cases.txt` |
| It agrees with `tk::spline` where worldline uses it | `host/native/parity/main.cpp` runs worldline's `GetTensionCoefficients` for 864 combinations (4 widths, 3 sample rates, 8 tension values, 9 pitches) with the original and the replacement: 830,304 values, 795,572 bit-identical, max |diff| 1.6e-14, tension 0 exactly 1.0. Harness compiled only in a scratch folder. | `host/native/build.ps1 -OpenUtauSrc <checkout> -Out <dir>` |
| Rendered audio is unchanged | `tests/golden/selftest_audio.json`: SHA-256 of all 13 WAVs of the self-test, produced with the stock DLL; the BLT DLL reproduces them byte for byte (`tests/integration/test_selftest_e2e.py`). Honest caveat: with tension 0 the spline output is all zeros, so this test shows the integration, not the spline's interpolation. | `pytest tests/integration/test_selftest_e2e.py` with `BLT_HOST_DIR` set |
| No `tk::spline` in the shipped DLL | `host/native/verify_dll.py` fails on any `@spline@tk@` symbol in the link map or the DLL, checks the 17 exports against what `OpenUtau.Core` calls and the imports (kernel32, msvcp140, vcruntime140, UCRT). The product build does not even have the GPL header on its include path (`CMakeLists.txt`, `PATCH_SPLINE=ON`). | `host/native/build.ps1` |
| The package contains BLT's DLL, not the stock one | `host/verify-host.ps1`: SHA-256 of `worldline.dll` equals `blt-host-build.json`. | `host/verify-host.ps1` |

Known limits of the evidence: extrapolation behaviour is verified against the mathematics only (worldline never reaches it);
numerical equality with `tk::spline` was tested only on worldline's own input shapes.

## 7. Build procedure (reproducible)

`host/native/build.ps1` → `prepare.py`: downloads the pinned archives (World `f8dd5fb2…`, libgvps `2f1b4106…`, libpyin `b3813539…`,
libnpy 1.0.1, miniaudio 0.11.21, xxHash 0.8.2, Abseil 20240116.1, `tk::spline` only for the parity harness) and **checks every
SHA-256**; takes OpenUtau's `cpp/` at commit `6958d68b648bdd734d1eafa9e49b02657ca9d18e`; applies OpenUtau's own small patches and BLT's
`effects-natural-spline.patch` (two lines: the include and the one use); builds with MSVC + CMake + Ninja, Release, `/Brepro`.
The same sources give the same bytes. Third-party notices for what is statically linked (World, libgvps, libpyin, libnpy, miniaudio,
xxHash, Abseil) ship in `NOTICES.txt` / `licenses/`. Residual: World's PLATINUM files carry only
"Copyright 2012-2015 Masanori Morise. All Rights Reserved." inside World's BSD-3-Clause archive.

## 8. Options if the risk is unacceptable (not implemented; the owner decides)

* **A. Independent clean-room rewrite.** A person who has not seen `tk::spline` implements section 2 from this specification only; the
  spec test and golden tests above decide acceptance. Slowest, strongest evidence.
* **B. Remove the interpolation from worldline.** Since BLT never sets tension, patch `GetTensionCoefficients` to return the flat
  envelope 1.0 (exactly what the spline yields for tension 0). No spline code remains, nothing to derive. Loss: a non-zero tension
  curve would be ignored; BLT cannot produce one. A change to OpenUtau's behaviour that the owner has not yet approved.
* **C. Ask the author of `tk::spline`** for permission or a different licence for the replacement's purpose.
* **D. Keep the current file** with your written opinion attached to the release gate.

## 9. What BLT needs back

A signed statement with: reviewer name and qualification, date, the files and hashes reviewed (from `MANIFEST.json`), the conclusion
(acceptable / acceptable with conditions / not acceptable), and the option chosen. The owner records it in
`compliance/release-gate.json` (`docs/release-gate.md`); the gate ties it to those hashes, so changing the files invalidates it.
