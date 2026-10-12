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
* **onnxruntime is removed**, which also removes the neural renderers; the supported renderers are
  CLASSIC and WORLDLINE-R.
* **The .NET runtime is bundled** (self-contained publish), so no .NET installation is needed on the
  user's machine.

## Blocker summary

Five blockers remain open (the tables below list every component's status):

| Blocker | Why it blocks | What resolves it |
|---|---|---|
| `worldline.dll` | It compiles GPL-2.0 code (tk::spline) and code without a licence (libpyin) | Written permission/clarification from upstream, a rebuild without those parts, or distribution under GPL-2.0 terms |
| `OpenUtau.Core.dll` | (1) Its Voicevox classes are "partially based on" the LGPL-3.0 VOICEVOX engine: the LGPL handling needs a person's confirmation. (2) Embedded g2p and Vogen data (and `yue.csv`) have no licence statement and unnamed training data | Confirm the LGPL statement; ask the OpenUtau maintainers about the data, or build a BLT-specific OpenUtau.Core without those features (no longer the unmodified upstream binary) |
| PySide6 / Qt LGPL statement | The compliance text in `NOTICES.txt` is drafted, not reviewed | Human review (or a commercial Qt licence) |
| Visual C++ runtime files (`VCRUNTIME140*.dll`, `MSVCP140*.dll`) | Redistribution terms of these app-local copies not reviewed | Review Microsoft's Distributable Code terms, or have the installer run Microsoft's redistributable instead |
| BLT's own copyright holder | `LICENSE` is the unfilled Apache-2.0 template | The owner names the holder and confirms the licence |

Resolved during this audit, with evidence: the Qt third-party attributions (collected from qtbase's own
`qt_attribution.json` files for the exact tag, `packaging/qt_attribution.py`); OpenBLAS and the GCC runtime inside the
NumPy wheel (named, with their texts, in the wheel's own licence file); the Universal C Runtime (an operating-system
component, no longer shipped); OpenUtau.Plugin.Builtin's per-file notices (searched; the derived-from statements found
are covered by the added Merlin / nnmnkwii attributions); the F0 smoother and Deque sources (MIT, upstream texts
shipped).

## Tables (generated)

<!-- BEGIN GENERATED: python packaging/notices.py audit -->

67 components are shipped in the package; **5 are release blockers** (unverified or conflicting licence obligations). A person must resolve each one before a public release; this table is regenerated from `packaging/components.json`.

### Release blockers

| Component | Version | Licence | What is unresolved |
|---|---|---|---|
| BLT Music Generator (application code, launchers, icon, generated notices) | 0.1.0 | Apache-2.0 | Name the copyright holder in LICENSE and confirm Apache-2.0 for the release. Original artwork only (the icon is drawn by packaging/make_icon.py); no third-party fonts or images are shipped. The Python sources are frozen inside the two executables. |
| Microsoft Visual C++ runtime (VCRUNTIME140*.dll, MSVCP140*.dll) | 14.x as shipped in Python 3.12.10 and the Qt/NumPy wheels | Microsoft Visual C++ redistributable terms (Distributable Code) | Microsoft permits redistributing the Visual C++ runtime files under its Distributable Code terms; the exact terms that apply to these copies were not reviewed or reproduced. Needs a human decision: confirm the terms, or have the installer run Microsoft's official Visual C++ Redistributable instead of carrying app-local copies. |
| PySide6 and shiboken6 (Qt for Python bindings) | 6.11.2 | LGPL-3.0-only (elected from LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only) | LGPL-3.0: ship the LGPL and GPL texts (done); keep the libraries as separate replaceable DLLs/PYDs (done: one-folder layout); state that the application uses PySide6/Qt under the LGPL; offer the corresponding source and any modifications (none made). A source offer is drafted in NOTICES.txt but has not been reviewed by a person. Blocker until a person confirms the LGPL-3.0 compliance statement. If commercial licensing is preferred instead, this entry changes. |
| OpenUtau.Core (OpenUtau.Core.dll) | 0.1.565 (commit a60ca5830b9064556157245d4bf8f5920d93e5f8) | MIT; contains code partially based on the VOICEVOX engine (LGPL-3.0), a C# port of SimpleEnunu's f0_smoother (MIT) and a Deque implementation matching Nito.Collections.Deque (MIT); embeds data of unverified provenance | MIT notice and the upstream MIT/Apache notices of the ported code (shipped). LGPL-3.0: OpenUtau.Core.Voicevox (VoicevoxRenderer, VoicevoxUtils, VoicevoxConfig) states it is 'partially based on the VOICEVOX engine' (LGPL_LICENSE), so OpenUtau.Core.dll is distributed with the LGPL text (shipped), as a separate replaceable DLL, built unmodified from the public commit named above; the written statement is in NOTICES.txt. Embedded data: the g2p models (arpabet, arpabet-plus, de, es, fr, it, ja-mono, ko, pt, ru) were contributed to the MIT repository by named contributors (e.g. commits 22e0c887, 2d0fcbe7, 8b8104ae, ed3267b9), the Vogen models and yue.csv by the maintainer in 2022 (e6486acc, 5b698e5b); none carries a licence statement, and the training data or dictionaries they derive from (for example CMUdict for the English model) are not named. The CREPE tiny.onnx model is MIT (Jong Wook Kim; licence shipped). Release blocker until a person (1) confirms the LGPL handling of the VOICEVOX-derived classes and (2) the owner of the embedded g2p/Vogen data is asked to confirm it may be redistributed, or those features are removed from a BLT-specific build of OpenUtau.Core (which would no longer be the unmodified upstream binary). |
| worldline.dll (OpenUtau's native resampler/vocoder, prebuilt win-x64) | from OpenUtau 0.1.565 (runtimes/win-x64/native/worldline.dll) | MIT (OpenUtau's own sources) combined with GPL-2.0 (tk::spline) and unlicensed (libpyin) code | worldline compiles third-party code: the header-only tk::spline (ttk592/spline) is GPL-2.0 and is included by worldline's effects code; libpyin (Sleepwalking/libpyin) has no licence file in its repository; libgvps is BSD-3-Clause; WORLD is modified BSD; libnpy and miniaudio are permissive. A binary containing GPL-2.0 code may be distributed only under GPL-2.0 terms (source for the whole work, no further restrictions), which does not fit an Apache-2.0/MIT bundle without that source offer; a library with no licence grants no right to redistribute. RELEASE BLOCKER (conflict). Options: obtain written permission or clarification from upstream; rebuild worldline without spline and libpyin; or distribute under GPL-2.0 compliance. The installer can still be built for internal acceptance testing, flagged as not for release. |

