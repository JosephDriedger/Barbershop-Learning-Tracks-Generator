# DRAFT, not sent: issue for stakira/OpenUtau

**Title:** Provenance and licence of `g2p-arpabet-plus.zip` (the 120k entries beyond CMUdict)

Hello, and thank you for OpenUtau.

I redistribute a headless build of OpenUtau.Core (MIT) in an Apache-2.0 application and am checking the licences of
everything embedded in it. `OpenUtau.Core/G2p/Data/g2p-arpabet-plus.zip` has 420,422 entries; 299,535 of them match CMUdict 0.07,
and about 120,887 do not (for example `'sblood`, `'tisn't`). The commit that added the file (`ba93f8b3`, February 2024, @cadlaxa)
and the files that use it (`ArpabetPlusG2p`, `ArpasingPlusPhonemizer`, `EnglishCpVPhonemizer`) do not say where the additional
entries come from or under which licence they can be redistributed.

Could the contributor (or a maintainer) tell me:

1. which sources the additional entries were taken or derived from;
2. the licence of those sources (and of the model trained alongside the dictionary, if any);
3. whether the additions can be redistributed under OpenUtau's MIT licence, and if so whether a licence note could be added
   to the repository (for example a `README` beside the zip).

If the answer is that the origin cannot be established, I will ship the plain CMUdict pack instead; no action needed from you.

Thank you.
