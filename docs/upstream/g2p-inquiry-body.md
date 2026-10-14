### Description of the new feature / enhancement

Hello, and thank you for OpenUtau.

I redistribute a headless build of OpenUtau.Core (MIT) inside an Apache-2.0 application and am checking the licence of every data file in it.
Two sets of data in `OpenUtau.Core/G2p/Data` have no stated origin that I can find:

**A. `g2p-arpabet-plus.zip`** (added in #1038 by @Cadlaxa). Its `dict.txt` has 420,420 lines. About 212,700 of its 258,522 distinct entries are CMUdict 0.7b
entries or forms of CMUdict words, but 45,819 entries (37,558 words, for example `kiva`, `negentropy`, `shigella`) are not in CMUdict, and I cannot find where they or their
pronunciations came from: not in the commit messages (`ba93f8b3` ... `8b8104ae`), not in #1038, not in the contributor's repository
(Cadlaxa/Syllable-Based-ARPAsing-Phonemizer, which has no licence file either). The zip also holds a g2p model (`g2p.onnx`, 1,779,659 bytes).

**B. `g2p-arpabet.zip`** (added by @stakira in `eebdf6cd`, "add g2p packs", 2022-02-24). Its dictionary is exactly CMUdict 0.7b (thank you: that is clear from its header), but
its `g2p.onnx` (1,769,706 bytes, used for words that are not in the dictionary) and `phones.txt` come with no description of how they were produced. What I could find: the model was
exported with PyTorch 1.10 (ONNX IR 7, opset 11); its weights have exactly the dimensions of `py/g2p/en_us/cfg.yaml` in the same tree (`d_model: 64`, `d_hidden: 128`, 2 + 2 layers,
32 graphemes, 43 phonemes), and that recipe (`py/g2p/train.py`, added in `4dca53d7`, 2023-04) trains from `cmudict-0.7b`; the model reproduces CMUdict at PER 8.2 % / WER 32 % on dictionary words, which is the range
the g2p trainer reports for validation. So I *think* the shipped model is that recipe trained on CMUdict 0.7b only, but nothing in the repository says so.

Could @Cadlaxa (for A) and @stakira (for B), or whoever knows, please answer:

1. **Provenance.** Which sources were the additional dictionary entries and pronunciations of A taken or derived from (another dictionary, a word list, scraped pages, output
   of a trained model, written by hand)? How was each `g2p.onnx` produced (which toolkit, which training script)?
2. **Training data.** On which data was each `g2p.onnx` (the plain pack's and the plus pack's) trained and validated: CMUdict only, or something else? For the plain pack, is my reading above right
   (the `py/g2p` recipe, `cmudict-0.7b`, no other data)?
3. **Licence.** Under which licence is each of those sources and training data, and were any used under a licence that restricts redistribution or derived models?
   What is the licence of each trained model itself?
4. **Redistribution rights.** Do you agree that the dictionary additions in A and both models may be redistributed under OpenUtau's MIT licence? If so, could a short note
   stating the sources and licences be added next to the zips (for example a `README` in `OpenUtau.Core/G2p/Data`)?
5. **Reproducibility.** If the models were trained from CMUdict with a public toolkit, could the recipe (toolkit, version, command, hyper-parameters) be recorded, so that
   downstream projects can regenerate them from CMUdict alone?

### Proposed technical implementation details

No code change is needed from you. If the sources are documented and permissive, a note beside the files is enough. If the origin cannot be established, I will keep shipping without A,
and I would ask nothing further for it; for B I would then look for a way to regenerate the model from CMUdict. There is no urgency on your side; my own build already excludes A.

Thank you for your time.