### Shipped components

| Component | Version | Licence | Copyright holder | Status |
|---|---|---|---|---|
| BLT Music Generator (application code, launchers, icon, generated notices) | 0.1.0 | Apache-2.0 | UNKNOWN: the repository LICENSE is the unfilled Apache-2.0 template | **blocker** |
| CPython runtime and standard library | 3.12.10 | PSF-2.0 | Python Software Foundation and contributors | ok |
| Third-party code inside CPython's extension modules (expat in pyexpat, libmpdec in _decimal, bzip2 in _bz2, liblzma in _lzma) | as built into Python 3.12.10 | MIT (expat) AND BSD-2-Clause (libmpdec) AND bzip2-1.0.6 AND public domain (liblzma) | expat: Expat maintainers, Thai Open Source Software Center, Clark Cooper; libmpdec: Stefan Krah; bzip2: Julian R Seward; liblzma: Lasse Collin and contributors | ok |
| libffi (libffi-8.dll, from the Python distribution) | bundled with Python 3.12.10 | MIT | Anthony Green, Red Hat and contributors | ok |
| OpenSSL libcrypto (libcrypto-3.dll, used by hashlib) | 3.x as bundled with Python 3.12.10 | Apache-2.0 | The OpenSSL Project Authors | ok |
| Microsoft Visual C++ runtime (VCRUNTIME140*.dll, MSVCP140*.dll) | 14.x as shipped in Python 3.12.10 and the Qt/NumPy wheels | Microsoft Visual C++ redistributable terms (Distributable Code) | Microsoft Corporation | **blocker** |
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
| OpenUtau.Core (OpenUtau.Core.dll) | 0.1.565 (commit a60ca5830b9064556157245d4bf8f5920d93e5f8) | MIT; contains code partially based on the VOICEVOX engine (LGPL-3.0), a C# port of SimpleEnunu's f0_smoother (MIT) and a Deque implementation matching Nito.Collections.Deque (MIT); embeds data of unverified provenance | Copyright (c) 2014 StAkira and OpenUtau contributors; (c) 2023 oatsu (SimpleEnunu); (c) 2015 Stephen Cleary (Deque); the VOICEVOX engine authors; (c) 2017 Ryuichi Yamamoto and the University of Edinburgh (Merlin-derived code in Plugin.Builtin) | **blocker** |
| OpenUtau.Plugin.Builtin (phonemizers) | 0.1.565 (same commit) | MIT | Copyright (c) 2014 StAkira and OpenUtau contributors | ok |
| worldline.dll (OpenUtau's native resampler/vocoder, prebuilt win-x64) | from OpenUtau 0.1.565 (runtimes/win-x64/native/worldline.dll) | MIT (OpenUtau's own sources) combined with GPL-2.0 (tk::spline) and unlicensed (libpyin) code | StAkira and contributors; Tino Kluge (spline); Masanori Morise (WORLD); Sleepwalking (libpyin, libgvps) | **blocker** |
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

