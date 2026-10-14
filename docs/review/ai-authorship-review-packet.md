# AI-assisted authorship of BLT's own code

Packet for a qualified, independent reviewer (gate item `ai-code-authorship`). Written in M17. **BLT does not claim this question is resolved.** It states the facts as the project's AI assistant knows them, what could be measured,
and what cannot be measured by anyone inside the project.

## 1. The facts

* **Who wrote the code.** Essentially all of BLT's own code, tests, build scripts and documents (about 88,000 lines in 946 tracked files: `tests` 44 k, `src` 20.5 k, `packaging` 11.6 k, `docs` 6.8 k, `scripts` 2.3 k,
  `host` 1.5 k lines, ...) was written by an AI coding assistant (Anthropic's Claude Code, several model versions over the project's life) in sessions directed by the owner, Joseph Driedger. The owner decided what to build,
  wrote the requirements, read the reports, approved or rejected each milestone and made every licensing decision; the assistant wrote and ran the code. The owner's line-by-line review of the code is not recorded.
* **What the repository says about it.** Every commit is authored as "Joseph Driedger" (no other author). There are **no AI co-author trailers or attribution lines**: that is the owner's standing instruction. So the git history is silent about the assistant's role; this is stated in the milestone reports (`docs/m15-report.md`, `docs/m16-report.md`, `docs/g2p-model-provenance.md`) and here, and the
  owner's declaration of ownership is recorded in `packaging/components.json` (component `blt`).
* **What the licence notices say.** `LICENSE` (Apache-2.0) and `NOTICE`: "Copyright 2026 Joseph Driedger". Source files that carry a header say the same (for example the former `natural_spline.h`).
* **Third-party code BLT copies or adapts.** None is copied verbatim into BLT's own files except: the pinned OpenUtau source is *patched* at build time (`host/patch_openutau.py` changes a copy; the patches are BLT's text),
  and `host/BltRenderHost/*.cs` is new code written against OpenUtau's public API in the order OpenUtau's own GUI initialises things (MIT, attribution in `NOTICES.txt`). Qt, PySide6, NumPy and the others are used as libraries.
* **The one case where the assistant demonstrably saw third-party code before writing**: the replacement spline of M13-M15, written after printing parts of the GPL `tk::spline` to its terminal. Handled in
  [source-history-review-packet.md](source-history-review-packet.md); it is a known instance, not a proof that it is the only one.

## 2. What could be measured (and was)

| Check | Result |
|---|---|
| Distinctive identifiers of the one GPL source known to have been seen (`band_matrix`, `make_monotonic`, `cspline_hermite`) anywhere in the history | none (`git log --all -S...`) |
| Text comparison of the former replacement spline with that source | no substantive shared line; elevated shared token n-grams relative to a control ([evidence/spline-text-comparison.txt](evidence/spline-text-comparison.txt)) |
| Licence scan of the package against the declared components | every file of the package maps to an inventoried component; `packaging/inventory.py` fails the build otherwise |
| Tool for any further pair of files | `python scripts/research/compare_source_text.py A B` (token n-gram overlap, with a size-matched control as in the evidence file) |

## 3. What cannot be measured from inside the project

1. **Whether any other BLT file reproduces third-party text** that a language model memorised from its training data. There is no list of what the model saw and no tool that can prove the absence of such text. Searching a few
   likely sources (done for OpenUtau and `tk::spline`) is evidence about those sources only.
2. **Whether the owner holds copyright in AI-generated code** and to what extent, which depends on the jurisdiction, on how much human creative control there was (the owner's direction, selection and review are real but modest
   in line-level terms), and on the terms of the assistant's provider. This affects whether "Copyright 2026 Joseph Driedger" and the Apache-2.0 grant mean what they say.
3. **Whether the provider's terms** restrict the use or licensing of output in a way that matters for a redistributed application. BLT has not examined them.
4. **What a downstream user may rely on**: the Apache-2.0 patent grant and warranty disclaimer are given by a licensor whose authorship is partly machine-generated.

## 4. Questions for the reviewer

1. Is the copyright notice accurate as written? Should the notice, `NOTICE` or `README` describe AI assistance, and how?
2. Is the Apache-2.0 licence appropriate for code of this origin, or should it be accompanied by a disclaimer about authorship?
3. What diligence is reasonable for the risk in §3.1 (for example, running a code-provenance scanner over the repository; BLT has none and did not run one)? Is it required before a public release?
4. Do the provider's terms of use for the assistant need to be checked, and by whom?
5. Is the silence of the git history (no trailer) a problem, or does the documentation suffice?

## 5. What would help the reviewer (offered, not done)

* A scan of `src/`, `host/`, `packaging/` and `tests/` with a commercial or open provenance scanner; the owner would need to choose and pay for it.
* The owner's statement of what they reviewed personally.
* The assistant's session logs (local files on the owner's PC) for any file the reviewer wants traced.

## 6. Sign-off

Gate item `ai-code-authorship`; it closes only with a person's recorded conclusion bound to this page:

```
python packaging/release_gate.py sign ai-code-authorship --by "<reviewer>" --role "<qualification>" \
    --conclusion approved|approved-with-conditions [--conditions "..."] --evidence <the reviewer's letter in compliance/evidence/>
```
