# M17: remaining dependency provenance and final release-risk reduction

Status: **done and verified; every artifact is still NOT FOR RELEASE.** Nothing was published, signed or uploaded, no commit was deleted, history was not rewritten, and nothing was posted to an external service
(the upstream inquiry is still drafted and **not sent**). The release gate is **closed: 12 items open**, four of them new. What is settled by evidence, what is still uncertain and what needs a person is listed at the end.

## The nine instructions

| # | Instruction | Result |
|---|---|---|
| 1 | Investigate the plain English pack's `g2p.onnx`: origin, licence, architecture, attribution, training data, whether the supported phonemizers need it | [g2p-model-provenance.md](g2p-model-provenance.md). **Origin and use established; training data and licence statement not.** The file is the OpenUtau author's own (commit `eebdf6cd`, 2022-02-24, never changed), exported with PyTorch 1.10; a 440,715-weight model: 2-layer bidirectional LSTM encoder, 2-layer LSTM decoder, joint network (the "modified RNN-T" of OpenUtau's g2p trainer). Its weights have exactly the dimensions of `py/g2p/en_us/cfg.yaml` in the pinned tree, whose recipe trains from `cmudict-0.7b`; it reproduces CMUdict at PER 8.2 % / WER 32 %, the trainer's validation range. **No document says what this binary was trained on or under which licence.** It is used only for words outside CMUdict; the dictionary is consulted first, so every CMUdict word and the default phonemizer never touch it |
| 2 | If rights cannot be established, investigate excluding it; keep CMUdict phonemization; do not substitute a model | **Built and tested as an option, not made the default**: `host/build.ps1 -ExcludeG2pModel`, `packaging/build.ps1 -ExcludeG2pModel`. The pack keeps `dict.txt` and `phones.txt` byte for byte, loses `g2p.onnx`, and the build drops the native `onnxruntime.dll` that exists only to run it (installer 54.1 MB instead of 58.4 MB). All host integration tests pass on both variants. **No other model was substituted.** The cost is real and measured: of 33 words typical of old songs, 9 are not in CMUdict (`ev'ry`, `heav'n`, `o'er`, `'neath`, `e'en`, `lov'd`, `mammy`, `alabamy`, `mmm`); without the model such a word has no pronunciation and generation stops. Choosing between the variants is the owner's decision (below) |
| 3 | Packaged-artifact checks so that excluded resources and unsupported phonemizers cannot return | `blt-render-host --inventory` + the reviewed allow-list `compliance/host-inventory.json` + `packaging/verify_host_inventory.py`: every phonemizer, every embedded resource with SHA-256 (and archive members), the whole set of 1,317 types (hash), the one model that may be present, the model/`onnxruntime.dll` pairing, and the bytes of the assemblies for removed class names. Runs on the **packaged** host in the package build, in the package smoke test (installed copy) and in CI for both variants. `packaging/verify_absent_data.py` gained `--without-g2p-model`; `verify-host.ps1` and the package audit know the variant. **`host/negative-control.ps1` proves the checks can fail**: it builds the host from the *unpatched* OpenUtau and requires all three checks to refuse it (CI runs it). It found a real defect: `verify-host.ps1`'s Voicevox/plus type check was **blind** under Windows PowerShell 5.1 (it cannot load .NET 8 assemblies); fixed with a byte scan and the type list |
| 4 | Document the historical spline source issue separately from the binary; evidence and options for a qualified reviewer; no history rewrite | [review/source-history-review-packet.md](review/source-history-review-packet.md): two questions kept apart (binary: settled; history: open), the facts (the file, 8 commits, 5.5 hours at the public tip, 0 forks/stars/releases, no GPL text ever committed), how the file came to be written, a measured text comparison with a size-matched control ([evidence](review/evidence/spline-text-comparison.txt): no substantive shared line; elevated n-gram overlap relative to the control, as expected for the same equation system; **a measurement, not a verdict**), what cannot be established, options A-F with consequences, questions for the reviewer. **Nothing was deleted or rewritten**; the packet warns against rewriting before an opinion exists |
| 5 | Keep the GC workaround; opt-in stress configuration without it; capture crashes and artifacts; do not claim a fix | `tests/gui_diagnostics.py` (a pytest plugin: `--gui-gc-stress`, `--gui-gc-threshold`, `--gui-gc-trace`, `--gui-crash-log`, with environment variables), `.github/workflows/gui-stress.yml` (manual only; tests the current or **any older commit**; uploads traces, crash logs, dumps), [gui-gc-diagnostics.md](gui-gc-diagnostics.md). **The workaround stays; the problem is not fixed.** What the diagnostics added: on `99d1648` 2 of 10 runs aborted at the identical place, and in both the last trace line before the abort is a 3,832-object garbage collection that ran **on a Qt pool worker thread** (`Dummy-384`). On the current tree, without the workaround, 0 of 16 runs aborted (the fault depends on allocation history). This supports a hypothesis (a collection triggered on a worker thread finalises GUI-thread PySide objects) and names no object. See the document for what is and is not shown |
| 6 | Final release-review checklist for an independent reviewer | [review/INDEPENDENT-REVIEWER-CHECKLIST.md](review/INDEPENDENT-REVIEWER-CHECKLIST.md) (one page, five areas, result block) with a packet each: Qt/PySide6 LGPL (existing), [source-history](review/source-history-review-packet.md), [g2p model](g2p-model-provenance.md), [AI-assisted authorship](review/ai-authorship-review-packet.md), [native dependencies](review/native-dependencies-review-packet.md). `packaging/review_packets.py` assembles all of them with hashes and evidence into `research-output/release/review/` (one folder and one zip each) |
| 7 | Preserve the release gate and acceptance requirements | Nothing was loosened. Four required items were **added** (`source-history-licensing`, `g2p-model-provenance`, `ai-code-authorship`, `native-dependencies-review`); `g2p-model-provenance` records which variant the reviewer approved (`--decision included|excluded`) and `check --release` refuses a build of the other one. The English acceptance test gained step 10b (sing words outside CMUdict; what must happen with and without the model) |
| 8 | Run everything | below |
| 9 | Report | this page |

## Program fixes made on the way

1. A host that finds notes with no sound now **says which**: `unsung_phonemes` in the host result, and a silent-stem failure names the word ("the singing voice has no sound for the word(s) 'ev'ry' (a word that is missing from the pronunciation dictionary, or a lyric this voice cannot sing)") with a hint in the GUI explanation (respell with ordinary words). Before, the message was only "the voicebank cannot sing those lyrics". Proven end to end with the real host on both variants.
2. `verify-host.ps1`'s blind type check (above).
3. CI: the FFmpeg install from Chocolatey's feed answered 504 on three runs in a row; it now retries (the failures were not in BLT).
4. An over-broad pattern in the new smoke check (it matched `ChineseCVVPlusPhonemizer`) was found by the first CI run and fixed.

## Verification

| Check | Result |
|---|---|
| `ruff check`, `ruff format --check`, `mypy` (strict, 293 files), licence audit tables | clean |
| Unit tests | 2,659 passed |
| Whole suite (`pytest tests`) against the **shipped** pruned self-contained host: unit, real-host synthesis, full pipeline, golden audio, the new host/inventory/variant tests | **2,721 passed, 5 skipped** (no English voicebank configured; no FFmpeg on this PC) |
| Host integration tests, both variants (with and without the model), development and published hosts | passed (CI builds and runs both) |
| Host inventory against the allow-list, both variants; `verify-host.ps1`; `verify_absent_data.py` (with and without `--without-g2p-model`) | ok |
| Negative control (unpatched host refused by all three checks) | passed (local and CI) |
| Package build, default variant (commit `9d42896`): inventory audit (456 files, 1 blocker: pyside6), package smoke test (plain and non-ASCII paths, the installed host's g2p state and its own inventory), replaceability test (12 of 12 Qt files identical to their wheels) | passed |
| Package build, variant without the model (commit `366b6ed`): same checks; `onnxruntime-native` absent as the audit now requires | passed |
| Installer test (silent install, missing-runtime refusal, install + smoke, upgrade, uninstall, user data kept) | passed |
| Installer GUI test (the real Setup window with the runtime reported missing; signature checks) | passed |
| CI on `9d42896` | all three jobs green |
| Release gate `check --release` | exit 1, **12 open** (as intended) |

## Which concerns are resolved, uncertain, or need a person

**Resolved by technical evidence**
* What `g2p.onnx` is, where it came from, that it is needed only for words outside CMUdict, and that the supported English phonemizers work without it (tested end to end).
* That the removed engines and data cannot come back unnoticed (three independent checks, shown able to fail), and that the previous Voicevox/plus type check was blind and is now backed by a working one.
* That the binary has no spline (unchanged: `worldline_spline_free`).
* That a word the voice cannot sing is now named instead of silently dropped.

**Still uncertain** (evidence is circumstantial or the question is legal)
* The g2p model's **training data and licence**: probably CMUdict 0.7b only, under a permissive licence, in an MIT repository by its author; unconfirmed by anyone. The inquiry is unsent.
* Whether the **historical replacement spline** is a derivative of `tk::spline`: the text comparison does not say it is not.
* The **GC problem**: a hypothesis with a strong clue (a collection on a worker thread), no named object, no fix; on the current tree no run reproduces it.
* **Qt/PySide6 LGPL arrangement** (including the four frozen PySide6 modules and the "already present" reading of 4(d)(1)); **AI-assisted authorship** of the code; the licence conclusions for the **native dependencies** (PLATINUM's missing licence text, the GCC runtime exception in OpenBLAS, onnxruntime's third-party list). All three are now packets for a reviewer.

**Needs a human decision**
1. **The g2p model**: keep it (A), ship without it (B, ready and tested), or have BLT train its own from CMUdict with the upstream recipe (C, needs your approval). Also whether to post the upstream inquiry (the session's permission system blocked it in M16; the command is in `docs/upstream-g2p-plus-issue.md`).
2. **The history**: options A-F of the source-history packet; whether to keep a private copy of the AI session log as evidence; whether to make the repository private meanwhile; whether to contact the `tk::spline` author. **Do not rewrite history before counsel has opinion** (the rewrite destroys the evidence).
3. **The GC problem in the product**: whether to try the candidate mitigation (automatic collection off in the app, collected from a GUI-thread timer) now or wait for a named object.
4. Find the reviewers and the testers.

**External sign-offs still required** (the gate): `qt-lgpl-review`, `qt-source-published`, `source-history-licensing`, `g2p-model-provenance`, `ai-code-authorship`, `native-dependencies-review`, `english-voicebank-acceptance` (a real voicebank and a listener), `clean-machine-verification` (including a PC without the Visual C++ runtime and the administrator prompt), `code-signing-decision`, `owner-release-approval`.

## Not done, on purpose

No model was substituted or trained; no history was rewritten; the upstream inquiry was not posted; nothing was signed, published or uploaded; no GUI feature was added (the only GUI change is one extra step in an existing explanation).
