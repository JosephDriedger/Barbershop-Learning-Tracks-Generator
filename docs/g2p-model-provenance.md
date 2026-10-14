# The English pronunciation model (`g2p.onnx` of the plain pack): provenance, licence, and what depends on it

Written in M17. **Status: origin and use established; training data and licence statement NOT established. A person must decide** (gate item `g2p-model-provenance`,
[release-gate.md](release-gate.md)). BLT can build with the model (default) or without it (`-ExcludeG2pModel`); both are tested. Nothing was substituted: the model BLT ships is
byte-for-byte the one in the pinned OpenUtau.

## 1. What the file is

| | |
|---|---|
| Where | member `g2p.onnx` of `OpenUtau.Core/G2p/Data/g2p-arpabet.zip` in OpenUtau 0.1.565 (pinned commit `a60ca58`); the zip also holds `dict.txt` (CMUdict 0.7b, entry for entry: [g2p-plus-provenance.md](g2p-plus-provenance.md)) and `phones.txt` |
| Bytes | 1,769,706; SHA-256 `10779eca9db25cab467f2a6271519c3f0c96f562845c393043fa5fa85ae06059` (zip: 2,459,789 bytes, `23312a3e…4575`; `dict.txt` `7a1feef4…0aae`, `phones.txt` `4614adcc…c8a7`) |
| Made by | exported with **PyTorch 1.10** (`producer_name: pytorch`, ONNX IR 7, opset 11, graph `torch-jit-export`); no description, no metadata properties, no licence field. Zip member dated 2022-02-23 13:49 |
| Added to the repository | 2022-02-24 by Sugita Akira (**stakira**, the author of OpenUtau and holder of its copyright) in commit `eebdf6cd` "add g2p packs"; moved to `OpenUtau.Core` on 2022-09-11 (`22e0c887`). **These are the only two commits that ever touched the file**: it has never been replaced |
| Size and shape | 440,715 float32 weights in 35 tensors; 114 graph nodes; operators: LSTM ×4, Gather, MatMul, Tanh, Softmax, ArgMax, Slice/Concat/… (no custom operator) |
| Architecture (read from the weights) | grapheme embedding 32×64; **2-layer bidirectional LSTM encoder** (64 per direction); phoneme embedding 43×64; **2-layer LSTM decoder** (128); joint network 128→128→43 with `tanh`; greedy decoding in which the input `t` selects the encoder frame and a "blank" (`<bos>`, index 2) advances it. That is the "modified RNN-T" the OpenUtau g2p trainer describes |

Reproduce all of it from the file alone: `python scripts/research/inspect_onnx.py g2p.onnx` (a stand-alone protobuf reader; no ONNX library needed).

## 2. Where it came from: what the public record shows

1. **The recipe is in the very tree BLT pins.** `py/g2p/` (added 2023-04-27, `4dca53d7`, removed upstream on 2026-08-31 in `8c0dc400`) trains the English ARPAbet model "from `cmudict-0.7b`"
   (`train.py`: `SphinxDataset('g2p/en_us/cmudict-0.7b', …)`, README: "Place `cmudict-0.7b` file in `en_us` folder"). Its `cfg.yaml` is `d_model: 64`, `d_hidden: 128`, `num_layers: 2`, 32 graphemes and 43
   phonemes (4 specials + 39 ARPAbet). **Every dimension of the shipped model matches that configuration** (embedding 32×64 and 43×64, encoder LSTM 64 per direction × 2 layers, decoder 128 × 2 layers, joint 128→43).
2. **The successor trainer** is the repository `openutau/g2p` ("version 2", 2025-12-22, author stakira): README "Train en_us arpabet model: place the `cmudict-0.7b` file in the `data` folder", and a table of error rates for
   `cmudict-0.7b` (validation: PER 8.56 %, WER 34.92 %; with stress removed 6.76 % / 30.27 %). That repository has **no licence file**.
