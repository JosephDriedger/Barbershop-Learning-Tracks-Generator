# Independent review checklist (one page for the reviewer)

For the person asked to judge the licensing and provenance of BLT Music Generator before any release. **Every installer BLT builds is marked NOT FOR RELEASE; nothing has been published, signed or uploaded.**
BLT's own tests prove that the program builds and works; they cannot say that its legal position is sound. That is your part, and the release gate ([../release-gate.md](../release-gate.md)) will not open until a person has recorded it.

## How to use this

1. Start from the **review kit** that `packaging/build.ps1` writes to `research-output/release/review/` (one folder and one zip per packet, each with a `MANIFEST.json` of SHA-256 hashes). The owner sends you the SHA-256 of the kit by a separate route; compare it.
2. Work through the five areas below. Each has a packet that gives the facts, the evidence and the questions. **A packet is the project's account, not a conclusion; check what you can, and say what you could not check.**
3. "I cannot conclude without more material" is a valid and useful answer: say what material. It keeps the item open, as it should.
4. Write your conclusion as a short signed letter (PDF or text). The owner files it under `compliance/evidence/` and runs the `sign` command in the last section naming **you** as the person who judged. The sign-off is bound to the exact text of the packet you read; if the packet changes afterwards, the item re-opens.

## The five areas

| # | Area | Gate item(s) | Packet | What you decide |
|---|---|---|---|---|
| 1 | Qt / PySide6 under the LGPL-3.0 | `qt-lgpl-review`, then `qt-source-published` | [qt-pyside6-review-packet.md](qt-pyside6-review-packet.md) | whether the arrangement satisfies the LGPL, and whether the source bundle's publication does |
| 2 | Source-history licensing | `source-history-licensing` | [source-history-review-packet.md](source-history-review-packet.md) | whether the replacement spline in the git history is a problem, and which remediation (if any) |
| 3 | The g2p model's provenance | `g2p-model-provenance` | [../g2p-model-provenance.md](../g2p-model-provenance.md) | confirm shipping without it (`excluded`); a build with the model is refused by the gate |
| 4 | AI-assisted authorship | `ai-code-authorship` | [ai-authorship-review-packet.md](ai-authorship-review-packet.md) | whether the copyright notice, the licence and the diligence are adequate |
| 5 | Remaining native dependencies | `native-dependencies-review` | [native-dependencies-review-packet.md](native-dependencies-review-packet.md) | whether the licence conclusions for every compiled component stand |

You may be asked for only some of these; each item is independent.

### 1. Qt / PySide6 (LGPL-3.0)

- [ ] Versions and licence identifiers are right (Qt 6.11.2, PySide6/shiboken6 6.11.2; LGPL-3.0-only elected), and every Qt/PySide6 file in the package is unmodified (the packet shows 12 of 12 identical to the wheel RECORD hashes).
- [ ] The notices in `NOTICES.txt` and `licenses\` meet LGPL-3.0 §4(a)-(b) (statement of use, licence texts).
- [ ] **§4(d)(1)**: does an application that carries its *own copy* of the Qt DLLs, next to the program and replaceable, use "a suitable shared library mechanism" that "operates properly with a modified version"? (The replaceability test replaces a DLL and the program runs; its log is in the packet.)
- [ ] Four small PySide6/shiboken6 **Python modules are frozen into the executables** (not separate files). Is that acceptable, given the relinking instructions (`RELINKING.md`) explain the rebuild route?
- [ ] The written offer and the corresponding-source bundle (prepared, **not published**): are they sufficient, and is hosting the bundle on the same release page enough for the required period?
- [ ] Anything you would want changed before publication.

### 2. Source-history licensing

- [ ] Read §2 and §3 of the packet and `evidence/spline-text-comparison.txt`; fetch the upstream file (URL in the packet) if you want to compare yourself.
- [ ] Is the file a derivative work of `tk::spline`? If you cannot tell, what would you need?
- [ ] Which remediation, if any (options A-F), and in which order. **Note the warning against rewriting history before an opinion exists: a rewrite destroys the evidence.**

### 3. The g2p model

- [ ] Read the evidence (§2) and what is *not* established (§3) of [../g2p-model-provenance.md](../g2p-model-provenance.md). You can reproduce the technical claims: `python scripts/research/inspect_onnx.py` and `eval_g2p_model.py`.
- [ ] Is the provenance enough to redistribute the model under MIT with the CMUdict notice? If not, the proposed release is the variant built **without** it (the default build; the model only in the research build `-IncludeG2pModel`); do you confirm that choice (what it costs is in §4-5)?
- [ ] State **`included` or `excluded`** in your letter. The gate then accepts only a build of that variant.

### 4. AI-assisted authorship

- [ ] Read §1 (facts) and §3 (what cannot be measured). Is "Copyright 2026 Joseph Driedger" under Apache-2.0 a fair statement for this code?
- [ ] What diligence about reproduced third-party text is reasonable before release (§4.3), and should the notices say that an AI assistant helped write the code?

### 5. Native dependencies

- [ ] Go through the table in the packet row by row; the file-level mapping is the kit's `inventory.json`. In particular: PLATINUM's missing licence text, the GCC Runtime Library Exception for the statically linked libgfortran, onnxruntime's third-party notices.
- [ ] Is relying on the vendor's published notices (NumPy, onnxruntime, .NET) enough, and is requiring the user's own Visual C++ runtime (not shipping it) in order?

## What is not yours to decide (so you know it is being handled)

English-voicebank listening test, clean-machine test (including a PC without the Visual C++ runtime), the code-signing decision and the owner's release approval are separate gate items with their own checklists in [../acceptance/](../acceptance/README.md).
The upstream inquiry about the g2p model is **drafted, not sent** ([../upstream-g2p-plus-issue.md](../upstream-g2p-plus-issue.md)); an answer from the OpenUtau maintainers would help item 3 and is not required.

## Recording the result (the owner runs this, naming you)

```
python packaging/release_gate.py sign <item> --by "<your name>" --role "<your qualification>" \
    --conclusion approved|approved-with-conditions [--conditions "..."] \
    --evidence compliance/evidence/<your-letter> [--decision included|excluded   # item 3 only]
python packaging/release_gate.py status        # what is still open
```

## Result block (copy into your letter)

```
Reviewer: ______________________   Qualification: ______________________   Date: __________
Kit SHA-256 checked: yes / no      Commit reviewed: ____________________
Item: ____________________   Conclusion: approved / approved with conditions / cannot conclude
Conditions or missing material: ________________________________________________________
For g2p-model-provenance only: build to be released contains the model: excluded (the only value the gate accepts)
What I verified myself, and what I relied on BLT's account for: ____________________________
```
