# DiffSinger voices (internal host variant)

BLT's release sings UTAU-style voicebanks with WORLDLINE-R. This page describes the **internal** way to sing a DiffSinger voicebank
such as **Tiger** (`TIGER_DS_v106`, a free English DiffSinger bank for OpenUtau used with the *DIFFS EN+* phonemizer; BLT never ships it).
Its licence (`extra/LICENSE.md` in the bank, read in the v106 pack from
https://github.com/spicytigermeat/tiger_diffsinger/releases/tag/v106) is the author's own, not CC BY-NC-ND: free use as long as nobody is harmed,
**no commercial use without buying a licence**, the copyright notice kept with copies, and the artwork not used to train image models.
Non-commercial quartet practice is within it.

**Status: not verified, not releasable.** No DiffSinger voice has been rendered through BLT yet (Tiger was not on the machine
that this was written on), and the host it needs contains data whose origin is unknown.

## Why it is a separate host build

*DIFFS EN+* (`DiffSingerARPAPlusEnglishPhonemizer`) uses the English "ARPAbet plus" dictionary and g2p model, which the release host omits
because their origin is unknown ([g2p-plus-provenance.md](g2p-plus-provenance.md)). Putting them back in the release would need the documented
upstream answer that document asks for, and would reopen the release-gate items about the host. So the data is kept out of the default build and
comes in only with a flag:

```
powershell -NoProfile -ExecutionPolicy Bypass -File host\build.ps1 -IncludeDiffSinger
```

`-IncludeDiffSinger` (like `-IncludeG2pModel`) writes to its own folders (`...-diffsinger-research`), records `arpa_plus: included` and
"INTERNAL RESEARCH ONLY" in `blt-host-build.json`, and keeps the native `onnxruntime.dll` that DiffSinger runs on. The patch behind it is
`host/patch_openutau.py --include-arpa-plus`: it keeps the plus pack, `ArpabetPlusG2p`, the lyrics helper and the DiffSinger English+ phonemizer;
Arpasing+ and English C+V stay omitted. `verify-host`, `verify_absent_data.py` and the release gate are written for the default build and are
**expected to fail on this variant**; do not package it.

## Using it

1. Put the `TIGER_DS_v106` folder in the voices folder (*Add voicebank* accepts it; it notes that it is a DiffSinger voice).
2. Use the DiffSinger edition of BLT (the installer built with `packaging\build.ps1 -IncludeDiffSinger`, or point `--host-dir` / *Singing engine
   folder* at the variant host). Its host build record says `arpa_plus: included`, which is how BLT knows it can sing DiffSinger voices.
3. Generate as usual; nothing has to be chosen for the voice type:

```
python -m barbershop_tracks generate score.musicxml ... --singer TIGER_DS_v106
```

**Each voice is sung by what its voicebank is.** A DiffSinger voicebank gets the DIFFSINGER renderer and
`OpenUtau.Core.DiffSinger.DiffSingerARPAPlusEnglishPhonemizer`; a UTAU-style one keeps the renderer and the pronunciation engine that were chosen
(or detected from its sounds). A quartet may mix them (`--singer LEAD=TIGER_DS_v106 --singer TENOR=Bennett ...`), and the mix drops DiffSinger's
tail only on the DiffSinger voices. BLT says so in a warning (`ENGINE_BY_VOICEBANK`). `--renderer DIFFSINGER` still works and is not needed. On a
host that is not the DiffSinger edition a DiffSinger voicebank is refused before anything is rendered, and says why.

## What differs from the UTAU path

* Words are sent whole (`together` + `+` + `+~`), as for Arpasing: the DiffSinger phonemizers group notes the same way.
* The phonemizer does its own g2p, including the neural fallback of the plus pack: an unknown word is **guessed** and is not reported, so
  the "BLT never guesses" stop does not apply. **Pronunciation overrides, the fermata tail logic and built-from-pieces words are not available.**
* The host switches OpenUtau's DiffSinger tensor cache off and discards `ds-*.wav` phrases before rendering, like the WORLDLINE-R ones.
* Depth and steps are OpenUtau's preferences (1.0 and 20 by default). CPU inference is slow: allow a long time limit.

## What the first Tiger run showed (2026-10-26, the 8-bar kit score `english-quartet-known-words`, CPU)

* `TIGER_DS_v106` (from `TIGER_DS_v106_PACK.zip`, GitHub release v106; installed with `voices add` on the bank zip inside the pack) is
  accepted by the install code and the DIFFS EN+ phonemizer resolves with the bank's own `dsdict-en.yaml`. The pack's two plugin DLLs are not used.
* All four parts rendered, the 13 tracks were published, all of one length (962,182 frames), about 38 s for the whole run. Every part is audible
  in every second of its Solo.
* **Every stem ends about 100 ms past the score** (100.8 to 108.2 ms; the release that DiffSinger adds after the last note, `tailMs`), so the
  mix refused it (`MIX_STEM_TOO_LONG`) as it does for CLASSIC. For the DIFFSINGER renderer only, the mix drops a tail of up to 130 ms and
  -20 dBFS and fades the last 30 ms before the cut (`DIFFSINGER_TAIL`, recorded in the manifest's `tail_policy`).
* **Two renders of the same score are not the same bytes** (the diffusion noise lives inside the ONNX model; OpenUtau has no seed). The UTAU path
  is bit-for-bit. Listen to each render you rely on.

## Still to check

* by ear: the owner listened to the 8-bar test tracks and said they "sound good" (an informal listen, no scores per part, no notes on the ends
  after the fade); the acceptance scoring below has not been done;
* the acceptance checklist ([acceptance/english-voicebank-acceptance.md](acceptance/english-voicebank-acceptance.md)) with Tiger;
* a score with words the dictionary lacks (the plus pack guesses them), a fermata, a pickup, and a long score (time and memory);
* GPU inference (not tried).
