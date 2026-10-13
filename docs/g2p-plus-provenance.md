# The English "ARPAbet plus" dictionary: provenance, dependency and BLT's release-safe fallback

Status (M15): **excluded from BLT's build.** The dictionary's origin is still unknown and no upstream answer exists, so this is
resolved by *exclusion*, not by provenance. Re-including it would need a documented answer first. The upstream inquiry is a
draft ([upstream-g2p-plus-issue.md](upstream-g2p-plus-issue.md)) that **has not been sent**.

## What it is

`OpenUtau.Core/G2p/Data/g2p-arpabet-plus.zip` (OpenUtau 0.1.565, 4,327,034 bytes, SHA-256 `9fc73c72…8733`): `dict.txt`, a neural
`g2p.onnx` and `phones.txt`. Added by the contributor **Cadlaxa** with pull request openutau/OpenUtau#1038 (merged 2024-03-28 by
stakira); six commits by Cadlaxa touch it, 2024-02-16 to 2024-06-21. Neither the commits, the pull request nor the contributor's own
repository (no licence file) state where the additional data comes from.

Reproducible measurements (`python scripts/analyze_g2p_plus.py <checkout> --cmudict cmudict-0.7b`):

| | |
|---|---|
| Plain pack `g2p-arpabet.zip` dictionary | 133,852 entries, **exactly the entries of CMU's `cmudict-0.7b`** (compared entry for entry; only line endings differ) |
| Plus pack dictionary lines | 420,420 (258,522 distinct after lower-casing) |
| of which identical to a CMUdict entry | 74,227 |
| of which another form of a CMUdict word (variants, apostrophe-marked forms) | 138,476 |
| **entries for words that are not in CMUdict** | **45,819 entries, 37,558 words** (e.g. `kiva`, `negentropy`, `shigella`) |

(M13 and M14 quoted "299,535 CMUdict words / 120,887 additions" from an ad-hoc count; the numbers above replace them because
they can be re-run.)

## What depends on it (traced in the pinned source, commit `a60ca58`)

| Consumer | Uses plus? | BLT |
|---|---|---|
| `DefaultPhonemizer` (BLT's default) | no (the voicebank's own aliases) | supported |
| `ArpasingPhonemizer`, `EnglishVCCVPhonemizer`, `EnXSampaPhonemizer`, ENtoJA, Enunu English, DiffSinger English | no: plain `g2p-arpabet` (CMUdict, plus a neural fallback for words not in it) | supported (the first three are tested end to end) |
| `ArpasingPlusPhonemizer` ("EN ARPA+") | yes | **omitted** |
| `EnglishCpVPhonemizer` ("EN C+V"; also uses a 1.2 MB template of its own) | yes | **omitted** |
| `DiffSingerARPAPlusEnglishPhonemizer`, `ArpabetPlusG2p`, the lyrics helper, the Phonetic Assistant | yes | omitted / not built |

English singing therefore never needed the plus dictionary unless Arpasing+ or English C+V were picked by name.

## The fallback (implemented, tested)

* `host/patch_openutau.py` deletes the pack, the three phonemizers, `ArpabetPlusG2p`, the lyrics-helper class and the English C+V
  template from the patched sources **and from the resource tables** (`Resources.resx`, `Resources.Designer.cs`), so the data is in
  the built assemblies neither as a resource nor as a file.
* `host/verify-host.ps1` (reflection) fails if a plus resource, a `*Plus*`/`EnglishCpV` type or the C+V template is present, and still
  requires the CMUdict pack to be byte-identical to the pinned source.
* `packaging/verify_absent_data.py` does not trust the patch: it fingerprints every removed data file as it is in the pinned source
  and searches **every file of the package folder** for those bytes. As a positive control it finds the plus pack and the C+V template
  in the previous (M14) host build; on the M15 build it finds nothing. It runs in `packaging/build.ps1` and in CI.
* Tests: the host refuses `ArpasingPlusPhonemizer`, `EnglishCpVPhonemizer` and the DiffSinger English+ phonemizer with exit 4 ("did not
  resolve"); `ArpasingPhonemizer`, `EnglishVCCVPhonemizer` and `EnXSampaPhonemizer` render all four stems against the real host;
  `tests/unit/test_verify_absent_data.py` checks that the scanner finds the data under any file name and refuses a vacuous pass.

## Residual items for the owner (not blockers of this exclusion)

1. The plain pack's `g2p.onnx` (the neural fallback for words not in CMUdict) has no stated training data either. It is a model, not a
   dictionary; the question can be added to the upstream inquiry.
2. Users lose two upstream phonemizers (Arpasing+, English C+V). Recorded in `docs/KNOWN-LIMITATIONS.md`.
3. If the upstream answer is positive and documented, re-inclusion is a small change to the patch plus a new review item in the
   release gate.
