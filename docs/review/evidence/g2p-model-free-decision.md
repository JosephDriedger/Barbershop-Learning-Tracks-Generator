# Record of the decision: the proposed release configuration has no English g2p model

This is the evidence behind the sign-off of the release-gate item `g2p-model-provenance` (decision value `excluded`). It records **who decided, in which words, and for which artifact**. It is a record of a decision;
it is not a legal opinion, it does not settle the model's provenance, and it is not an approval to release.

## Who decided, and how it is known

* The decision was stated in chat, in the instruction that opened milestone M19, by the person who owns this project. The words, quoted exactly:

  > "1. Confirm the model-free build as the proposed release configuration. Record the g2p decision as excluded using the existing release-gate mechanism, with the correct artifact hash and an authentic human approval record. Never invent a reviewer name or signature."

  It repeats the decision of the M18 instruction, item 1: "Select the -ExcludeG2pModel variant as the proposed release configuration. The unknown-provenance g2p.onnx must not be in the proposed release artifact."
* The person is recorded as **Joseph Driedger**, the name in the project's copyright notice ("Copyright 2026 Joseph Driedger", `LICENSE`, `NOTICE`) and the git identity under which the repository is committed. No other name was used, and none was chosen by the assistant.
* **How the record was made.** The assistant (an AI) ran `packaging/release_gate.py sign` **on that person's instruction**; the gate refuses names of automation and AI assistants, so the sign-off names the person, not the tool. This record rests on the person's statement in the
  working session, which is not independently verifiable from the repository. If a stronger record is wanted, the person can re-sign with their own command (the gate re-binds the item to the then-current files):
  `python packaging/release_gate.py sign g2p-model-provenance --by "<name>" --role "<role>" --evidence docs/review/evidence/g2p-model-free-decision.md --installer-sha256 <sha> --decision excluded`.

## What was decided

The release candidate ships **without** `g2p.onnx` (the neural fallback of OpenUtau's English pack, whose training data and licence are not documented) and without the native `onnxruntime.dll` that exists only to run it. A word the pronunciation dictionary
(CMUdict 0.7b) lacks stops generation; a person respells it or gives its pronunciation (M19). The build with the model exists only for internal research (`-IncludeG2pModel`), is named `...-RESEARCH-ONLY-Setup.exe`, and is refused by `-ForRelease` and by
`release_gate.py check --release`.

## The artifact this was checked against

| | |
|---|---|
| Installer | `BLT-Music-Generator-0.1.0-Setup.exe`, 56,810,686 bytes, unsigned |
| SHA-256 | `16acbab1f5ee188b86426d0f93e250a2e3b6a47b543ce9f4e17e0f0002973976` |
| Built from commit | `5559301ac986676394cb22371d56a8cab271c935` (no uncommitted changes) |
| `release-info.json` | `"g2p_model": "excluded"`, "proposed release configuration (model-free); not for release until the release gate is open" |
| Host inventory | `compliance/host-inventory.json` (allow-list; 1,324 types; model and `onnxruntime.dll` absent in this variant); the build's `verify_host_inventory.py --g2p-model excluded`, `verify_absent_data.py --without-g2p-model` and the smoke test's `g2p-check` passed on it |
| Tests on the shipped host | full suite 2,933 passed, 5 skipped (voicebank- and FFmpeg-dependent); installer, upgrade, uninstall and installer-GUI tests passed (see `docs/m19-report.md`) |

## What this sign-off does not cover

* The provenance of `g2p.onnx` is **not** established and the upstream inquiry is **not** sent; excluding the file is the way the proposed release avoids needing it.
* It is not a release approval. Eleven items of the release gate remain open and need other people: `qt-lgpl-review`, `qt-source-published`, `source-history-licensing`, `ai-code-authorship`, `native-dependencies-review`, `english-voicebank-acceptance`,
  `clean-machine-verification`, `code-signing-decision`, `owner-release-approval`, the `pyside6` component blocker and the package check.
* The sign-off is bound to the item's subject files (`docs/g2p-model-provenance.md`, `compliance/host-inventory.json`, `packaging/verify_host_inventory.py`, `host/patch_openutau.py`) by their hashes: changing any of them re-opens it.