3. **The model behaves like a small model trained on CMUdict.** `python scripts/research/eval_g2p_model.py g2p-arpabet.zip` reproduces OpenUtau's greedy decoding with onnxruntime and, on a random sample of 5,000 of the 124,816
   usable dictionary words, gives **WER 31.9 %, PER 8.15 %** (a second sample: 33.9 % / 8.78 %), the range of the trainer's published validation figures. It matches the dictionary no better than a small model should, so it was not memorising
   a larger list that includes these words.
4. **The licence of the surroundings.** The repository is MIT (`LICENSE.txt`, "Copyright (c) 2014 StAkira"); the file was committed by that copyright holder. CMUdict is under a permissive Carnegie Mellon licence
   (redistribution and use with or without modification, provided the copyright notice and conditions are kept); BLT already ships that notice
   (`packaging/licenses/upstream_CMUdict_0.07_licence.txt`, in `NOTICES.txt`).

## 3. What is NOT established

* **No document states what this binary was trained on, with which toolkit, or under which licence.** Item 1 above is the strongest evidence, and it is circumstantial: the recipe was published 14 months after the file, in a later
  version of the training code (PyTorch 2.0, not 1.10), and a match of dimensions says the architecture is the same, not that the data was.
* No one involved has confirmed anything. **The upstream inquiry is still not sent** ([upstream-g2p-plus-issue.md](upstream-g2p-plus-issue.md); text in `docs/upstream/`; the permission to post to a third-party repository was
  refused in M16 and I did not work around it). Its question B now says what this page found and only asks to confirm it.
* Whether weights trained on CMUdict are "derived" from it in a way that engages the CMUdict licence is a legal question. Under that licence the answer matters little (the notice is shipped either way), but a
  reviewer, not BLT, should say so.
* The plus pack's model (`g2p-arpabet-plus.zip`, unknown origin) is not in BLT's build and is not discussed here.

## 4. What genuinely depends on it

The model is used in exactly one place: `G2pPack.Query` asks the dictionary first and calls `Predict` (the model) only for a word the dictionary does not have.

| | needs the model? |
|---|---|
| Any word of CMUdict (133,852 entries incl. variants) | **no**: dictionary lookup, byte-identical with or without the model (tests below) |
| A word outside CMUdict | **yes**: without it the phonemizer reports "word not found"; the note is phonemized to nothing |
| BLT's supported engines: `DefaultPhonemizer`, `ArpasingPhonemizer`, `EnglishVCCVPhonemizer`, `EnXSampaPhonemizer` | the default never touches it; the three English ones only for words outside CMUdict |
| Present in the host but not supported (non-English dictionaries are empty): ENtoJA, Enunu English, DiffSinger English | same single use |
| Lyrics helper / Phonetic Assistant of the OpenUtau GUI | not in BLT's host |
| The native **onnxruntime.dll** (and its third-party notices) | shipped **only** to run this model; the neural renderers are not offered |

Words outside CMUdict are not rare in this repertoire. A spot check of 33 words typical of old-time and barbershop lyrics found **9 missing**: `ev'ry`, `heav'n`, `o'er`, `'neath`, `e'en`, `lov'd`, `mammy`,
`alabamy`, `mmm`. The model guesses `ev'ry → eh v r iy`, `heav'n → hh eh v ah n`, `o'er → ow er`, `'neath → ih n eh th`, `lov'd → l aa v d`, `mammy → m ae m iy`: usable, sometimes wrong, always reviewable by the singer.
(Reproduce with the two scripts above; the 33-word list is only a spot check, not a measurement of any real repertoire.)

## 5. The variant without the model (`host/build.ps1 -ExcludeG2pModel`, `packaging/build.ps1 -ExcludeG2pModel`)

* `host/patch_openutau.py --exclude-g2p-model` rebuilds `g2p-arpabet.zip` with only `dict.txt` and `phones.txt` (their bytes unchanged) and lets `G2pPack.LoadPack` accept a pack without `g2p.onnx`
  (one line: no inference session). Nothing else of OpenUtau changes, and no other model is put in its place.
