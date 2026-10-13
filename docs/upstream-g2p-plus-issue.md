# DRAFT: upstream inquiry about the English "plus" dictionary (NOT POSTED)

**Status: prepared for the owner's approval. Nothing has been posted, sent or commented anywhere.** The owner posts it
(or tells BLT to), after reading this page. Details checked on 2026-10-13 with the public GitHub API.

## Where, who, what

| | |
|---|---|
| Repository | **openutau/OpenUtau** (https://github.com/openutau/OpenUtau; `stakira/OpenUtau` redirects to it). MIT licence. Default branch `master`. |
| Contributor | **@Cadlaxa** (GitHub login `Cadlaxa`), author of pull request **openutau/OpenUtau#1038** "Add ARPAsing Plus Phonemizer" (merged by **@stakira** on 2024-03-28) and of all 6 commits that touch `g2p-arpabet-plus.zip`: `ba93f8b3` (2024-02-16, "Add Arpabet Plus G2P"), `97365778`, `3f4bfeaf`, `ddeffd5b`, `5ed2dff3`, `8b8104ae` (2024-06-21, "Update ARPA+ G2p Dictionary (preparing for model retrain)") |
| The file | `OpenUtau.Core/G2p/Data/g2p-arpabet-plus.zip` (4,327,034 bytes; SHA-256 `9fc73c72a112084820cccbe1ddecdd36b8c20a757428c16f0a8bacf758f88733`): `dict.txt`, `g2p.onnx` (a neural model), `phones.txt` |
| Contributor's own repository | https://github.com/Cadlaxa/Syllable-Based-ARPAsing-Phonemizer: has issues enabled, **no licence file** (`license: null`), README without a word about the dictionary's sources |
| Existing discussion | none: no issue or pull-request comment in openutau/OpenUtau names a source for the dictionary (searched "arpabet plus" and "dictionary license"; PR #1038 has one comment, from the maintainer, about a failing test) |
| How to post | The repository disables blank issues; its forms are "Bug report" and "Feature Request / Idea". Use the **Feature Request / Idea** form and fill the sections below (acknowledgement box, description, proposed change). Or ask in the project's Discord (link on the issue chooser). |
| Optional second place | a short issue on `Cadlaxa/Syllable-Based-ARPAsing-Phonemizer` pointing to the first, so the contributor is notified even if they no longer watch OpenUtau. Only with the owner's approval. |

## Evidence the inquiry rests on (reproducible)

`python scripts/analyze_g2p_plus.py <OpenUtau 0.1.565 checkout> --cmudict cmudict-0.7b` (read-only; CMU's original file
from `https://svn.code.sf.net/p/cmusphinx/code/trunk/cmudict/cmudict-0.7b`, SHA-256 `209a8b4c…29e4`):

* the plain `g2p-arpabet.zip` dictionary has exactly the 133,852 entries of CMUdict 0.7b (header: "CMUdict -- Major Version: 0.07");
* `g2p-arpabet-plus.zip` has 420,420 dictionary lines (258,522 distinct after lower-casing): 74,227 identical to CMUdict entries,
  138,476 other forms of CMUdict words (variants, apostrophe-marked forms such as `'bout` / `bout'`), and **45,819 entries for
  37,558 words that are not in CMUdict at all** (for example `kiva`, `negentropy`, `shigella`, `stuiver`, `baronage`);
* nothing in the repository, the pull request, or the contributor's repository says where those words or pronunciations come from.

## The text to post (Feature Request / Idea form)

**Title:** Provenance and licence of `g2p-arpabet-plus.zip` (entries beyond CMUdict)

**Description of the new feature / enhancement**

Hello, and thank you for OpenUtau.

I redistribute a headless build of OpenUtau.Core (MIT) inside an Apache-2.0 application and am checking the licence of every
data file in it. `OpenUtau.Core/G2p/Data/g2p-arpabet-plus.zip`, added in #1038 by @Cadlaxa, contains a dictionary of 420,420
lines. About 212,700 of its 258,522 distinct entries are CMUdict 0.7b entries or forms of CMUdict words, but 45,819 entries (37,558
words, e.g. `kiva`, `negentropy`, `shigella`) are not in CMUdict, and I cannot find where they or their pronunciations came from:
not in the commit messages (`ba93f8b3` … `8b8104ae`), not in #1038, not in the contributor's repository
(Cadlaxa/Syllable-Based-ARPAsing-Phonemizer, which has no licence file either). The zip also holds a g2p model (`g2p.onnx`).

Could @Cadlaxa (or @stakira, if they know) please answer:

1. Which sources were the additional dictionary entries and pronunciations taken or derived from (another dictionary, a word list,
   scraped pages, output of a trained model, written by hand)?
2. Under which licence is each of those sources, and were any of them used with a licence that restricts redistribution?
3. On which data was `g2p.onnx` in the plus pack trained, and under which licence is that data?
4. Do you agree that these additions may be redistributed under OpenUtau's MIT licence? If so, could a short note stating the sources
   and licence be added next to the zip (for example a `README` in `OpenUtau.Core/G2p/Data`)?

**Proposed technical implementation details**

No code change is needed from your side. If the sources are documented and permissive, a note beside the file is enough. If the
origin cannot be established, I will ship OpenUtau's plain CMUdict pack only (that is already done in my build, so there is no
urgency), and downstream projects could do the same.

Thank you for your time.

## What BLT does with each answer

| Answer | BLT's action |
|---|---|
| Sources and licences documented, redistribution allowed | `docs/g2p-plus-provenance.md` updated with the evidence; the owner may then decide to re-include the pack and the Arpasing+ and English C+V phonemizers (the patch change is small), with the notices the licences need. A new review item would be added to the release gate. |
| Answer says some sources are restricted or not redistributable | Keep it excluded; record the answer. |
| No answer | Keep it excluded. Nothing else depends on an answer: the supported English phonemizers run on CMUdict only. |

## Secondary observation (not part of the inquiry above)

The plain pack's `g2p.onnx` (used for words that are not in CMUdict) comes with no stated training data either. That is a model,
not a dictionary, and BLT's position (see `docs/g2p-plus-provenance.md`) is that it is a residual item for the owner to be aware of.
It could be added as question 5 if the owner wants the whole g2p area cleared at once.
