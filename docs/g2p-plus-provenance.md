# The English "ARPAbet plus" dictionary: provenance and dependency

Status: **explicit blocker, redistribution not approved** (owner decision, M14). It is still inside the host build because
removing it was not approved either ("do not remove blindly"). Nothing here resolves it.

## What it is

`OpenUtau.Core/G2p/Data/g2p-arpabet-plus.zip` (embedded in `OpenUtau.Core.dll`): a dictionary and a neural g2p model for English.

* 420,422 entries. 299,535 of them are CMUdict 0.07 words (Carnegie Mellon University, BSD-style licence, shipped and credited).
* 120,887 entries are **additions** (for example `'sblood`, `'tisn't`) whose source is not stated anywhere in OpenUtau's repository.
* Added to OpenUtau by the contributor *cadlaxa* in February 2024 (commit `ba93f8b3`), updated until June 2024; the commit/PR
  text names no source and no licence. The file's later history in the pinned tree is only a revert-merge (`a60ca58`).

## What depends on it (traced in the pinned source, commit `a60ca58`)

| Consumer | Uses plus? | In BLT? |
|---|---|---|
| `DefaultPhonemizer` (BLT's default) | no: voicebank's own dictionary | yes, default |
| `ArpasingPhonemizer`, `EnglishVCCV`, `EnXSampa`, `ENtoJA`, Enunu English, DiffSinger English | no: they use the plain `g2p-arpabet` (CMUdict + a neural fallback for unknown words) | selectable by name |
| `ArpasingPlusPhonemizer` | **yes** | selectable by name |
| `EnglishCpVPhonemizer` | **yes** | selectable by name |
| DiffSinger ARPA+ English, Phonetic Assistant, lyrics helper | yes | not offered or tested by BLT (DiffSinger is not a supported BLT renderer) |

So English singing does **not** depend on the plus dictionary unless the user explicitly picks "Arpasing+" or "English CpV".
Everything BLT tests (default phonemizer, Arpasing, the self-test, the English acceptance plan) works from CMUdict.
The plain dictionary's neural fallback needs the shipped `onnxruntime.dll`; that is checked by `blt-render-host --g2p-check`.

## Options (nothing is done yet)

1. **Keep as is**: not acceptable until provenance is known (the blocker).
2. **Replace the plus pack with an empty one** in `host/patch_openutau.py` (as for the other languages) and mark
   Arpasing+/English CpV unavailable. Cheapest, loses those two phonemizers. `host/verify-host.ps1` would then expect an empty pack.
3. **Replace it with a pack made only from CMUdict** (299,535 entries) so the two phonemizers keep working with the
   known-licence part. Needs a build step that regenerates the zip from `cmudict-0.7b` and the neural fallback model of the
   plain pack; the model's licence must be known as well (the plain pack's model is the same trained weights family but that is
   *not verified*).
4. **Get the answer from upstream**: ask the contributor which sources the 120,887 additions come from and under which licence.

## Upstream contact

A draft issue for OpenUtau is in `docs/upstream-g2p-plus-issue.md`. **It has not been sent**: it is a public post under the
owner's account, so the owner sends it (or asks BLT to). Until a reply documents the sources and licences, the blocker stays.

## Recommendation

Do option 4 in parallel with option 2 as the default for any release candidate: ship the build with the plus pack emptied
unless the upstream answer is positive and documented. That keeps all BLT-supported English functionality, because the
supported English phonemizers do not use it.
