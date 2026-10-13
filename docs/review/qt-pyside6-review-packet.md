# Review packet: Qt and PySide6 under the LGPL-3.0 in BLT Music Generator

For: a person qualified to judge open-source licence compliance (licensing counsel, or the owner with counsel's written advice).
From: the BLT project (owner: Joseph Driedger). Prepared 2026-10-13 (M15). The generated packet folder
(`python packaging/review_packets.py`) holds the exact files, hashes and logs named below.

**This is not legal advice and it does not claim compliance.** It describes what BLT does and what it has tested, and lists the
questions BLT cannot answer itself. The release gate (`docs/release-gate.md`) keeps `qt-lgpl-review` and `qt-source-published` open
until a person signs them.

## 1. What is used

| | |
|---|---|
| Libraries | Qt **6.11.2** (Qt6Core, Qt6Gui, Qt6Widgets; platform plugins `qwindows`, `qoffscreen`; image plugin `qico`) and **PySide6 / shiboken6 6.11.2** (Qt for Python bindings) |
| Origin | the binary wheels `PySide6`, `PySide6_Essentials`, `PySide6_Addons`, `shiboken6` 6.11.2 from PyPI (`pip install`, version-pinned in `packaging/requirements-build.txt`; the build fails if the installed versions differ); built by The Qt Company |
| Licence offered by the wheels | "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only" (package metadata). **BLT elects LGPL-3.0-only.** BLT uses no Qt module that is GPL-only or commercial-only (only Core, Gui, Widgets and the three plugins are shipped; `packaging/inventory.py` fails the build on any file that no audited component owns) |
| BLT's own licence | Apache-2.0, "Copyright 2026 Joseph Driedger" |
| Modified? | **No.** `packaging/review_packets.py` compares every Qt/PySide6 file in the package with the hash the wheel's own `RECORD` lists (result in `evidence/qt-files-vs-wheel-record.json`) |
| How it is shipped | the one-folder PyInstaller package, installed per user by an Inno Setup installer. Qt and the binding libraries are **loose files** under `_internal\PySide6\` and `_internal\shiboken6\`: `Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Widgets.dll`, `QtCore.pyd`, `QtGui.pyd`, `QtWidgets.pyd`, `pyside6.abi3.dll`, `Shiboken.pyd`, `shiboken6.abi3.dll`, `plugins\platforms\*.dll`, `plugins\imageformats\qico.dll` (list with sizes and SHA-256: `evidence/qt-files-in-package.json`) |
| What is inside the executables | BLT's code and **four small Python modules of the bindings** (`PySide6/__init__`, `PySide6.support`, `PySide6.support.deprecated`, `shiboken6/__init__`) that PyInstaller freezes into the archive of `BLT Music Generator.exe` and `blt.exe`. The libraries themselves are not inside the executables |
| Where BLT is distributed from (proposed) | the BLT GitHub repository's release page: https://github.com/JosephDriedger/Barbershop-Learning-Tracks-Generator/releases (nothing is published yet) |

## 2. What the LGPL-3.0 asks, and what BLT does

(Section numbers are those of the LGPL-3.0 and, where it incorporates it, GPL-3.0.)

| Obligation | What BLT does | Evidence | Open point |
|---|---|---|---|
| **LGPL 4(a)**: prominent notice that the Library is used and covered by the licence | `NOTICES.txt` section "Qt and PySide6 (LGPL-3.0)" (text in `qt-statement.txt`), installed beside the program; Help > About in the GUI says "uses Qt and PySide6 under the GNU LGPL version 3" and points to Help > Third-party notices | `evidence/notices-qt-section.txt` | Is the placement prominent enough? |
| **LGPL 4(b)**: a copy of the GPL and the LGPL accompanies | `licenses\LGPL-3.0-only.txt` and `licenses\GPL-3.0-only.txt` in the install folder, verbatim | `evidence/` hashes in `MANIFEST.json` | none known |
| **LGPL 4(c)**: if the program displays copyright notices at run time, include the Library's and a reference to the licence copies | the About dialog states the use of Qt/PySide6 under the LGPL and refers to the third-party notices, which refer to `licenses\` | `src/barbershop_tracks/ui/main_window.py` (`_about`) | Does the About text need Qt's copyright line itself? |
| **LGPL 4(d)(1)**: use a suitable shared-library mechanism: uses at run time a copy of the Library that is *already present on the user's system*, and works with a modified, interface-compatible version | Qt and the bindings are separate DLL/PYD files that the program loads at run time; the installer places them on the user's PC | `packaging/replaceability-test.ps1` (log: `evidence/replaceability-test.log`) | **Does a copy shipped in the application's own folder count as "already present on the user's system"?** BLT assumes yes once installed; this is the reading to confirm. The alternative, 4(d)(0), would mean supplying object code of BLT for relinking |
| **LGPL 4(e)** / GPL-3.0 §6 *Installation Information* (only where a "User Product" restricts installing modified versions) | nothing in BLT checks, signs or pins the libraries; a user can overwrite the files. BLT is a program for a general-purpose PC, not a locked device. The installer and the executables are unsigned today; **if signing is adopted, signing the executables does not make Windows reject a replaced DLL**, and BLT would add no such check | `RELINKING.md` | confirm no Installation-Information duty arises |
| **GPL-3.0 §6**: convey the Corresponding Source of the Library as distributed, by one of the allowed means | BLT relies on §6(d) *and* a written offer in the style of §6(b): the source archives are attached to the same GitHub release as the installer ("equivalent access ... through the same place"), and `WRITTEN-OFFER.txt` promises a copy on request for three years after the last distribution of that version | `WRITTEN-OFFER.txt`, `MANIFEST.json`, `SHA256SUMS.txt`; the bundle `BLT-Music-Generator-<version>-corresponding-source.zip` is built by `packaging/compliance.py` and is **not published** | If the GitHub release page or the bundle disappears, is the offer still met? Is the contact channel (GitHub issues) enough? Would a second host (e.g. an archive) be advisable? |
| **LGPL 4 (intro)**: the Combined Work's terms must not restrict modifying the Library or reverse engineering to debug such modifications | BLT is Apache-2.0; the installer's licence page shows only BLT's own `LICENSE.txt` (Apache-2.0); there are no end-user terms about the libraries | `LICENSE.txt` | confirm the installer's text adds no restriction |
| Third-party code inside Qt | the verbatim `qt_attribution.json` files and licence texts of qtbase at tag v6.11.2 (PCRE2, FreeType, HarfBuzz, libpng, zlib, TinyCBOR, double-conversion, Unicode data and others) are installed under `licenses\third-party\qt\`; a deliberate superset | `packaging/licenses/qt-6.11.2/`, `packaging/components.json` entry `qt` | any component that needs more than a notice? |

## 3. Corresponding source (exact versions and checksums)

All from the Qt Project, unmodified. Qt publishes an MD5 list for qtbase; for the PySide6 source it publishes none, so the SHA-256 is BLT's own measurement.

| Archive | URL | Bytes | SHA-256 | Cross-check |
|---|---|---|---|---|
| `qtbase-everywhere-src-6.11.2.tar.xz` | https://download.qt.io/official_releases/qt/6.11/6.11.2/submodules/qtbase-everywhere-src-6.11.2.tar.xz | 50,582,668 | `5b2e00eccaf5a4d8c14134ffa0ea8dfd0a35ae1ffc7f8d87fa4305a1ed23cf22` | MD5 `cb3b718e2e589b61bd781b4596604a5b` equals Qt's `md5sums.txt`; release tag `v6.11.2` in github.com/qt/qtbase is the annotated tag `7a59d906…` → commit `ef55f427f2c8b410d34f8a7681020a3000cf6866` |
| `pyside-setup-everywhere-src-6.11.2.tar.xz` | https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz | 18,053,248 | `cba47efbaad1bedd529725cbc14e21f156c7a19366f07b3edfbb076ffd7afdf8` | tag `v6.11.2` on code.qt.io/pyside/pyside-setup.git: object `bd13ae01…` → commit `24627cd36e1593adf22eb1f2950e4248e7bcc1ec` |
| BLT source at the release commit | built by `git archive HEAD` in `compliance.py` | varies | recorded in `MANIFEST.json` | the bundle warns if the tree is dirty; a release bundle must be built from the tagged, clean commit |

Not covered by the table: the *binary* wheels' build recipe at The Qt Company (BLT did not build Qt; it redistributes Qt's binaries
and offers Qt's source). A reviewer may ask whether the wheel's DLLs correspond to that source; BLT has no independent proof beyond
Qt's own release.

## 4. Written-offer language (verbatim, as the bundle will contain it)

See `WRITTEN-OFFER.txt` in the packet. Summary of what it promises: the source is on the same release page as the installer; if a
person cannot get it there, they may ask by opening an issue on the BLT repository and receive a copy at no charge beyond the cost of
physically providing it, for at least three years after the last distribution of that version and for as long as the page offers the
installer; the user may replace the libraries and may modify and reverse-engineer them under the LGPL.

## 5. Replacement ("relinking") instructions

`RELINKING.md` in the packet: which files, how to replace them, how to check the program still starts, and (for the four frozen
Python modules) how to rebuild the program from the BLT source in the bundle using the user's own PySide6.

## 6. Replaceability evidence (what was actually tested)

`packaging/replaceability-test.ps1`, run by `packaging/build.ps1` for every build, on a private copy of the package folder:

1. baseline: `BLT Music Generator.exe --smoke-test` (offscreen Qt) starts;
2. with `Qt6Widgets.dll` deleted it **cannot** start: the library really is loaded from that file;
3. with `Qt6Widgets.dll` replaced by a *different* file (the original plus four appended bytes; Windows ignores trailing bytes in a DLL)
   it starts again: BLT neither pins nor checks the file.

Log: `evidence/replaceability-test.log`. **Limits, stated plainly:** no Qt build modified by anyone else was ever substituted; the test
covers one DLL; the four frozen Python modules were not replaced (the rebuild path in `RELINKING.md` is documented, not exercised by
CI).

## 7. Questions for the reviewer

1. Is the arrangement in section 2 sufficient for LGPL-3.0 4(a)–(e) and GPL-3.0 §6, in particular the "already present on the user's
   system" reading of 4(d)(1) for a copy installed in BLT's own folder?
2. Is hosting the source bundle as an asset of the same GitHub release (with the issue-tracker offer) adequate, and for how long must
   it stay? Should BLT keep a second copy elsewhere?
3. Are the four PySide6/shiboken6 Python modules frozen into the executables a problem under 4(d)(1), given the rebuild instructions?
4. Are the notices (About text, `NOTICES.txt`, `licenses\`) adequate, including Qt's third-party components?
5. Does anything change if the installer is code-signed later, or if Qt is ever upgraded or modified?

## 8. What BLT needs back

A signed statement: reviewer name and qualification, date, files and hashes reviewed (the gate's `subjects`), the conclusion
(approved / approved with conditions / not approved) and any required changes. The owner records it with
`python packaging/release_gate.py sign qt-lgpl-review ...`; the second item `qt-source-published` is closed only after the bundle is
actually attached to the release (evidence: the asset's https URL).
