# Upstream inquiry about OpenUtau's English g2p data

**Status: see "Submission record" at the end.** The owner approved submitting this inquiry on 2026-10-13 (M16 decision 1), with added
questions about the plain English pack's `g2p.onnx`. Details checked on 2026-10-13 with the public GitHub API.

## Where, who, what

| | |
|---|---|
| Repository | **openutau/OpenUtau** (https://github.com/openutau/OpenUtau; `stakira/OpenUtau` redirects to it). MIT licence. Default branch `master`. |
| Contributor of the "plus" pack | **@Cadlaxa**, author of pull request **openutau/OpenUtau#1038** "Add ARPAsing Plus Phonemizer" (merged by **@stakira** on 2024-03-28) and of all six commits that touch `g2p-arpabet-plus.zip`: `ba93f8b3` (2024-02-16), `97365778`, `3f4bfeaf`, `ddeffd5b`, `5ed2dff3`, `8b8104ae` (2024-06-21, "Update ARPA+ G2p Dictionary (preparing for model retrain)") |
| Author of the plain pack | **@stakira**: commit `eebdf6cd` "add g2p packs" (2022-02-24) added `g2p-arpabet.zip` (then under `OpenUtau.Plugin.Builtin/Data`); moved to `OpenUtau.Core/G2p/Data` by `22e0c887` (2022-09-11) |
| The files | `OpenUtau.Core/G2p/Data/g2p-arpabet-plus.zip` (4,327,034 bytes, SHA-256 `9fc73c72a112084820cccbe1ddecdd36b8c20a757428c16f0a8bacf758f88733`: `dict.txt`, `g2p.onnx` 1,779,659 bytes, `phones.txt`) and `OpenUtau.Core/G2p/Data/g2p-arpabet.zip` (2,459,789 bytes, SHA-256 `23312a3ec764bce8f3e6411db4e26a240f218a0c1c8ec4dbf95726634ed34575`: `dict.txt`, `g2p.onnx` 1,769,706 bytes, `phones.txt`) |
| Contributor's own repository | https://github.com/Cadlaxa/Syllable-Based-ARPAsing-Phonemizer: issues enabled, **no licence file** (`license: null`), README silent about the dictionary |
| Existing discussion | none: no issue or PR comment names a source for the dictionary or the models (searched "arpabet plus" and "dictionary license") |
| How to post | blank issues are disabled; the forms are "Bug report" and "Feature Request / Idea". The text below fits the Feature Request form (acknowledgement box, description, proposed change) |

## Evidence the inquiry rests on (reproducible)

`python scripts/analyze_g2p_plus.py <OpenUtau 0.1.565 checkout> --cmudict cmudict-0.7b` (read-only; CMU's original file, SHA-256 `209a8b4c…29e4`):

* the plain pack's dictionary has exactly the 133,852 entries of CMUdict 0.7b (header: "CMUdict -- Major Version: 0.07");
* the plus pack has 420,420 dictionary lines (258,522 distinct after lower-casing): 74,227 identical to CMUdict entries, 138,476 other forms of
  CMUdict words, and **45,819 entries for 37,558 words that are not in CMUdict at all** (for example `kiva`, `negentropy`, `shigella`);
* nothing in the repository, the pull request or the contributor's repository says where those entries, or either `g2p.onnx`, come from.

## The text to post

The exact title and body are kept in two files so that what is approved is what is posted:

* `docs/upstream/g2p-inquiry-title.txt`
* `docs/upstream/g2p-inquiry-body.md` (five questions: provenance, training data, licence, redistribution rights, reproducibility; for the plus pack by @Cadlaxa and for the plain pack's
  `g2p.onnx` by @stakira)

To submit (as the owner, from a shell where `gh` is logged in as the owner's account):

```
gh issue create --repo openutau/OpenUtau --title "$(cat docs/upstream/g2p-inquiry-title.txt)" --body-file docs/upstream/g2p-inquiry-body.md
```

(or paste the two files into the "Feature Request / Idea" form at https://github.com/openutau/OpenUtau/issues/new/choose).

## What BLT does with each answer

| Answer | BLT's action |
|---|---|
| Sources and licences of A documented, redistribution allowed | `docs/g2p-plus-provenance.md` updated with the evidence; the owner may then decide to re-include A and the Arpasing+ and English C+V phonemizers (a small change to the patch), with the notices the licences need; a new review item in the release gate |
| A restricted, or no answer | A stays excluded (it already is; nothing else depends on it) |
| B: training data and licence documented and permissive | recorded in `docs/g2p-plus-provenance.md` and in `packaging/components.json` (component `onnxruntime-native` is unrelated; the model belongs to `openutau-core`); a licence note is added to the shipped notices |
| B: no answer or restrictive | the owner decides: keep shipping B as an upstream-MIT file with the residual risk recorded, or regenerate the model from CMUdict |

## Submission record

**NOT SUBMITTED.** On 2026-10-13 the owner approved submitting this inquiry (M16 decision 1). The attempt to post it with `gh issue create` was **denied by the
permission system of the coding session** (it blocks writes to external systems), so no issue exists and nothing was sent. The owner must submit it (command above) or
allow the tool to do it; the issue URL and the time are then to be recorded here.
