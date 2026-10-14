# Source-history licensing: the replacement spline in BLT's git history

Packet for a qualified, independent reviewer. Written in M17. **Nothing here is a conclusion that the concern is resolved.** It separates two questions that are easy to run together,
gives the evidence in full, and lists options. No commit was deleted and no history was rewritten (that needs the owner's explicit authorisation, and it destroys evidence; see option D).

## 1. Two different questions

| | The current binary | The source history of the public repository |
|---|---|---|
| Question | does `worldline.dll` contain `tk::spline` (GPL-2.0-or-later) or anything derived from it? | does an old commit contain a file that is a derivative of `tk::spline`, published under Apache-2.0? |
| Status | **settled by build-time evidence.** The spline functionality is gone from BLT's native build (M16); `host/native/verify_dll.py` fails every build whose link map or DLL bytes mention "spline", "tk::" or "NaturalCubic"; the result is recorded as `worldline_spline_free` in `blt-host-build.json` and `release-info.json`, and `release_gate.py check --release` refuses a build without it. Details: [../worldline-provenance.md](../worldline-provenance.md) | **open.** The file is in the history and the history is public. It cannot be settled by a build; it needs a legal judgement about the file and how it came to be written |
| Who can close it | a test did | a person (counsel) and the owner |

Removing the code from the tip of `main` (M16) did what it can for the binary and the working tree. It does nothing for commits that already exist.

## 2. Facts

**The file.** `host/native/patched/natural_spline.h`: a natural cubic spline class, 92 lines (3,475 bytes; SHA-256 of the last version starts `bc9ebdc7af55493c`), header "Copyright 2026 Joseph Driedger.
Licensed under the Apache License, Version 2.0", added so that BLT's own `worldline.dll` would not contain `tk::spline` (author Tino Kluge, GPL-2.0-or-later, used by OpenUtau's "tension" voice effect). With it:
`host/native/effects-natural-spline.patch` (20 lines), and parity/specification tests (`host/native/parity/`). All removed in `7d2e938`.

**Where it exists.** Added in `11939bd` (M14, committed 2026-10-13 15:26:49 UTC) and present in the eight commits `11939bd`..`b4b99bb`; removed from the tip by `7d2e938` (committed 20:18:23 UTC). GitHub's event log
shows the push that carried `11939bd` at 15:27:06 UTC and the push that carried the removal at 20:58:06 UTC the same day, so the file was at the tip of the public branch for about five and a half hours and is in the history of every commit since.
The repository is `JosephDriedger/Barbershop-Learning-Tracks-Generator`, **public** (checked 2026-10-13: visibility public, 0 forks, 0 stars, 0 watchers, 0 releases, no tags, licence Apache-2.0). Whether it was public
at the time of the first push is not recorded in anything I can read; the owner can tell from the repository's settings history.
No installer or other build containing the file was ever published or uploaded; every artifact is marked NOT FOR RELEASE.

**No GPL text was ever committed.** `tk::spline`'s `spline.h` was downloaded by the old build script at build time (pinned `5894beaf91e9adbfdbe5c6c9a1c60770e380e8e8`) and never added to the repository. A search of the whole history for identifiers that
are distinctive of its source (`band_matrix`, `make_monotonic`, `cspline_hermite`) finds nothing (`git log --all -S"band_matrix"` and the others: no commit).

**How the file was written (this is the uncomfortable part).** It was written by an AI coding assistant (Claude Code) in a session that the owner directed. The owner's own review of the file is not recorded.
It was **not clean-room**: the session log shows the assistant printing parts of `tk::spline`'s `spline.h` to its terminal (lines 215-262; the boundary-condition and equation-system set-up around lines 276-360; and `spline::operator()`
with its extrapolation formulas) at 22:44:29 and 22:44:37 UTC on 2026-10-12, and creating the replacement at 22:45:01. The earlier M13/M14 wording "written from the maths" understated that and was corrected in M15.
The session log is a file on the owner's PC (`%USERPROFILE%\.claude\projects\...\*.jsonl`), not in the repository; **the owner should keep a copy as evidence** before anything is cleaned up. A model trained on public code
may also reproduce text it has seen without being shown it; that cannot be examined from here.

**What the file implements.** The textbook natural cubic spline: second derivatives from the tridiagonal system, Thomas elimination, evaluation by the standard cubic formula, linear continuation outside the knots. It does not use
`tk::spline`'s coefficient form or its band-matrix solver; the structure differs. The mathematical specification and tests that checked it against the definition (20,840 values) and against `tk::spline`'s output on every input
worldline produces (max difference 1.6e-14) are in the history (`cef2670`, `host/native/parity/`); the old packet is [worldline-spline-review-packet.md](worldline-spline-review-packet.md).

## 3. Evidence for the reviewer

