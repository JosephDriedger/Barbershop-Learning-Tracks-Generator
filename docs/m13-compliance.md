# M13: release-compliance investigation

Status: **investigation only. Every artifact is still NOT FOR RELEASE and no blocker is marked resolved.**
Four blockers remain (`worldline.dll`, `OpenUtau.Core.dll`, the PySide6/Qt LGPL position, the Visual C++
runtime); BLT's own copyright holder is now recorded. Nothing was published or uploaded. The changes below that
would alter what ships are *proposals* for review; the prototypes that back them live in `research-output/`
(git-ignored) and are reproducible from `packaging/prototypes/m13/`.

| Blocker | Finding in one line | Proposed resolution | Needs |
|---|---|---|---|
| `worldline.dll` | One GPL-2.0-or-later file (`tk::spline`) is compiled in and runs on **every** rendered frame; everything else is permissive. The M12 note about libpyin was wrong | BLT-owned MSVC rebuild with a two-line change replacing the spline (prototype: output byte-identical to today's) | Review of the replacement; owner decision to own a native build |
| `OpenUtau.Core.dll` | LGPL-3.0-derived Voicevox classes; embedded data of unknown provenance (CMUdict is *known*: BSD-style, notice added) | Build the pinned source with the Voicevox classes, Vogen data and non-English dictionaries removed (prototype: DLL 25 MB to 10 MB, 44 of 46 host tests pass, the other 2 only check the version string) | Owner decision; upstream answer on the English "plus" dictionary |
| PySide6/Qt | LGPL-3.0 conditions are met technically (separate replaceable DLLs, shown); written source offer and prominent notice were incomplete | Concrete written offer and hosted source archives with each release; notice in the About box (done) | Legal review of the offer |
| Visual C++ runtime | Microsoft permits redistribution only to licensed Visual Studio users; the 11 copies shipped came from third parties; the .NET host directory has none, so a PC without the runtime cannot render | Do not ship Microsoft DLLs; installer checks for the Microsoft runtime and sends the user to Microsoft's installer (or, alternatively, ship the files from the owner's licensed VS 2026 with the licence's three conditions) | Owner choice; legal review only for the "ship it" option |
| BLT copyright | Owner declaration recorded: `Copyright 2026 Joseph Driedger` | done: `LICENSE`, `NOTICE`, metadata, About box | none beyond the owner's own assertion |

## 0. BLT's copyright and the Apache-2.0 review

* `LICENSE` is the SPDX Apache-2.0 text token for token, with only the appendix line filled in:
  `Copyright 2026 Joseph Driedger`. A `NOTICE` file carries the same line and points to the third-party notices.
  `pyproject.toml` (authors), the Windows version resource, the installer publisher, the About box and
  `NOTICES.txt` follow. The package now ships `LICENSE.txt` and `NOTICE`.
* Evidence for ownership: the owner's written declaration (M13 instruction, 2026-10-12); git history has one author
  (Joseph Driedger, 108 commits and one GitHub web commit); the repository contains no third-party source
  files (test scores are hand-written, the icon is drawn by code). Residual: the declaration is an assertion; a
  lawyer may want to look at how AI-assisted code affects ownership.
* Apache-2.0 section 4 for what BLT conveys: licence copy included (installer licence page, `LICENSE.txt`); no
  modified Apache-licensed files; NOTICE obligations of Apache-licensed dependencies: none of the NuGet packages
  (NumSharp, Serilog, csharp-kana, csharp-pinyin) ships a NOTICE file; `Microsoft.Extensions.ObjectPool` ships
  `THIRD-PARTY-NOTICES.TXT` (included); Abseil has none, and OpenSSL's source tree was not checked for one. Source-file headers are optional and absent.
* Added this milestone because the binaries require them even without any change: attributions for World,
  libgvps, libpyin, libnpy, miniaudio, xxHash, Abseil (inside `worldline.dll`) and the CMUdict licence (inside
  `OpenUtau.Core.dll`), with verbatim texts.

## 1. `worldline.dll` (OpenUtau 0.1.565, `runtimes/win-x64/native/worldline.dll`)

**What it is.** SHA-256 `1a478b29...`, 363,520 bytes, x64, PE timestamp 2024-07-28 03:56 UTC. The OpenUtau commit that
last changed it is `6958d68b648bdd734d1eafa9e49b02657ca9d18e` ("miniaudio fixes", 2024-07-28), committed by the
maintainer (not a CI build; CI rebuilds only started in 2026). Its `cpp/` tree at that commit differs from the tag's
`cpp/` only in `audio_output.*` and `.bazelrc`. Exports: `F0 DecodeMgc DecodeBap WorldSynthesis Resample PhraseSynth*`
and the `ou_*` audio-device functions. It is stripped: no symbols, no strings from its libraries.

**What is compiled into it** (Bazel graph `cpp/worldline/BUILD.bazel`, third-party pins in `WORKSPACE.bazel` and
`MODULE.bazel`; every archive hash re-checked by `prepare.py`). A faithful MSVC rebuild from those exact sources
(`/O2`, link map kept) contains objects from:

| Component | Version / pin | Licence (evidence) |
|---|---|---|
| OpenUtau worldline sources | `6958d68` | MIT (repository LICENSE) |
| World | `f8dd5fb` | BSD-3-Clause (modified; `LICENSE.txt` in the archive) |
| PLATINUM (`worldline/platinum`) | extracted from World 0.1.4_3 | files say only "Copyright 2012-2015 Masanori Morise. All Rights Reserved."; no licence text (residual, low: same author and package as World) |
| libgvps | `2f1b410` | BSD-3-Clause (`LICENSE`) |
| libpyin | `b381353` | **BSD-3-Clause**: every source file carries the licence header (Copyright 2015-2017 Kanru Hua); the repository has no LICENSE file. *Correction of the M12 audit, which called it unlicensed.* |
| libnpy | 1.0.1 | MIT |
| miniaudio | 0.11.21 | public domain (Unlicense) or MIT-0, user's choice |
| xxHash | 0.8.2 | BSD-2-Clause (library) |
| Abseil (strings, int128, raw logging) | 20240116.1 | Apache-2.0 (no NOTICE file). *Not in the M12 audit.* |
| **tk::spline** (`spline.h`) | `ttk592/spline` `5894bea` | **GPL-2.0-or-later**: the header says "version 2 of the License, or (at your option) any later version", the repository has `LICENSE` = GPL-2.0, and no linking exception was found |

**Is the GPL code really in the binary, and used?**
* Source: `worldline/model/effects.cpp` includes `spline.h` and uses `tk::spline` in `GetTensionCoefficients`. That
  function is called per frame by `Resampler::ApplyEffects` (CLASSIC path, `Resample`) and by `PhraseSynth`
  (`phrase_synth.cpp:164`, the WORLDLINE-R path BLT uses), for every frame with f0 >= 50 Hz, *even when the tension value
  is 0* (the spline of all-zero data then evaluates to exactly 1.0). So it is live code on BLT's own render path, not an
  unused leftover.
* Binary: the shipped DLL cannot be inspected symbolically. A rebuild from the same sources with `/OPT:REF` keeps 17
  `tk::spline` symbols in the link map (`effects.cpp.obj`); the same rebuild with the patch below has 0. A rebuild
  produces **identical rendered audio** to the shipped DLL (13 of 13 WAVs, 0 LSB difference), which supports, but
  does not prove, that the shipped DLL has the same composition. Residual uncertainty about the stripped binary is
  removed only by shipping a binary BLT built itself.

**Obligations if shipped as is.** A binary containing GPL-2.0-or-later code may be conveyed only under GPL terms: the
corresponding source of the whole combined work and no added restrictions. BLT loads the DLL by P/Invoke, so treating the
host as a separate program is not a safe assumption. Not acceptable for an Apache-2.0 product without legal advice.

**Proposed resolution (prototype built and tested).**
1. Replace `tk::spline` in `effects.cpp` by an original natural cubic spline (`natural_spline.h`, Apache-2.0, written from the
   textbook definition: second derivatives from the tridiagonal system, Thomas algorithm; same end conditions and
   linear extrapolation as tk::spline's default). The source change is two lines (`effects-natural-spline.patch`).
   **Disclosure:** the author of the replacement had read tk::spline's source while checking its default behaviour, so
   this is not a clean-room implementation; the formulation differs (second derivatives and Thomas algorithm versus
   its band-matrix LU on the cubic coefficients), but a lawyer should judge that, or a permissively licensed spline
   (for example from a library under MIT/BSD) can be substituted.
2. Build `worldline.dll` ourselves with CMake and MSVC from the pinned sources (`packaging/prototypes/m13/`:
   `prepare.py`, `CMakeLists.txt`, patches). With `/Brepro`, two builds in different directories were byte-identical.
3. Evidence collected: 864 parameter combinations of `GetTensionCoefficients` (830,304 values): max absolute difference
   1.6e-14 from tk::spline (95.8 % bit-identical), exactly 1.0 for tension 0; full runs of `blt selftest` with the original
   DLL, an unpatched rebuild and the patched rebuild produce byte-identical WAVs; the host-test suite passes with the patched
   DLL. No tk::spline symbol remains in the patched build's link map; the export list and imports equal the original's.

**Source/build changes required.** Add the CMake build and the pinned-source fetch to `packaging/build.ps1` (needs the
MSVC build tools, present on GitHub runners and on a developer PC with Visual Studio), ship the new DLL, update the audit
(`worldline` components list, remove tk::spline from the licence field), keep the upstream notices above. No other change.

**Remaining obligations after the fix.** Reproduce the notices of World, PLATINUM (as World), libgvps, libpyin, libnpy,
miniaudio, xxHash, Abseil and OpenUtau (done in `NOTICES.txt`); keep the patched files marked as changed. The build then
statically links the Microsoft CRT pieces that MSVC always links (standard).

**Legal review / upstream permission.** Review of the replacement spline recommended; no upstream permission needed.
Alternatively ask Tino Kluge for permissive terms for `spline.h` (not relied on).

## 2. `OpenUtau.Core.dll` (OpenUtau 0.1.565, built unmodified from `a60ca58`)

**Embedded resources** (read from the shipped assembly): CREPE `tiny.onnx` 1,955,909 bytes; g2p packs: arpabet 2,459,789,
arpabet-plus 4,327,034, de 1,887,996, es 1,777,613, fr 1,772,222, it 1,694,543, ko 1,996,861, pt 1,679,178, ru 2,593,982,
ja-mono 11,028 (20.2 MB in all); Vogen data: seven files, 1.4 MB. `OpenUtau.Plugin.Builtin.dll` embeds seven small YAML
phoneme templates and the 1.2 MB `en_cPv` template.

| Item | Evidence | Licence status |
|---|---|---|
| Voicevox classes (`OpenUtau.Core/Voicevox/*`, 5 files, 1,309 lines, plus two phonemizers; `Simple*` in Plugin.Builtin) | Source comment: "partially based on the VOICEVOX engine" with a link to `LGPL_LICENSE`; the engine is LGPL-3.0 or a commercial licence | **LGPL-3.0 applies to the derived part** |
| g2p-arpabet | `dict.txt` is CMUdict 0.07 verbatim; the model is trained on it (`py/README.md`) | Carnegie Mellon BSD-style licence: notice now shipped |
| g2p-arpabet-plus | 420,422 entries: 299,535 are CMUdict words, 120,887 are additions (for example `'sblood`, `'tisn't`); added by a contributor in 2024 (`ba93f8b`) with no source named | CMUdict part known; additions **unknown** |
| g2p de, es, fr, it, ru, pt, ko, ja-mono | contributed by named people (2022-2024); dictionaries without headers or sources | **unknown** |
| Vogen models, `yue.csv` | added by the maintainer (2022-03/04, `e6486ac`, `5b698e5`); no licence statement | **unknown** |
| F0 smoother (SimpleEnunu port) | header "Copyright (c) 2022 oatsu"; upstream is MIT (repository `LICENSE`: 2023 oatsu) | MIT, text shipped |
| `Deque.cs` | matches Stephen Cleary's Nito.Collections.Deque (MIT); the file carries no notice | MIT assumed, text shipped |
| `EnunuOnnx/Merlin.cs` (Plugin.Builtin) | adapted from nnmnkwii (MIT), itself from Merlin (Apache-2.0) | texts shipped |

**Present in the distributed artifact?** Yes, all of it: the DLL is the unmodified upstream build. Whether unused code is
absent was *not* assumed: the embedded-resource list above comes from the assembly itself.

**Can they be excluded safely?** A prototype copy of the pinned source (`patch_openutau.py`, three edits plus
data stubbing) builds into a host that runs BLT's pipeline: `blt selftest` output is byte-identical to the current host
(13/13 WAVs); `OpenUtau.Core.dll` shrinks from 25.2 MB to 10.2 MB; 44 of the 46 host-driven integration tests pass and the
remaining two only assert that the reported commit equals the pinned id (the prototype appends a suffix on purpose). What
stops working: Voicevox singers, Vogen singers, and every non-English g2p. Not touched: English phonemizers built on
`g2p-arpabet` and (still embedded) `g2p-arpabet-plus`, which the English acceptance test needs.

**Proposed resolution.** Ship the prototype's build instead of the stock Core: removes the LGPL-derived code and the
unlicensed Vogen/other-language data. Keep `g2p-arpabet-plus` only if its additions are acceptable (ask the
contributor/upstream for their source) or drop it too and document that `ArpasingPlusPhonemizer` is unavailable.
**Required source/build changes:** `host/build.ps1` copies the pinned checkout, runs the patch script, builds from the copy
(the pinned commit stays verified); notices already include CMUdict, SimpleEnunu, Deque, nnmnkwii, Merlin. **Remaining
obligations:** MIT notice for OpenUtau; CMUdict notice; the three small MIT/Apache notices; none of the LGPL once the classes
are gone (the statement added in M12 can then be removed). The change makes the host a *modified* build of OpenUtau: it must
be described as such in `NOTICES.txt` and the audit.

**Legal review / upstream.** Not needed for the removal itself. Upstream confirmation is useful for `g2p-arpabet-plus`. If the
owner prefers to keep the stock binary, the LGPL handling needs legal review (separate replaceable DLL plus text and a source
offer, like Qt) and the data provenance stays an open risk.

## 3. PySide6 and Qt (6.11.2)

* **Versions and licence:** PySide6, shiboken6 and the Qt libraries 6.11.2; wheel metadata
  `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`; BLT elects the LGPL-3.0. Qt Core, Gui, Widgets and the platform/image
  plugins are all qtbase. Third-party attributions inside them are shipped (collected from qtbase's own
  `qt_attribution.json` files; string search confirmed PCRE2, FreeType, HarfBuzz, libpng, zlib, TinyCBOR and Unicode tables).
* **LGPL-3.0 conditions checked:**
  1. *Notice and licence copies:* `NOTICES.txt`, `licenses\LGPL-3.0-only.txt` and `GPL-3.0-only.txt` ship. The **About box
     now states** that BLT uses Qt and PySide6 under the LGPL-3.0 and points to the notices (was only in a file).
  2. *Replaceable library (section 4(d)):* PyInstaller one-folder keeps Qt and PySide6 as separate files. Demonstrated on a
     scratch copy: with `Qt6Widgets.dll` removed the app fails with "DLL load failed while importing QtWidgets"; a
     replacement file in the same place is used and the app starts again. (That test popped the error dialog you saw.)
     Not demonstrated: relinking against a *modified* Qt (none exists; BLT modifies nothing).
  3. *No restriction on modification and reverse engineering of the library (4(b)):* the Apache-2.0 licence page and
     installer add none; keep it that way (the Inno Setup stub has no such term).
  4. *Corresponding source (4(c), GPL-3.0 section 6):* **open.** The existing text says the source is "available from its
     project page" and on request. LGPL requires conveying the source along with the binary, or a written offer valid for at
     least three years, or equivalent access from the same place. Qt's own source servers are not "the same place".
  5. *Installation Information (User Products):* applies to consumer products; a desktop application without lock-down is not
     one, so no extra step is proposed (a point for the reviewer).
* **Proposed resolution:** with every release publish (a) a source bundle: Qt 6.11.2 qtbase archive and the PySide6 6.11.2
  sources with SHA-256, and BLT's own source and build scripts, next to the installer, and (b) a concrete written offer in
  `NOTICES.txt` naming that bundle, valid for at least three years after the last distribution of that version, and how to
  swap the libraries. **Source changes:** the offer text and a release step; the About-box text (done).
* **Remaining obligations:** retain the licence texts; if BLT ever modifies Qt or PySide6, publish the changes.
* **Legal review:** yes, for the sufficiency of the offer and the hosting arrangement. No upstream permission needed.

## 4. Visual C++ runtime

* **Files shipped** (11): Python's `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll` (14.42.34438.0, in `_internal`); NumPy's renamed
  `msvcp140-a4c2...dll` (14.40.33810.0, delvewheel); Qt's `MSVCP140`, `MSVCP140_1`, `MSVCP140_2`, `VCRUNTIME140`,
  `VCRUNTIME140_1` in `PySide6` and `shiboken6` (14.44.35211.0, signed by The Qt Company). Needed by 50+ files on the Python
  side and by `host\worldline.dll` on the .NET side (nothing else in `host\`).
* **Licence evidence (Microsoft's own pages, fetched 2026-10-12):** "Distribution of the Visual C++ Runtime Redistributable
  package, merge modules, and individual binaries is limited to licensed Visual Studio users and is subject to Microsoft
  Software License Terms" (Visual C++ redistribution page and the VS 2026 REDIST list). The Visual Studio Community 2026 terms
  (Last Updated October 1, 2025) allow copying the *object code of files on the Distributable List* if you (1) add significant
  primary functionality, (2) **require distributors and end users to agree to terms that protect the Distributable Code at
  least as much as Microsoft's terms**, and (3) **indemnify Microsoft** for claims about your application; Community may be
  used by an individual developing their own applications. So: BLT's right to pass on copies that came inside the Python, NumPy
  and Qt distributions was **not established**, and the same files taken from the owner's licensed VS 2026 install
  (`VC\Redist\MSVC\14.51.36231\x64\Microsoft.VC145.CRT`, 14.51.36247.0) would carry conditions (2) and (3).
* **A functional gap found:** `host\worldline.dll` imports `MSVCP140.dll` and `VCRUNTIME140*.dll` but the host folder has no
  copies; on a PC without the Microsoft runtime the app opens and rendering fails. (Not testable here: this PC has the runtime.)
* **Options.**
  A. *Do not ship Microsoft files; the installer ensures the runtime.* Installer detects the installed runtime (registry key
  `HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64`, `Bld` at or above the newest one our DLLs need, 14.44), and if
  missing or older tells the user to run Microsoft's `vc_redist.x64.exe` (link, or an Inno Setup download with SHA-256 and the
  user's consent); the package drops all 11 app-local copies. Cost: one UAC prompt on PCs lacking the runtime; most PCs have
  it. Licence position: BLT redistributes nothing from Microsoft.
  B. *Ship the files from the owner's licensed VS 2026 copy,* unmodified, replacing all 11, and add to the installer licence
  page a clause protecting them and an indemnity statement, accepting Community terms (an individual developer qualifies).
  Cost: a contractual indemnity and an end-user term; a release built on CI would need its own licensed source.
  **Recommendation: A.** Source changes: remove the CRT files in `packaging/blt.spec`, a runtime check page in
  `installer.iss`, and an installer-test case that simulates the missing runtime by registry check only (a real clean machine
  is needed to prove it).
* **Remaining obligations (A):** none towards Microsoft beyond the user's own installation; the runtime EULA is accepted by the
  user at install. **(B):** the three conditions above, ongoing.
* **Legal review:** not for A; yes for B (the indemnity and the end-user-terms clause).

## 5. Using the app without OpenUtau (your question)

BLT never starts or needs the OpenUtau program: it runs its own headless host (OpenUtau's engine as a library). Checked:
no process other than BLT's own and optional FFmpeg is ever launched; a run writes nothing into `Documents\OpenUtau` or the
OpenUtau AppData folders (file-timestamp check around a run); the packaged app rendered a real voicebank in a stripped
environment. The user-facing message that told people to "install voicebanks in OpenUtau's Singers folder" was reworded.

Gaps that still make you reach for something else, found while checking (not fixed, as they are features):
1. **Installing a voicebank:** BLT does not unpack voicebank zips; you extract the voicebank yourself and point BLT at the
   folder (OpenUtau's installer also copes with odd archive encodings; BLT does not).
2. **Choosing a pronunciation engine for English:** it is a text field in Advanced settings; nothing lists the built-in
   phonemizers (for English voicebanks you must type for example `OpenUtau.Plugin.Builtin.ArpasingPhonemizer`).
3. **Microsoft runtime** on a clean PC (section 4).
4. **CLASSIC renderer:** produced audio that the mix check rejects (`MIX_STEM_TOO_LONG`, also with a real voicebank); it is no
   longer offered (WORLDLINE-R only).
5. **Voicebank multi-folder layouts** were listed as many voices (fixed in M12).

## 6. Reproducing the evidence

```
python packaging/prototypes/m13/prepare.py <work> --openutau-src research-output/spike/OpenUtau-src
cmake -S <work> -B <work>/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPATCH_SPLINE=ON   # OFF = as upstream
cmake --build <work>/build --target worldline
python packaging/prototypes/m13/patch_openutau.py research-output/spike/OpenUtau-src <patched tree>
```

`prepare.py` verifies the SHA-256 of every pinned archive (World, libgvps, libpyin, spline, libnpy, miniaudio, xxHash, Abseil)
and applies OpenUtau's own three patches before BLT's. Nothing here is wired into `packaging/build.ps1`.

## 7. Decisions needed from the owner

1. Own a rebuilt `worldline.dll` (proposal 1) and, optionally, review of the replacement spline.
2. Ship a patched OpenUtau.Core (proposal 2), and whether to keep `g2p-arpabet-plus`.
3. Hosting of the Qt/PySide6 source bundle and the written offer (section 3).
4. Option A or B for the Visual C++ runtime (section 4).
5. Who performs legal review, and which of the above they should see first.

Until each has documented evidence of resolution, `release-info.json` and `RELEASE-STATUS.txt` keep the NOT FOR RELEASE status.