### Obligations and sources

| Component | Source | Obligations / notes |
|---|---|---|
| BLT Music Generator (application code, launchers, icon, generated notices) | this repository | Name the copyright holder in LICENSE and confirm Apache-2.0 for the release. Original artwork only (the icon is drawn by packaging/make_icon.py); no third-party fonts or images are shipped. The Python sources are frozen inside the two executables. |
| CPython runtime and standard library | https://www.python.org/downloads/release/python-31210/ (the interpreter that builds the package) | Include the Python licence text and copyright notices. |
| Third-party code inside CPython's extension modules (expat in pyexpat, libmpdec in _decimal, bzip2 in _bz2, liblzma in _lzma) | CPython 3.12.10 Windows build (see 'Licenses and Acknowledgements for Incorporated Software' in the Python documentation) | Reproduce the expat, libmpdec and bzip2 notices (shipped). Version of each embedded library not individually read; the licences are those of every release of these libraries. |
| libffi (libffi-8.dll, from the Python distribution) | https://github.com/libffi/libffi | Reproduce the MIT notice. The exact libffi version inside the Python build was not read; the licence is MIT for all releases. |
| OpenSSL libcrypto (libcrypto-3.dll, used by hashlib) | https://www.openssl.org/ | Reproduce the Apache-2.0 text (OpenSSL 3.x is Apache-2.0). libssl and the _ssl module are excluded from the package; BLT makes no network connections. |
| Microsoft Visual C++ runtime (VCRUNTIME140*.dll, MSVCP140*.dll) | Python 3.12.10 installation; PySide6 and NumPy wheels | Microsoft permits redistributing the Visual C++ runtime files under its Distributable Code terms; the exact terms that apply to these copies were not reviewed or reproduced. Needs a human decision: confirm the terms, or have the installer run Microsoft's official Visual C++ Redistributable instead of carrying app-local copies. |
| PyInstaller bootloader and runtime hooks (inside the two executables) | https://pyinstaller.org/ | The bootloader exception allows distributing the frozen program under any licence; ship PyInstaller's COPYING.txt. |
| PySide6 and shiboken6 (Qt for Python bindings) | https://code.qt.io/cgit/pyside/pyside-setup.git (tag v6.11.2); wheels from PyPI | LGPL-3.0: ship the LGPL and GPL texts (done); keep the libraries as separate replaceable DLLs/PYDs (done: one-folder layout); state that the application uses PySide6/Qt under the LGPL; offer the corresponding source and any modifications (none made). A source offer is drafted in NOTICES.txt but has not been reviewed by a person. Blocker until a person confirms the LGPL-3.0 compliance statement. If commercial licensing is preferred instead, this entry changes. |
| Qt libraries and plugins (Qt6Core, Qt6Gui, Qt6Widgets, platform and image plugins) | https://download.qt.io/official_releases/qt/6.11/6.11.2/ | LGPL-3.0 as for PySide6 (statement in NOTICES.txt). Qt's third-party attributions are reproduced: the verbatim qt_attribution.json files and licence texts of qtbase at tag v6.11.2 for every bundled component that can be part of Qt6Core, Qt6Gui, Qt6Widgets and the windows/offscreen/ico plugins (PCRE2, FreeType, HarfBuzz, libpng, zlib, TinyCBOR, double-conversion, the Unicode data and more). A deliberate superset (it includes entries for code that may not be compiled into the Windows binaries), produced by packaging/qt_attribution.py. A string search of the shipped DLLs confirmed that PCRE2, FreeType, HarfBuzz, libpng, zlib, TinyCBOR and the Unicode tables are in them. The LGPL statement itself is tracked under 'pyside6'. |
| NumPy (numpy package) | https://numpy.org/ (PyPI wheel) | Reproduce the NumPy licence and the licences of its bundled sub-components (shipped from the wheel's dist-info). |
| OpenBLAS (numpy.libs/libscipy_openblas64_*.dll) and its runtime libraries | NumPy wheel (scipy-openblas64) | Reproduce the notices: NumPy's licence file for this wheel names exactly this DLL (numpy.libs\libscipy_openblas*.dll) for OpenBLAS, LAPACK and the GCC runtime library (GCC Runtime Library Exception 3.1) and is shipped verbatim (licenses	hird-party umpy\LICENSE.txt), together with the GPL-3.0 text. Relies on the NumPy project's published licence inventory for its wheel; it was not re-derived from the binary. |
| mido | https://github.com/mido/mido | Reproduce the copyright notice and licence text (shipped). |
| defusedxml | https://github.com/tiran/defusedxml | Reproduce the copyright notice and licence text (shipped). |
| platformdirs | https://github.com/tox-dev/platformdirs | Reproduce the copyright notice and licence text (shipped). |
| packaging | https://github.com/pypa/packaging | Reproduce the copyright notice and licence text (shipped). |
| typing_extensions | https://github.com/python/typing_extensions | Reproduce the copyright notice and licence text (shipped). |
| OpenUtau.Core (OpenUtau.Core.dll) | https://github.com/stakira/OpenUtau (tag 0.1.565, built unmodified from that commit) | MIT notice and the upstream MIT/Apache notices of the ported code (shipped). LGPL-3.0: OpenUtau.Core.Voicevox (VoicevoxRenderer, VoicevoxUtils, VoicevoxConfig) states it is 'partially based on the VOICEVOX engine' (LGPL_LICENSE), so OpenUtau.Core.dll is distributed with the LGPL text (shipped), as a separate replaceable DLL, built unmodified from the public commit named above; the written statement is in NOTICES.txt. Embedded data: the g2p models (arpabet, arpabet-plus, de, es, fr, it, ja-mono, ko, pt, ru) were contributed to the MIT repository by named contributors (e.g. commits 22e0c887, 2d0fcbe7, 8b8104ae, ed3267b9), the Vogen models and yue.csv by the maintainer in 2022 (e6486acc, 5b698e5b); none carries a licence statement, and the training data or dictionaries they derive from (for example CMUdict for the English model) are not named. The CREPE tiny.onnx model is MIT (Jong Wook Kim; licence shipped). Release blocker until a person (1) confirms the LGPL handling of the VOICEVOX-derived classes and (2) the owner of the embedded g2p/Vogen data is asked to confirm it may be redistributed, or those features are removed from a BLT-specific build of OpenUtau.Core (which would no longer be the unmodified upstream binary). |
| OpenUtau.Plugin.Builtin (phonemizers) | https://github.com/stakira/OpenUtau | MIT notice (shipped). The sources were searched for licence, copyright and derived-from statements. Found: EnunuOnnx/Merlin.cs is adapted from nnmnkwii (MIT), itself from Merlin (Apache-2.0) - both notices shipped under 'openutau-core'; GermanDiphonePhonemizer is based on the German CMUSphinx dictionary (named in the source; the dictionary is not embedded as a file); several phonemizers say they are 'based on' another phonemizer or reclist from the same community (no licence terms stated). The Data\*.template.yaml files are contributor-authored within the MIT repository. Residual risk: the in-repository authorship statements are not independently verified. |
| worldline.dll (OpenUtau's native resampler/vocoder, prebuilt win-x64) | https://github.com/stakira/OpenUtau/tree/0.1.565/cpp | worldline compiles third-party code: the header-only tk::spline (ttk592/spline) is GPL-2.0 and is included by worldline's effects code; libpyin (Sleepwalking/libpyin) has no licence file in its repository; libgvps is BSD-3-Clause; WORLD is modified BSD; libnpy and miniaudio are permissive. A binary containing GPL-2.0 code may be distributed only under GPL-2.0 terms (source for the whole work, no further restrictions), which does not fit an Apache-2.0/MIT bundle without that source offer; a library with no licence grants no right to redistribute. RELEASE BLOCKER (conflict). Options: obtain written permission or clarification from upstream; rebuild worldline without spline and libpyin; or distribute under GPL-2.0 compliance. The installer can still be built for internal acceptance testing, flagged as not for release. |
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
| Microsoft.ML.OnnxRuntime.Managed (NuGet package) | https://www.nuget.org/packages/Microsoft.ML.OnnxRuntime.Managed/1.16.3 | Reproduce the copyright notice and licence text (shipped). The managed wrapper only: the native onnxruntime.dll is pruned (host/prune.txt), so ONNX-based renderers are unavailable in this build. |
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

### Deliberately not shipped

| Item | Licence | Why | How it is excluded |
|---|---|---|---|
| NetMQ 4.0.1.13 (NetMQ.dll) | LGPL-3.0 (COPYING.LESSER in its repository) | OpenUtau's DAW-bridge messaging; unused by the headless host. The LGPL replaceability duties are avoided by not shipping it. | host/prune.txt; the host and backend tests and `blt selftest` pass without it. |
| AsyncIO 0.1.69 (AsyncIO.dll) | unspecified in the package | Transitive dependency of NetMQ. | host/prune.txt |
| NaCl.Net 0.1.13 (NaCl.dll) | MPL-2.0 | Transitive dependency of NetMQ. | host/prune.txt |
| ONNX Runtime native (onnxruntime.dll, onnxruntime.lib) | MIT, with bundled third-party notices that were not read | Only the neural renderers (DiffSinger, ENUNU, Vogen, CREPE) need it; BLT supports the classic and WORLDLINE-R renderers. | host/prune.txt. Consequence: neural renderers are unavailable in this build. |
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
