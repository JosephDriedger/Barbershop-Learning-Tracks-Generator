# Dependency and licence audit (M12a)

Status: **complete inventory, not a legal review. The package must not be released publicly while any
blocker below is open.** This replaces the working ledger written at M7b, which was based on the
NuGet cache of a spike build. This audit is based on the files that are actually in the Windows
package.

## What was audited, and how completeness is enforced

The audited artifact is the folder `BLT Music Generator\` produced by `packaging/build.ps1` (what the
installer installs):

* two PyInstaller executables, `BLT Music Generator.exe` (GUI) and `blt.exe` (CLI), with the
  Python 3.12 runtime, the standard-library extension modules, PySide6 / Qt, NumPy and BLT's own
  code;
* the self-contained win-x64 .NET 8 render host in `host\` (publish mode documented in
  `docs/m12-packaging.md`) with OpenUtau.Core, its managed dependencies and the native
  `worldline.dll`;
* generated `NOTICES.txt`, `LICENSE.txt` and `licenses\`.

`packaging/components.json` is the audit's data: each entry names the component, version, source,
licence, copyright holder, redistribution obligations, which package files it owns (glob patterns)
and which licence texts must accompany it. `packaging/inventory.py` classifies **every file** of the
built package into a component and **fails the build** when a file belongs to none, when an entry
lists files that are no longer present, or when an installed Python package or host NuGet package
differs from the audited version. Files of the .NET runtime are recognised by comparing their
SHA-256 with the runtime pack they were published from. So the audit cannot silently fall behind the
package: adding or upgrading a dependency forces an update here.

`packaging/notices.py bundle` produces the distributable `NOTICES.txt` and `licenses\` folder. Texts
are copied verbatim from the audited packages (site-packages, the NuGet cache, the pinned OpenUtau
checkout) or from the SPDX text in `packaging/licenses`; a text that cannot be found fails the
build. The tables below are generated from the same data (`python packaging/notices.py audit`; CI
runs it with `--check`).

Rules applied: a package being freely downloadable (PyPI, NuGet) is not permission to bundle it; an
obligation that cannot be verified is recorded as a **blocker**, not guessed; where a package
declares no licence, the upstream repository's licence was read and is cited as such.

## Decisions

* **FFmpeg is not bundled.** Its licence depends on the build (LGPL or GPL), no build has been
  audited, and no redistribution strategy exists. MP3 output needs a user-installed FFmpeg that
  BLT is pointed to (Preferences, `BLT_FFMPEG`, or `PATH`); WAV output needs nothing.
* **No voicebank is bundled**, now or ever, including ALYS. Users install their own.
* **PySide6 / Qt is used under the LGPL-3.0**, dynamically linked: the Qt and PySide6 libraries are
  loose DLL/PYD files in the one-folder layout so that they can be replaced. The written offer and
  attribution text are in `NOTICES.txt`. Whether that statement is sufficient is a blocker until a
  person confirms it.
* **NetMQ (LGPL-3.0), AsyncIO and NaCl are removed from the host** instead of complying with the
  LGPL for code BLT never runs. The host tests and `blt selftest` run against the pruned host.
* **onnxruntime.dll (MIT) is shipped** beside the host: the English phonemizers use a neural g2p model for words that are not in
  CMUdict. (M12 had removed it; that left the fallback depending on a Windows-supplied copy. Fixed in M14, proven by
  `blt-render-host --g2p-check`.) The supported renderer is still WORLDLINE-R; the neural renderers are not offered.
* **The Microsoft Visual C++ runtime is not shipped.** Setup requires Microsoft's own redistributable (detection, signed
  download or offline file); the build fails if any runtime file is in the package.
* **OpenUtau.Core is a patched build** of the pinned source (no Voicevox classes, Vogen data or non-English dictionaries);
  `host/verify-host.ps1` checks the result. **worldline.dll is BLT's own build** with its own spline instead of `tk::spline`.
* **The .NET runtime is bundled** (self-contained publish), so no .NET installation is needed on the
  user's machine.

## Blocker summary

Three blockers remain open after M14 (details and evidence: [m14-compliance-report.md](m14-compliance-report.md); the M13
investigation that proposed the changes is [m13-compliance.md](m13-compliance.md)):

| Blocker | State | What resolves it |
|---|---|---|
| `worldline.dll` | BLT builds it itself from the pinned sources with its own natural cubic spline; no `tk::spline` symbol (checked at build); byte-identical audio to the stock DLL. Provenance: [worldline-provenance.md](worldline-provenance.md) | An independent source/licensing review of the replacement, documented (owner requirement) |
| English "plus" dictionary (inside `OpenUtau.Core.dll`) | 120,887 of 420,422 entries have no stated source; only Arpasing+ and English CpV use it. Not approved for redistribution. [g2p-plus-provenance.md](g2p-plus-provenance.md) | Upstream answer on the additions, or replacing the pack with an empty/CMUdict-only one |
| PySide6 / Qt LGPL position | Corresponding-source bundle, written offer and relinking instructions are generated by `packaging/compliance.py`; replacement is tested on every build (`packaging/replaceability-test.ps1`). Not published | Attach the bundle to the GitHub release the installer is published with; a person reviews the arrangement |

Resolved in M14 with evidence: the patched `OpenUtau.Core.dll` (no Voicevox/LGPL code; `host/verify-host.ps1`; audio
identical to the stock build) and the Visual C++ runtime (not shipped; installer prerequisite, app pre-flight and a build check).

Resolved with evidence: BLT's own copyright holder (owner declaration, `Copyright 2026 Joseph Driedger`, single-author
git history); the Qt third-party attributions (qtbase's own `qt_attribution.json` for the exact tag); OpenBLAS and the GCC
runtime inside the NumPy wheel; the Universal C Runtime (no longer shipped); OpenUtau.Plugin.Builtin's per-file notices;
the F0 smoother, Deque and Merlin-derived sources; libpyin (BSD-3-Clause per source-file headers, corrected from M12);
CMUdict (notice added). Added in M13 because the binaries need them: the notices for World, libgvps, libpyin, libnpy,
miniaudio, xxHash and Abseil inside `worldline.dll`.

## Tables (generated)

<!-- BEGIN GENERATED: python packaging/notices.py audit -->

69 components are shipped in the package; **3 are release blockers** (unverified or conflicting licence obligations). A person must resolve each one before a public release; this table is regenerated from `packaging/components.json`.

### Release blockers

| Component | Version | Licence | What is unresolved |
|---|---|---|---|
| PySide6 and shiboken6 (Qt for Python bindings) | 6.11.2 | LGPL-3.0-only (elected from LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only) | LGPL-3.0: ship the LGPL and GPL texts (done); keep the libraries as separate replaceable DLLs/PYDs (done: one-folder layout, proven by packaging/replaceability-test.ps1 on every build); state that the application uses PySide6/Qt under the LGPL (done, NOTICES.txt); offer the corresponding source and any modifications (none made). Materials are prepared by packaging/compliance.py: the Qt Project's own qtbase and pyside-setup 6.11.2 source archives (SHA-256 recorded; qtbase MD5 matches Qt's published md5sums.txt), BLT's source at the release commit, a written offer, RELINKING.md. They are meant to be attached to the BLT GitHub release (BLT-Music-Generator-<version>-corresponding-source.zip); nothing is published yet. Blocker until (1) the corresponding-source zip is actually published with the release it accompanies and the NOTICES.txt link works, and (2) a person has reviewed the LGPL-3.0 arrangement (docs/m14-compliance-report.md). No Qt or PySide6 file is modified. |
| worldline.dll (OpenUtau's native resampler/vocoder, prebuilt win-x64) | BLT build of OpenUtau's worldline sources at 6958d68 with the pinned third-party sources; see docs/worldline-provenance.md | MIT (OpenUtau's worldline sources) with statically linked World (BSD-3-Clause, modified), PLATINUM (Morise, no licence text in file), libgvps and libpyin (BSD-3-Clause), libnpy (MIT), miniaudio (public domain or MIT-0), xxHash (BSD-2-Clause), Abseil strings (Apache-2.0), and BLT's own natural cubic spline (Apache-2.0) in place of the GPL tk::spline | tk::spline is no longer compiled in: host/native/build.ps1 builds the DLL from the pinned sources with host/native/effects-natural-spline.patch and fails unless the link map has no tk::spline symbol and the exports are those OpenUtau.Core calls; the replacement matches tk::spline to 1.6e-14 and renders byte-identical audio (tests/golden/selftest_audio.json). Permissive notices shipped (World, libgvps, libpyin, libnpy, miniaudio, xxHash, Abseil). Open: the owner requires an independent source/licensing review of the replacement before this is marked resolved (the author had read tk::spline's source; docs/worldline-provenance.md). BLOCKER stays open until that independent review is documented. PLATINUM files carry only 'Copyright 2012-2015 Masanori Morise. All Rights Reserved.' (extracted from World 0.1.4_3, BSD-3-Clause): residual, low. |
| English 'ARPAbet plus' dictionary and model (OpenUtau.Core g2p-arpabet-plus.zip, inside OpenUtau.Core.dll) | 0.1.565, added 2024-02 by cadlaxa (commit ba93f8b3), updated until 2024-06 | UNKNOWN for the additions; CMUdict-derived entries under the Carnegie Mellon licence | 420,422 entries: 299,535 are CMUdict words, 120,887 are additions whose source is not stated anywhere in the repository. Not approved for redistribution until the provenance is established (docs/g2p-plus-provenance.md). Explicit blocker by decision of the owner: do not remove blindly, do not approve redistribution yet. |

### Shipped components

| Component | Version | Licence | Copyright holder | Status |
|---|---|---|---|---|
| BLT Music Generator (application code, launchers, icon, generated notices) | 0.1.0 | Apache-2.0 | Copyright 2026 Joseph Driedger | ok |
| CPython runtime and standard library | 3.12.10 | PSF-2.0 | Python Software Foundation and contributors | ok |
| Third-party code inside CPython's extension modules (expat in pyexpat, libmpdec in _decimal, bzip2 in _bz2, liblzma in _lzma) | as built into Python 3.12.10 | MIT (expat) AND BSD-2-Clause (libmpdec) AND bzip2-1.0.6 AND public domain (liblzma) | expat: Expat maintainers, Thai Open Source Software Center, Clark Cooper; libmpdec: Stefan Krah; bzip2: Julian R Seward; liblzma: Lasse Collin and contributors | ok |
| libffi (libffi-8.dll, from the Python distribution) | bundled with Python 3.12.10 | MIT | Anthony Green, Red Hat and contributors | ok |
| OpenSSL libcrypto (libcrypto-3.dll, used by hashlib) | 3.x as bundled with Python 3.12.10 | Apache-2.0 | The OpenSSL Project Authors | ok |
| Microsoft Visual C++ runtime (VCRUNTIME140*.dll, MSVCP140*.dll): required of the user's PC, not shipped | 14.44.35211 or newer, installed by the user from Microsoft's redistributable | Microsoft Software License Terms of the Visual C++ Redistributable (accepted by the user at install) | Microsoft Corporation | ok |
| PyInstaller bootloader and runtime hooks (inside the two executables) | 6.22.3 | GPL-2.0-or-later WITH Bootloader-exception | PyInstaller Development Team (Hartmut Goebel, Giovanni Bajo, David Vierra, David Cortesi, Martin Zibricky) | ok |
| PySide6 and shiboken6 (Qt for Python bindings) | 6.11.2 | LGPL-3.0-only (elected from LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only) | The Qt Company Ltd. and the Qt for Python team | **blocker** |
| Qt libraries and plugins (Qt6Core, Qt6Gui, Qt6Widgets, platform and image plugins) | 6.11.2 | LGPL-3.0-only (with the third-party components listed in the Qt attribution index under their own licences) | The Qt Company Ltd. and others | ok |
| NumPy (numpy package) | 2.5.4 | BSD-3-Clause (with bundled sub-components: 0BSD, MIT, Zlib, CC0-1.0, Apache-2.0) | NumPy Developers | ok |
| OpenBLAS (numpy.libs/libscipy_openblas64_*.dll) and its runtime libraries | as bundled in the NumPy 2.5.4 wheel | BSD-3-Clause (OpenBLAS and the LAPACK it bundles); GPL-3.0-or-later WITH GCC-exception-3.1 (libgfortran runtime statically linked) | Copyright (c) 2011-2014 The OpenBLAS Project; LAPACK authors (see the NumPy licence file); Free Software Foundation (libgfortran) | ok |
| mido | 1.3.3 | MIT | Ole Martin Bjorndalen | ok |
| defusedxml | 0.7.1 | PSF-2.0 | Christian Heimes | ok |
| platformdirs | 4.12.3 | MIT | platformdirs contributors | ok |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause (BSD-2-Clause elected) | Donald Stufft and individual contributors | ok |
| typing_extensions | 4.16.0 | PSF-2.0 | Python Software Foundation and contributors | ok |
| OpenUtau.Core (OpenUtau.Core.dll) | 0.1.565 (commit a60ca5830b9064556157245d4bf8f5920d93e5f8), built by BLT with host/patch_openutau.py | MIT; embeds CMUdict 0.07 (Carnegie Mellon University licence) and the English 'plus' dictionary (see g2p-arpabet-plus); the Voicevox classes (LGPL-derived), the Vogen data and the non-English dictionaries are NOT in BLT's build | Copyright (c) 2014 StAkira and OpenUtau contributors; (c) 2023 oatsu (SimpleEnunu); (c) 2015 Stephen Cleary (Deque); (c) 2017 Ryuichi Yamamoto and the University of Edinburgh (Merlin-derived code in Plugin.Builtin); Carnegie Mellon University (CMUdict 0.07) | ok |
| OpenUtau.Plugin.Builtin (phonemizers) | 0.1.565 (same commit) | MIT | Copyright (c) 2014 StAkira and OpenUtau contributors | ok |
| worldline.dll (OpenUtau's native resampler/vocoder, prebuilt win-x64) | BLT build of OpenUtau's worldline sources at 6958d68 with the pinned third-party sources; see docs/worldline-provenance.md | MIT (OpenUtau's worldline sources) with statically linked World (BSD-3-Clause, modified), PLATINUM (Morise, no licence text in file), libgvps and libpyin (BSD-3-Clause), libnpy (MIT), miniaudio (public domain or MIT-0), xxHash (BSD-2-Clause), Abseil strings (Apache-2.0), and BLT's own natural cubic spline (Apache-2.0) in place of the GPL tk::spline | StAkira and OpenUtau contributors; Masanori Morise (World, PLATINUM); Kanru Hua (libgvps, libpyin); Leon Merten Lohse (libnpy); David Reid (miniaudio); Yann Collet (xxHash); The Abseil Authors; Tino Kluge (tk::spline); Copyright 2026 Joseph Driedger (the replacement spline) | **blocker** |
| .NET runtime and base class library (self-contained: coreclr, clrjit, hostfxr, hostpolicy, System.*.dll, msquic, ...) | 8.0.31 (Microsoft.NETCore.App.Runtime.win-x64) | MIT | .NET Foundation and Contributors; Microsoft Corporation | ok |
| BunLabs.NAudio.Flac (NuGet package) | 2.0.1 | MS-PL | Vivelin | ok |
| Concentus (NuGet package) | 2.2.1 | BSD-3-Clause (Xiph/Opus text shipped with the package) | Copyright (c) Xiph.Org Foundation, Skype Limited, CSIRO, Microsoft Corp.; Logan Stromberg | ok |
| Concentus.Oggfile (NuGet package) | 1.0.6 | MS-PL | Copyright (c) Logan Stromberg, Andrew Ward | ok |
| csharp-kana (NuGet package) | 1.0.2 | Apache-2.0 | wolfgitpr | ok |
| csharp-pinyin (NuGet package) | 1.0.0 | Apache-2.0 | wolfgitpr | ok |
| Ignore (NuGet package) | 0.1.50 | MIT (repository licence; the package declares none) | Copyright (c) 2020 Hardik Goel | ok |
| K4os.Hash.xxHash (NuGet package) | 1.0.8 | MIT (repository licence; the package gives a URL) | Copyright (c) 2017 Milosz Krajewski | ok |
| Melanchall.DryWetMidi (NuGet package) | 7.2.0 | MIT | Copyright © Melanchall 2024 | ok |
| Microsoft.Bcl.AsyncInterfaces (NuGet package) | 5.0.0 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| Microsoft.Extensions.ObjectPool (NuGet package) | 5.0.10 | Apache-2.0 | © Microsoft Corporation. All rights reserved. | ok |
| Microsoft.ML.OnnxRuntime.Managed (NuGet package) | 1.16.3 | MIT | Copyright (c) Microsoft Corporation | ok |
| Microsoft.Win32.SystemEvents (NuGet package) | 5.0.0 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| NAudio (NuGet package) | 2.2.1 | MIT | Copyright (c) Mark Heath 2023 | ok |
| NAudio.Asio (NuGet package) | 2.2.1 | MIT | © Mark Heath 2023 | ok |
| NAudio.Core (NuGet package) | 2.2.1 | MIT | © Mark Heath 2023 | ok |
| NAudio.Midi (NuGet package) | 2.2.1 | MIT | © Mark Heath 2023 | ok |
| NAudio.Vorbis (NuGet package) | 1.5.0 | MIT | Copyright © Andrew Ward 2021 | ok |
| NAudio.Wasapi (NuGet package) | 2.2.1 | MIT | © Mark Heath 2023 | ok |
| NAudio.WinMM (NuGet package) | 2.2.1 | MIT | © Mark Heath 2023 | ok |
| Newtonsoft.Json (NuGet package) | 13.0.3 | MIT | Copyright © James Newton-King 2008 | ok |
| NLayer (NuGet package) | 1.15.0 | MIT | Mark Heath, Andrew Ward | ok |
| NLayer.NAudioSupport (NuGet package) | 1.4.0 | MIT | Mark Heath | ok |
| NumSharp (NuGet package) | 0.30.0 | Apache-2.0 | Copyright (c) 2021 SciSharp STACK Team | ok |
| NVorbis (NuGet package) | 0.10.4 | MIT | Copyright (c) Andrew Ward 2021 | ok |
| NWaves (NuGet package) | 0.9.6 | MIT | ar1st0crat | ok |
| Serilog (NuGet package) | 4.1.0 | Apache-2.0 | Copyright © Serilog Contributors | ok |
| SharpCompress (NuGet package) | 0.38.0 | MIT | Copyright (c) 2014  Adam Hathcock | ok |
| SharpGen.Runtime (NuGet package) | 2.0.0-beta.13 | MIT | (c) 2010-2017 Alexandre Mutel, 2017-2018 Jeremy Koritzinsky | ok |
| SharpGen.Runtime.COM (NuGet package) | 2.0.0-beta.13 | MIT | (c) 2010-2017 Alexandre Mutel, 2017-2018 Jeremy Koritzinsky | ok |
| System.Drawing.Common (NuGet package) | 5.0.0 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| System.IO.Packaging (NuGet package) | 9.0.2 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| System.IO.Pipelines (NuGet package) | 9.0.2 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| System.Private.ServiceModel (NuGet package) | 4.9.0 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| System.Security.Cryptography.Pkcs (NuGet package) | 5.0.0 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| System.Security.Cryptography.Xml (NuGet package) | 5.0.0 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| System.Security.Permissions (NuGet package) | 5.0.0 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| System.ServiceModel.Primitives (NuGet package) | 4.9.0 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| System.Text.Encodings.Web (NuGet package) | 9.0.2 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| System.Text.Json (NuGet package) | 9.0.2 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| System.Windows.Extensions (NuGet package) | 5.0.0 | MIT | © Microsoft Corporation. All rights reserved. | ok |
| UTF.Unknown (NuGet package) | 2.5.1 | MPL-1.1 (elected from MPL-1.1 / GPL-2.0+ / LGPL-2.1+) | Julian Verdurmen, Rustam Zinnatullin and contributors (derived from Mozilla's universalchardet) | ok |
| Vortice.DirectX (NuGet package) | 2.4.2 | MIT | Copyright © Amer Koleci and Contributors | ok |
| Vortice.DXGI (NuGet package) | 2.4.2 | MIT | Copyright © Amer Koleci and Contributors | ok |
| Vortice.Mathematics (NuGet package) | 1.4.25 | MIT | Copyright © Amer Koleci and Contributors | ok |
| WanaKana-net (NuGet package) | 1.0.0 | MIT | Copyright Martin Zikmund 2020 | ok |
| YamlDotNet (NuGet package) | 15.1.2 | MIT | Copyright (c) 2008-2014 Antoine Aubry and contributors | ok |
| ZstdSharp.Port (NuGet package) | 0.8.1 | MIT | Copyright Oleg Stepanischev 2024 | ok |
| English 'ARPAbet plus' dictionary and model (OpenUtau.Core g2p-arpabet-plus.zip, inside OpenUtau.Core.dll) | 0.1.565, added 2024-02 by cadlaxa (commit ba93f8b3), updated until 2024-06 | UNKNOWN for the additions; CMUdict-derived entries under the Carnegie Mellon licence | Carnegie Mellon University (CMUdict entries); the contributor and unknown others (additions) | **blocker** |
| ONNX Runtime native library (onnxruntime.dll, DirectML build; Microsoft.ML.OnnxRuntime.DirectML NuGet package) | 1.16.3 | MIT | Copyright (c) Microsoft Corporation | ok |

### Obligations and sources

| Component | Source | Obligations / notes |
|---|---|---|
| BLT Music Generator (application code, launchers, icon, generated notices) | this repository | Keep LICENSE (Apache-2.0, copyright line filled in) and NOTICE in the package; retain third-party attribution (NOTICES.txt). Evidence: the owner's written declaration (M13 instruction, 2026-10-12) that Joseph Driedger owns the original code and chooses Apache-2.0; git history has a single author (Joseph Driedger, 108 commits plus one GitHub web commit) and the repository holds no third-party source files. Original artwork only (the icon is drawn by packaging/make_icon.py); no third-party fonts or images. Frozen Python sources are inside the two executables. Rests on the owner's declaration; a lawyer may still want to review the ownership of AI-assisted code. |
| CPython runtime and standard library | https://www.python.org/downloads/release/python-31210/ (the interpreter that builds the package) | Include the Python licence text and copyright notices. |
| Third-party code inside CPython's extension modules (expat in pyexpat, libmpdec in _decimal, bzip2 in _bz2, liblzma in _lzma) | CPython 3.12.10 Windows build (see 'Licenses and Acknowledgements for Incorporated Software' in the Python documentation) | Reproduce the expat, libmpdec and bzip2 notices (shipped). Version of each embedded library not individually read; the licences are those of every release of these libraries. |
| libffi (libffi-8.dll, from the Python distribution) | https://github.com/libffi/libffi | Reproduce the MIT notice. The exact libffi version inside the Python build was not read; the licence is MIT for all releases. |
| OpenSSL libcrypto (libcrypto-3.dll, used by hashlib) | https://www.openssl.org/ | Reproduce the Apache-2.0 text (OpenSSL 3.x is Apache-2.0). libssl and the _ssl module are excluded from the package; BLT makes no network connections. |
| Microsoft Visual C++ runtime (VCRUNTIME140*.dll, MSVCP140*.dll): required of the user's PC, not shipped | Python 3.12.10 installation; PySide6 and NumPy wheels | BLT redistributes none of Microsoft's runtime files (Microsoft limits redistribution to licensed Visual Studio users). Setup requires Microsoft's own Visual C++ Redistributable (x64), downloaded by the user from Microsoft or supplied by the user for offline installs, and verifies its Microsoft signature before running it. The program checks again before rendering. The one file NumPy imports under a hash-renamed name (msvcp140-<hash>.dll) is created at install time as a copy of the PC's own msvcp140.dll: a copy of a file the user already has, not a redistribution. Enforced by build: packaging/runtime_copies.py fails the build if any Visual C++ runtime file is in the package, and inventory.py fails on unowned files. The installer's prerequisite flow is tested silently (missing runtime stops Setup, nothing installed); its dialogs have not been exercised on a PC that really lacks the runtime (clean-machine gate). |
| PyInstaller bootloader and runtime hooks (inside the two executables) | https://pyinstaller.org/ | The bootloader exception allows distributing the frozen program under any licence; ship PyInstaller's COPYING.txt. |
| PySide6 and shiboken6 (Qt for Python bindings) | https://code.qt.io/cgit/pyside/pyside-setup.git (tag v6.11.2); wheels from PyPI | LGPL-3.0: ship the LGPL and GPL texts (done); keep the libraries as separate replaceable DLLs/PYDs (done: one-folder layout, proven by packaging/replaceability-test.ps1 on every build); state that the application uses PySide6/Qt under the LGPL (done, NOTICES.txt); offer the corresponding source and any modifications (none made). Materials are prepared by packaging/compliance.py: the Qt Project's own qtbase and pyside-setup 6.11.2 source archives (SHA-256 recorded; qtbase MD5 matches Qt's published md5sums.txt), BLT's source at the release commit, a written offer, RELINKING.md. They are meant to be attached to the BLT GitHub release (BLT-Music-Generator-<version>-corresponding-source.zip); nothing is published yet. Blocker until (1) the corresponding-source zip is actually published with the release it accompanies and the NOTICES.txt link works, and (2) a person has reviewed the LGPL-3.0 arrangement (docs/m14-compliance-report.md). No Qt or PySide6 file is modified. |
| Qt libraries and plugins (Qt6Core, Qt6Gui, Qt6Widgets, platform and image plugins) | https://download.qt.io/official_releases/qt/6.11/6.11.2/ | LGPL-3.0 as for PySide6 (statement in NOTICES.txt). Qt's third-party attributions are reproduced: the verbatim qt_attribution.json files and licence texts of qtbase at tag v6.11.2 for every bundled component that can be part of Qt6Core, Qt6Gui, Qt6Widgets and the windows/offscreen/ico plugins (PCRE2, FreeType, HarfBuzz, libpng, zlib, TinyCBOR, double-conversion, the Unicode data and more). A deliberate superset (it includes entries for code that may not be compiled into the Windows binaries), produced by packaging/qt_attribution.py. A string search of the shipped DLLs confirmed that PCRE2, FreeType, HarfBuzz, libpng, zlib, TinyCBOR and the Unicode tables are in them. The LGPL statement itself is tracked under 'pyside6'. |
| NumPy (numpy package) | https://numpy.org/ (PyPI wheel) | Reproduce the NumPy licence and the licences of its bundled sub-components (shipped from the wheel's dist-info). |
| OpenBLAS (numpy.libs/libscipy_openblas64_*.dll) and its runtime libraries | NumPy wheel (scipy-openblas64) | Reproduce the notices: NumPy's licence file for this wheel names exactly this DLL (numpy.libs\libscipy_openblas*.dll) for OpenBLAS, LAPACK and the GCC runtime library (GCC Runtime Library Exception 3.1) and is shipped verbatim (licenses	hird-party umpy\LICENSE.txt), together with the GPL-3.0 text. Relies on the NumPy project's published licence inventory for its wheel; it was not re-derived from the binary. |
| mido | https://github.com/mido/mido | Reproduce the copyright notice and licence text (shipped). |
| defusedxml | https://github.com/tiran/defusedxml | Reproduce the copyright notice and licence text (shipped). |
| platformdirs | https://github.com/tox-dev/platformdirs | Reproduce the copyright notice and licence text (shipped). |
| packaging | https://github.com/pypa/packaging | Reproduce the copyright notice and licence text (shipped). |
| typing_extensions | https://github.com/python/typing_extensions | Reproduce the copyright notice and licence text (shipped). |
| OpenUtau.Core (OpenUtau.Core.dll) | https://github.com/stakira/OpenUtau (tag 0.1.565, commit a60ca58...; built from a copy modified by host/patch_openutau.py) | MIT notice and the upstream MIT/Apache notices of the ported code (shipped); CMUdict licence text (shipped). BLT's host is a MODIFIED build of OpenUtau.Core: host/patch_openutau.py deletes the Voicevox classes and blanks the Vogen data and the non-English dictionaries; the reported revision is 'a60ca58...+blt-patched'. host/verify-host.ps1 (run by every package build) reads the built assemblies and fails unless there is no Voicevox type, the English dictionaries are byte-identical to the pinned source, and the other dictionaries and Vogen data are empty. No LGPL obligation remains for this DLL. Resolved by evidence: the patched build renders byte-identical audio to the stock build (tests/golden/selftest_audio.json), 44 of 46 host-driven tests passed at prototype stage and all pass now. Supported functionality kept: the WORLDLINE-R renderer, the default and English phonemizers. Removed on purpose: Voicevox, Vogen, and phonemizers needing a non-English dictionary. The English 'plus' dictionary is tracked separately. |
| OpenUtau.Plugin.Builtin (phonemizers) | https://github.com/stakira/OpenUtau | MIT notice (shipped). The sources were searched for licence, copyright and derived-from statements. Found: EnunuOnnx/Merlin.cs is adapted from nnmnkwii (MIT), itself from Merlin (Apache-2.0) - both notices shipped under 'openutau-core'; GermanDiphonePhonemizer is based on the German CMUSphinx dictionary (named in the source; the dictionary is not embedded as a file); several phonemizers say they are 'based on' another phonemizer or reclist from the same community (no licence terms stated). The Data\*.template.yaml files are contributor-authored within the MIT repository. Residual risk: the in-repository authorship statements are not independently verified. |
| worldline.dll (OpenUtau's native resampler/vocoder, prebuilt win-x64) | https://github.com/stakira/OpenUtau/tree/0.1.565/cpp | tk::spline is no longer compiled in: host/native/build.ps1 builds the DLL from the pinned sources with host/native/effects-natural-spline.patch and fails unless the link map has no tk::spline symbol and the exports are those OpenUtau.Core calls; the replacement matches tk::spline to 1.6e-14 and renders byte-identical audio (tests/golden/selftest_audio.json). Permissive notices shipped (World, libgvps, libpyin, libnpy, miniaudio, xxHash, Abseil). Open: the owner requires an independent source/licensing review of the replacement before this is marked resolved (the author had read tk::spline's source; docs/worldline-provenance.md). BLOCKER stays open until that independent review is documented. PLATINUM files carry only 'Copyright 2012-2015 Masanori Morise. All Rights Reserved.' (extracted from World 0.1.4_3, BSD-3-Clause): residual, low. |
| .NET runtime and base class library (self-contained: coreclr, clrjit, hostfxr, hostpolicy, System.*.dll, msquic, ...) | https://dotnet.microsoft.com/ (the runtime pack restored by dotnet publish) | Ship the runtime's LICENSE.TXT and THIRD-PARTY-NOTICES.TXT (done, copied verbatim from the runtime pack). |
| BunLabs.NAudio.Flac (NuGet package) | https://www.nuget.org/packages/BunLabs.NAudio.Flac/2.0.1 | Reproduce the copyright notice and licence text (shipped). |
| Concentus (NuGet package) | https://www.nuget.org/packages/Concentus/2.2.1 | Reproduce the copyright notice and licence text (shipped). |
| Concentus.Oggfile (NuGet package) | https://www.nuget.org/packages/Concentus.Oggfile/1.0.6 | Reproduce the copyright notice and licence text (shipped). |
| csharp-kana (NuGet package) | https://www.nuget.org/packages/csharp-kana/1.0.2 | Reproduce the copyright notice and licence text (shipped). |
| csharp-pinyin (NuGet package) | https://www.nuget.org/packages/csharp-pinyin/1.0.0 | Reproduce the copyright notice and licence text (shipped). |
| Ignore (NuGet package) | https://www.nuget.org/packages/Ignore/0.1.50 | Reproduce the copyright notice and licence text (shipped). |
| K4os.Hash.xxHash (NuGet package) | https://www.nuget.org/packages/K4os.Hash.xxHash/1.0.8 | Reproduce the copyright notice and licence text (shipped). |
| Melanchall.DryWetMidi (NuGet package) | https://www.nuget.org/packages/Melanchall.DryWetMidi/7.2.0 | Reproduce the copyright notice and licence text (shipped). |
| Microsoft.Bcl.AsyncInterfaces (NuGet package) | https://www.nuget.org/packages/Microsoft.Bcl.AsyncInterfaces/5.0.0 | Reproduce the copyright notice and licence text (shipped). |
| Microsoft.Extensions.ObjectPool (NuGet package) | https://www.nuget.org/packages/Microsoft.Extensions.ObjectPool/5.0.10 | Reproduce the copyright notice and licence text (shipped). |
| Microsoft.ML.OnnxRuntime.Managed (NuGet package) | https://www.nuget.org/packages/Microsoft.ML.OnnxRuntime.Managed/1.16.3 | Reproduce the copyright notice and licence text (shipped). The managed wrapper; the native onnxruntime.dll that it loads ships separately (component onnxruntime-native). |
| Microsoft.Win32.SystemEvents (NuGet package) | https://www.nuget.org/packages/Microsoft.Win32.SystemEvents/5.0.0 | Reproduce the copyright notice and licence text (shipped). |
| NAudio (NuGet package) | https://www.nuget.org/packages/NAudio/2.2.1 | Reproduce the copyright notice and licence text (shipped). |
| NAudio.Asio (NuGet package) | https://www.nuget.org/packages/NAudio.Asio/2.2.1 | Reproduce the copyright notice and licence text (shipped). |
| NAudio.Core (NuGet package) | https://www.nuget.org/packages/NAudio.Core/2.2.1 | Reproduce the copyright notice and licence text (shipped). |
| NAudio.Midi (NuGet package) | https://www.nuget.org/packages/NAudio.Midi/2.2.1 | Reproduce the copyright notice and licence text (shipped). |
| NAudio.Vorbis (NuGet package) | https://www.nuget.org/packages/NAudio.Vorbis/1.5.0 | Reproduce the copyright notice and licence text (shipped). |
| NAudio.Wasapi (NuGet package) | https://www.nuget.org/packages/NAudio.Wasapi/2.2.1 | Reproduce the copyright notice and licence text (shipped). |
| NAudio.WinMM (NuGet package) | https://www.nuget.org/packages/NAudio.WinMM/2.2.1 | Reproduce the copyright notice and licence text (shipped). |
| Newtonsoft.Json (NuGet package) | https://www.nuget.org/packages/Newtonsoft.Json/13.0.3 | Reproduce the copyright notice and licence text (shipped). |
| NLayer (NuGet package) | https://www.nuget.org/packages/NLayer/1.15.0 | Reproduce the copyright notice and licence text (shipped). |
| NLayer.NAudioSupport (NuGet package) | https://www.nuget.org/packages/NLayer.NAudioSupport/1.4.0 | Reproduce the copyright notice and licence text (shipped). |
| NumSharp (NuGet package) | https://www.nuget.org/packages/NumSharp/0.30.0 | Reproduce the copyright notice and licence text (shipped). |
| NVorbis (NuGet package) | https://www.nuget.org/packages/NVorbis/0.10.4 | Reproduce the copyright notice and licence text (shipped). |
| NWaves (NuGet package) | https://www.nuget.org/packages/NWaves/0.9.6 | Reproduce the copyright notice and licence text (shipped). |
| Serilog (NuGet package) | https://www.nuget.org/packages/Serilog/4.1.0 | Reproduce the copyright notice and licence text (shipped). |
| SharpCompress (NuGet package) | https://www.nuget.org/packages/SharpCompress/0.38.0 | Reproduce the copyright notice and licence text (shipped). |
| SharpGen.Runtime (NuGet package) | https://www.nuget.org/packages/SharpGen.Runtime/2.0.0-beta.13 | Reproduce the copyright notice and licence text (shipped). |
| SharpGen.Runtime.COM (NuGet package) | https://www.nuget.org/packages/SharpGen.Runtime.COM/2.0.0-beta.13 | Reproduce the copyright notice and licence text (shipped). |
| System.Drawing.Common (NuGet package) | https://www.nuget.org/packages/System.Drawing.Common/5.0.0 | Reproduce the copyright notice and licence text (shipped). |
| System.IO.Packaging (NuGet package) | https://www.nuget.org/packages/System.IO.Packaging/9.0.2 | Reproduce the copyright notice and licence text (shipped). |
| System.IO.Pipelines (NuGet package) | https://www.nuget.org/packages/System.IO.Pipelines/9.0.2 | Reproduce the copyright notice and licence text (shipped). |
| System.Private.ServiceModel (NuGet package) | https://www.nuget.org/packages/System.Private.ServiceModel/4.9.0 | Reproduce the copyright notice and licence text (shipped). |
| System.Security.Cryptography.Pkcs (NuGet package) | https://www.nuget.org/packages/System.Security.Cryptography.Pkcs/5.0.0 | Reproduce the copyright notice and licence text (shipped). |
| System.Security.Cryptography.Xml (NuGet package) | https://www.nuget.org/packages/System.Security.Cryptography.Xml/5.0.0 | Reproduce the copyright notice and licence text (shipped). |
| System.Security.Permissions (NuGet package) | https://www.nuget.org/packages/System.Security.Permissions/5.0.0 | Reproduce the copyright notice and licence text (shipped). |
| System.ServiceModel.Primitives (NuGet package) | https://www.nuget.org/packages/System.ServiceModel.Primitives/4.9.0 | Reproduce the copyright notice and licence text (shipped). |
| System.Text.Encodings.Web (NuGet package) | https://www.nuget.org/packages/System.Text.Encodings.Web/9.0.2 | Reproduce the copyright notice and licence text (shipped). |
| System.Text.Json (NuGet package) | https://www.nuget.org/packages/System.Text.Json/9.0.2 | Reproduce the copyright notice and licence text (shipped). |
| System.Windows.Extensions (NuGet package) | https://www.nuget.org/packages/System.Windows.Extensions/5.0.0 | Reproduce the copyright notice and licence text (shipped). |
| UTF.Unknown (NuGet package) | https://www.nuget.org/packages/UTF.Unknown/2.5.1 | Reproduce the copyright notice and licence text (shipped). MPL-1.1: keep the notice; file-level copyleft applies only to modified UTF.Unknown files (none made). |
| Vortice.DirectX (NuGet package) | https://www.nuget.org/packages/Vortice.DirectX/2.4.2 | Reproduce the copyright notice and licence text (shipped). |
| Vortice.DXGI (NuGet package) | https://www.nuget.org/packages/Vortice.DXGI/2.4.2 | Reproduce the copyright notice and licence text (shipped). |
| Vortice.Mathematics (NuGet package) | https://www.nuget.org/packages/Vortice.Mathematics/1.4.25 | Reproduce the copyright notice and licence text (shipped). |
| WanaKana-net (NuGet package) | https://www.nuget.org/packages/WanaKana-net/1.0.0 | Reproduce the copyright notice and licence text (shipped). |
| YamlDotNet (NuGet package) | https://www.nuget.org/packages/YamlDotNet/15.1.2 | Reproduce the copyright notice and licence text (shipped). |
| ZstdSharp.Port (NuGet package) | https://www.nuget.org/packages/ZstdSharp.Port/0.8.1 | Reproduce the copyright notice and licence text (shipped). |
| English 'ARPAbet plus' dictionary and model (OpenUtau.Core g2p-arpabet-plus.zip, inside OpenUtau.Core.dll) | https://github.com/stakira/OpenUtau (OpenUtau.Core/G2p/Data/g2p-arpabet-plus.zip) | 420,422 entries: 299,535 are CMUdict words, 120,887 are additions whose source is not stated anywhere in the repository. Not approved for redistribution until the provenance is established (docs/g2p-plus-provenance.md). Explicit blocker by decision of the owner: do not remove blindly, do not approve redistribution yet. |
| ONNX Runtime native library (onnxruntime.dll, DirectML build; Microsoft.ML.OnnxRuntime.DirectML NuGet package) | https://www.nuget.org/packages/Microsoft.ML.OnnxRuntime.DirectML/1.16.3 | MIT licence and the package's ThirdPartyNotices.txt (shipped verbatim: it lists the libraries inside onnxruntime.dll). Needed because the English phonemizers fall back to a neural g2p model for words that are not in CMUdict. M12 had pruned it as 'neural renderer only', which left that fallback depending on a Windows-supplied onnxruntime that does not exist on Windows 10; restored in M14 and proven by 'blt-render-host --g2p-check'. DirectML.dll is not shipped (the DirectML provider is never used). |

### Deliberately not shipped

| Item | Licence | Why | How it is excluded |
|---|---|---|---|
| NetMQ 4.0.1.13 (NetMQ.dll) | LGPL-3.0 (COPYING.LESSER in its repository) | OpenUtau's DAW-bridge messaging; unused by the headless host. The LGPL replaceability duties are avoided by not shipping it. | host/prune.txt; the host and backend tests and `blt selftest` pass without it. |
| AsyncIO 0.1.69 (AsyncIO.dll) | unspecified in the package | Transitive dependency of NetMQ. | host/prune.txt |
| NaCl.Net 0.1.13 (NaCl.dll) | MPL-2.0 | Transitive dependency of NetMQ. | host/prune.txt |
| ONNX Runtime import library (onnxruntime.lib) and DirectML.dll | MIT / Microsoft DirectML terms (not analysed) | Not needed to run: onnxruntime.dll itself is shipped (the English g2p fallback uses it); DirectML is never used. | host/prune.txt (the .lib); DirectML.dll is not part of the published host. |
| DirectML (Microsoft.AI.DirectML) | Microsoft proprietary terms (not analysed) | Not part of the published host output at all (checked against the file list). | not present |
| DryWetMidi natives for other platforms (Native32.dll, Native64.dylib) | MIT | Wrong platform. | host/prune.txt |
| createdump.exe | MIT (.NET) | Crash-dump tool, not needed to run. | host/prune.txt |
| Debug symbols (*.pdb) | n/a | Not needed to run. | dotnet publish -p:DebugType=none |
| libssl and the _ssl module of Python | Apache-2.0 (OpenSSL 3) | BLT never opens network connections. | excluded in packaging/blt.spec |
| Qt modules, plugins and translations other than Core/Gui/Widgets, qwindows, qoffscreen, qico | LGPL-3.0 / GPL-3.0 / commercial per module | Unused; keeps GPL-only and commercial-only Qt modules out. | DROP_PATTERNS in packaging/blt.spec |
| Universal C Runtime (ucrtbase.dll, api-ms-win-*.dll) | Microsoft Distributable Code | An operating-system component of Windows 10 and later, which the installer requires; PyInstaller copies it from the build machine only for Windows 7/8. | filtered out in packaging/blt.spec; the installer sets MinVersion=10.0 |

### External, user-supplied or build-time

| Item | Licence | Decision | Reason |
|---|---|---|---|
| FFmpeg | LGPL-2.1+ or GPL-2+ depending on the build | NOT bundled. MP3 output uses an ffmpeg the user installs and points BLT at (Preferences, BLT_FFMPEG or PATH). WAV output needs nothing. | The licence depends on the build chosen; there is no audited build and redistribution strategy to approve. |
| Voicebanks (ALYS DB002 FRA and every other) | per voicebank | NOT bundled, never copied into the repository or the installer. Users install their own. | Not authorised for redistribution. |
| .NET SDK, Visual Studio, Inno Setup, PyInstaller (as tools) | various | Build-time only; not needed on the user's machine (the .NET runtime itself is bundled, self-contained). | The Inno Setup stub inside Setup.exe is listed under 'installer'. |

### Inside the installer only

- **Inno Setup (compiled setup stub embedded in the installer)**: Inno Setup License (permissive; keep the copyright notice). Copyright (C) 1997-2026 Jordan Russell; portions Copyright (C) 2000-2026 Martijn Laan. The stub is embedded unmodified, which keeps its notices; the licence text is reproduced in NOTICES.txt.

<!-- END GENERATED -->