| Evidence | Where |
|---|---|
| The file and its patch, exactly as committed | `git show b4b99bb:host/native/patched/natural_spline.h`, `git show b4b99bb:host/native/effects-natural-spline.patch` |
| Every commit that touched them | `git log --all --format='%h %cI %s' -- host/native/patched/natural_spline.h host/native/effects-natural-spline.patch host/native/parity` |
| Where GPL text would be if it had been committed | `git log --all -S"band_matrix"` (and `make_monotonic`, `cspline_hermite`): empty |
| A text comparison with `tk::spline` and with unrelated C++ of the same size | [evidence/spline-text-comparison.txt](evidence/spline-text-comparison.txt) (tool: `scripts/research/compare_source_text.py`) |
| The upstream file compared (GPL; fetch it yourself, it is not in this repository) | `https://raw.githubusercontent.com/ttk592/spline/5894beaf91e9adbfdbe5c6c9a1c60770e380e8e8/src/spline.h` |
| Proof the current binary has none of it | `host/native/verify_dll.py`, `blt-host-build.json` (`worldline_spline_free`), `docs/worldline-provenance.md` |
| How the AI session came to see the upstream file | the owner's local session log (see above) |

**What the text comparison shows, and does not show.** After removing comments and whitespace, the two files share **no substantive line of code** (the seven identical lines are `#include`s, access labels and closing braces).
The longest run of identical tokens is 20: the constructor's parameter list, the obvious interface for "a curve through these points". Counting token 8-grams, 2.8 % of the replacement's also occur in the 947-line `tk::spline`
(0.4 % in an unrelated six-file control of similar size); counting 5-grams, 12.3 % (control 5.1 %); with names and numbers blanked, so that only the shape of the code counts, 26.6 % of 8-grams (control 10.0 %). So the replacement
is closer to `tk::spline` than unrelated code is, which is expected for two programs that solve the same equation system, and it contains no copied statement. **That is a measurement of text, not an answer to whether one work is derived from the other.**
Derivation is a legal and factual judgement that includes how the file came to be written (above).

## 4. What I cannot establish

* Whether the file is a derivative work of `tk::spline` in the legal sense (a lawyer's question; the copyright in a short implementation of a standard algorithm is thin, but the assistant's exposure to the source is the fact a lawyer will ask about first).
* Who owns the copyright in AI-written code and what the "Copyright 2026 Joseph Driedger" header is worth (see the AI-authorship item of the reviewer's checklist).
* Whether anyone obtained a copy of the file while it was public (0 forks and 0 stars at the last check; clone counts exist only for someone with push access, under *Insights > Traffic*, and cover just the last 14 days).
* Whether `tk::spline`'s licence notice requires anything of a repository that only *links to* the idea. It does not appear to, but I have no standing to say.

## 5. Options (decisions for the owner with counsel; none was taken)

| | Option | What it takes | Consequence / risk |
|---|---|---|---|
| A | **Leave the history, keep this record** | nothing | the file stays reachable in old commits; the residual risk is the one above |
| B | **Get counsel's written opinion first** (recommended before D) | a lawyer; this packet; the session log | an opinion to attach to the gate item; may conclude A is enough |
| C | **Ask Tino Kluge (the author of `tk::spline`)** for a statement, or a permission, about the replacement | a polite issue/e-mail from the owner showing the file and the comparison | a written answer settles the practical risk; silence changes nothing |
| D | **Remove the file from every commit and force-push** (`git filter-repo --path host/native/patched/natural_spline.h --path host/native/effects-natural-spline.patch --path host/native/parity --invert-paths`, then a forced push) | the owner's explicit authorisation; a private backup bundle **first** (the rewrite destroys the evidence); GitHub support to purge cached views of old commits | every commit id after `11939bd` changes, so the ids quoted in docs and reports (and any clone) become wrong; collaborators must re-clone; forks made in the meantime keep the old history; the gate's sign-offs hash files, not commits, so they survive |
| E | **Make the repository private** until A-D are decided | the owner | reduces further exposure; does not undo past exposure |
| F | **Never reintroduce interpolation** in the native build | nothing | keeps the binary question closed; the gate item `worldline-spline-review` stays retired. If tension is ever wanted it must be a new, separately reviewed, clean-room item |

Do **not** do D before B: a rewrite removes the very history a lawyer would want to inspect. If D is chosen, make the backup (`git bundle create ../blt-before-rewrite.bundle --all`, kept privately) before running anything.

## 6. Questions for the reviewer

1. Is `natural_spline.h` (92 lines) a derivative work of `tk::spline`, given §2 and the comparison? If you cannot say without a closer technical comparison, say what you need.
2. If it is, is the presence of the file in the history of a public repository, for the period and with the exposure in §2, something that requires remediation beyond the removal already made? Which of A-F do you advise?
3. Is the owner's statement in the file header ("Copyright 2026 Joseph Driedger; Apache-2.0") accurate, or should the history carry a correction?
4. Does anything in §2 need to be disclosed to anyone (the `tk::spline` author, OpenUtau)?

## 7. Sign-off

This item is `source-history-licensing` in [../../compliance/release-gate.json](../../compliance/release-gate.json). It closes only with a person's recorded conclusion bound to this page and the evidence file:

```
python packaging/release_gate.py sign source-history-licensing --by "<reviewer>" --role "<qualification>" \
    --conclusion approved|approved-with-conditions [--conditions "..."] --evidence <the reviewer's letter in compliance/evidence/>
```