* The build drops `onnxruntime.dll` from the host: one fewer native library, and its long third-party notice list, in the package.
* **Cost:** every word outside CMUdict now yields no phonemes. BLT already refuses silent notes, so a song with such a word is not generated quietly wrong: the stem check stops with
  `STEM_NOTE_SILENT` ("note(s) … render as silence … the voicebank cannot sing those lyrics"), which is true but does not say that the cause is the dictionary. The user's remedy is the one OpenUtau offers: respell the word
  with words CMUdict has, or give a phonetic hint. **BLT has no screen for this yet**; a new GUI feature was not added (M12/M13 rule). If this variant is chosen, an explanation for that case should be added first.
* **Evidence it works:** the host integration tests of `tests/integration/test_render_host.py` pass on both builds (CI builds and runs both); `blt-render-host --g2p-check` proves in the variant that a dictionary word is
  phonemized, a word outside it gets no guess and no onnxruntime is even loaded; `host/verify-host.ps1`, `packaging/verify_absent_data.py --without-g2p-model` and `packaging/verify_host_inventory.py --g2p-model excluded` pass on it.

## 6. Options for the owner (the gate item records the choice: `release_gate.py sign g2p-model-provenance … --decision included|excluded`)

| Option | What it takes | Consequence |
|---|---|---|
| **A. Keep the model** (default build) | a person accepts the evidence of §2, or upstream answers the inquiry (post it: command in `upstream-g2p-plus-issue.md`) | unchanged behaviour; a licence statement for the model still does not exist in writing |
| **B. Ship without it** (`-ExcludeG2pModel`) | nothing more for the build; decide how users learn about words outside CMUdict (§5) | no model, no onnxruntime in the package; words outside CMUdict need respelling |
| **C. A model BLT trains itself** from CMUdict with the upstream recipe (`py/g2p` at the pinned commit; MIT) | owner approval (this would be a different model, so it was not done or silently assumed), a GPU-less training run, an ONNX export, then the same evidence as this page | provenance fully under BLT's control; behaviour close to, not identical with, the shipped model |

My recommendation, as a view and not a sign-off: A or B are both defensible; do not release while the item is unanswered. If no answer from upstream or counsel arrives in time, B is the conservative choice and costs
a class of words that the singer can respell.

## 7. How the build keeps this honest

Three independent checks run on the **packaged** host, in `packaging/build.ps1`, in the smoke test (on the installed copy) and in CI, for both variants:

1. `packaging/verify_host_inventory.py` runs the host's own `--inventory` (it reads the assemblies, nothing of OpenUtau runs) and compares it with the reviewed allow-list `compliance/host-inventory.json`:
   every phonemizer class, every embedded resource with its size and SHA-256 (and the members of the embedded archives), the **set of all 1,317 types** (count and hash), and the one model that may be present. It fails
   on anything not on the list, on a changed byte, on a removed engine (Arpasing+, English C+V, DiffSinger English+, anything named Voicevox) coming back, on the model when the build was meant to lack it (or lacking when it was
   meant to have it), and on an `onnxruntime.dll` that does not match. It also searches the two OpenUtau assemblies for the removed class names as bytes, which needs no loading.
2. `packaging/verify_absent_data.py` searches **every file** of the package, whatever it is called, for the bytes of the removed data (the plus pack, the C+V template, the other languages' packs, the Vogen models and, with
   `--without-g2p-model`, the model as a loose file).
3. `host/verify-host.ps1` reflects on the built assemblies (and, since Windows PowerShell 5.1 cannot load .NET 8 assemblies, also scans their bytes) and compares the English pack member by member with the pinned source.

**Proof that the checks can fail.** `host/negative-control.ps1` builds the host from the *unpatched* pinned OpenUtau (Voicevox classes, the plus dictionary, Arpasing+, English C+V, every language's dictionary) and requires all three
checks to refuse it, each naming the specific things it must find (CI runs it). Finding it was worth doing: the first version showed that `verify-host.ps1`'s type check was blind under Windows PowerShell 5.1 (it saw no Voicevox
type in a host full of them); the byte scan and the type list now cover that.
