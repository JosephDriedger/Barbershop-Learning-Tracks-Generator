# Closing record: the replacement spline in worldline.dll (review item retired in M16)

In M15 this page was a review packet asking a qualified person to judge whether BLT's replacement for the GPL-licensed `tk::spline` was a derivative of it.
**In M16 the question was removed instead of answered**: the spline code is gone from BLT's build, the build proves it, and the release gate no longer asks for this review
(`worldline-spline-review`, `required: false`, with the reason written in `compliance/release-gate.json`). This page keeps the record straight and says what is left.

## What happened (kept for the record)

* OpenUtau's prebuilt `worldline.dll` contains `tk::spline` (Tino Kluge, GPL-2.0-or-later), used only by the "tension" voice effect.
* M13-M15: BLT built the DLL itself with `host/native/patched/natural_spline.h` (92 lines, "Copyright 2026 Joseph Driedger, Apache-2.0") in its place.
  It was **written by an AI coding assistant (Claude Code) in a session directed by the owner; the owner's own review of that file is not recorded**.
  It was **not clean-room**: the session log shows that at 22:44:29 and 22:44:37 UTC on 2026-10-12 the assistant printed to its terminal parts of `tk::spline`'s `spline.h`
  (lines 215-262, the boundary-condition and equation-system set-up around lines 276-360, and `spline::operator()` with its extrapolation formulas), and created the replacement
  file at 22:45:01. The structure differs (second derivatives and Thomas elimination, instead of coefficients and a band-matrix solver), but nobody independent ever compared them.
* M16 (owner decision 2): remove the unused spline functionality rather than keep a possibly derivative replacement.

## What is true now

| | |
|---|---|
| The binary | `worldline.dll` has no spline: neither the link map nor the DLL's bytes mention "spline", "tk::" or "NaturalCubic" (`host/native/verify_dll.py`, run by every build; recorded in `blt-host-build.json` and `release-info.json` as `worldline_spline_free`, which `release_gate.py check --release` requires) |
| The source tree | the file `natural_spline.h`, its patch, its parity and specification tests, and the spline library's download and include path are gone; `effects-no-tension-spline.patch` makes `GetTensionCoefficients` return the neutral envelope |
| Behaviour | BLT only ever asks for tension 0 (45,624 of 45,624 native calls over the whole integration suite), and for 0 the original returns exactly 1.0; the host refuses projects with a tension curve. Full evidence, and what the byte-identical audio test does and does not prove: [../worldline-provenance.md](../worldline-provenance.md) |

## What is NOT resolved

1. **The earlier file is in the git history of the public repository** (commits of M13-M15, pushed). If it is a derivative of `tk::spline`, its presence there is a distribution of
   GPL-derived text under Apache-2.0, independent of what any binary contains. BLT has not rewritten history (destructive; not approved). It is an item for the owner and counsel:
   leave it and document it, or remove the file from all commits and force-push (which also invalidates anyone's clones and the commit ids this project's documents quote).
2. The removal itself needs no review: it deletes code and adds no new algorithm. A reviewer who wants to look at it can read one short patch (`host/native/effects-no-tension-spline.patch`).
3. If a tension effect is ever wanted, it must be re-introduced as a new, separately reviewed item (clean-room, from the specification only, by someone who has not seen `tk::spline`), and this gate item must be re-opened.

## If you are a reviewer

You do not need to decide anything about the spline. If counsel is asked about item 1, the facts above are the complete provenance of the file that was in the history; the
`tk::spline` source was never part of this repository (it was downloaded only by the old parity test, never committed). Nothing was signed or certified.
