"""Assemble the LGPL "corresponding source" materials that accompany a release (nothing is uploaded).

BLT uses Qt 6.11.2 and PySide6 6.11.2 under the GNU LGPL version 3, as unmodified separate files. The
LGPL (and the GPL section 6 it refers to) requires that whoever hands out the binaries also hands out,
or offers in writing, the corresponding source. BLT's arrangement: every release on the project's
GitHub page carries one extra asset, ``BLT-Music-Generator-<version>-corresponding-source.zip``, built
by this script from

* the Qt Project's own source archives for qtbase and Qt for Python (PySide6), byte for byte, checked
  against the hashes recorded here and against the tag in Qt's repository;
* BLT's own source at the release commit (``git archive``), which holds the build scripts;
* a manifest of the pinned third-party sources the build downloads (the permissively licensed ones);
* the written offer and the instructions for replacing the Qt and PySide6 libraries.

    python packaging/compliance.py --out DIR [--version 0.1.0]

The output folder holds the zip, its SHA-256 and the loose documents. Nothing here publishes anything:
attaching the zip to the GitHub release is a manual step done together with the installer.
"""

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GITHUB = "https://github.com/JosephDriedger/Barbershop-Learning-Tracks-Generator"
QT = "6.11.2"
QT_BASE = f"https://download.qt.io/official_releases/qt/6.11/{QT}/submodules"
PYSIDE_BASE = f"https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-{QT}-src"
SOURCES = {
    "qtbase": (f"{QT_BASE}/qtbase-everywhere-src-{QT}.tar.xz", "qtbase", f"v{QT}"),
    "pyside-setup": (
        f"{PYSIDE_BASE}/pyside-setup-everywhere-src-{QT}.tar.xz",
        "pyside-setup",
        f"v{QT}",
    ),
}
# The release tags in the Qt Project's own repositories (annotated tags: object -> commit), read on
# 2026-10-13 (qtbase: github.com/qt/qtbase; pyside-setup: git ls-remote https://code.qt.io/pyside/
# pyside-setup.git). Qt publishes no checksum for the pyside-setup archive, so the SHA-256 recorded
# in the manifest is BLT's own measurement of what it downloaded.
TAG_COMMITS = {
    "qtbase": (
        "7a59d906fb765eb85759d4d3cae45d3f295f6359",
        "ef55f427f2c8b410d34f8a7681020a3000cf6866",
    ),
    "pyside-setup": (
        "bd13ae01c34bd018aa53f29b6044043a255cf9e0",
        "24627cd36e1593adf22eb1f2950e4248e7bcc1ec",
    ),
}
REPLACEABLE = (
    "_internal/PySide6/Qt6Core.dll, Qt6Gui.dll, Qt6Widgets.dll",
    "_internal/PySide6/plugins/platforms/qwindows.dll, qoffscreen.dll and plugins/imageformats/qico.dll",
    "_internal/PySide6/QtCore.pyd, QtGui.pyd, QtWidgets.pyd, pyside6.abi3.dll",
    "_internal/shiboken6/Shiboken.pyd, shiboken6.abi3.dll",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, target: Path) -> None:
    if target.exists():
        return
    print("downloading", url)
    with urllib.request.urlopen(url) as response, target.open("wb") as out:  # fixed https URLs
        shutil.copyfileobj(response, out)


def written_offer(version: str, items: dict[str, dict[str, str]]) -> str:
    lines = [
        "WRITTEN OFFER AND SOURCE FOR THE QT AND PYSIDE6 LIBRARIES IN BLT MUSIC GENERATOR",
        "=" * 80,
        "",
        f"BLT Music Generator {version} (Copyright 2026 Joseph Driedger, Apache License 2.0) contains Qt {QT} and",
        f"PySide6 / shiboken6 {QT} (Qt for Python), licensed under the GNU Lesser General Public License,",
        "version 3 (licenses/LGPL-3.0-only.txt and licenses/GPL-3.0-only.txt in the program folder). They are",
        "included unmodified, as the separate files listed in RELINKING.md (plus four small Python modules",
        "of PySide6 and shiboken6 that PyInstaller freezes into the two .exe files; RELINKING.md says how to",
        "replace those by rebuilding).",
        "",
        "1. Where the source is",
        "   Each release of BLT Music Generator on its GitHub page carries the asset",
        f"   BLT-Music-Generator-{version}-corresponding-source.zip next to the installer:",
        f"   {GITHUB}/releases/tag/v{version}",
        "   It contains, unchanged from the Qt Project's downloads:",
    ]
    for item in items.values():
        lines.append(f"     {item['file']}  (SHA-256 {item['sha256']})")
    lines += [
        "   plus BLT's own source at the release commit (blt-source), the build scripts and this offer.",
        "",
        "2. Written offer",
        f"   If you received BLT Music Generator {version} but cannot get that file from the page above, ask for it",
        f"   by opening an issue at {GITHUB}/issues and we will give you a copy, at no charge beyond the",
        "   reasonable cost of physically providing it, for at least three years after the last time this",
        "   version was distributed, and for as long as the page offers the installer.",
        "",
        "3. Your right to replace the libraries",
        "   You may replace the Qt and PySide6 files with other builds of the same version (or interface-",
        "   compatible ones) and run BLT with them; nothing in BLT checks, signs or restricts them. See",
        "   RELINKING.md. You may modify, and reverse-engineer for debugging, those libraries under the LGPL.",
        "",
        "BLT's own code is not covered by the LGPL; nothing in the Apache License of BLT restricts the above.",
    ]
    return "\n".join(lines) + "\n"


def relinking(version: str) -> str:
    files = "\n".join(f"  * {line}" for line in REPLACEABLE)
    return f"""# Replacing the Qt and PySide6 libraries in BLT Music Generator {version}

BLT is installed as a folder (by default `%LOCALAPPDATA%\\Programs\\BLT Music Generator`). Qt and PySide6
are ordinary separate files inside it, loaded at run time; they are not merged into the program:

{files}

To use your own build of Qt {QT} / PySide6 {QT} (or an interface-compatible one):

1. Build or obtain the libraries. The unmodified source is in this bundle (`qtbase-everywhere-src-{QT}.tar.xz`
   and `pyside-setup-everywhere-src-{QT}.tar.xz`); `pip download PySide6=={QT}` gets the binary wheel BLT uses.
2. Close BLT. Copy your files over the ones named above (keep the file names and folders).
3. Start BLT. If a file is missing or incompatible Windows reports "DLL load failed"; restore the original.
4. `blt.exe diagnostics` and `"BLT Music Generator.exe" --smoke-test` (with the environment variable
   `QT_QPA_PLATFORM=offscreen`) check that the program starts with your libraries.

BLT's own program code is frozen with PyInstaller into the two `.exe` files; the Qt and PySide6 libraries
listed above are *not* inside them, which is what makes this replacement possible.

One part is inside the executables: four small Python modules of the bindings (`PySide6`, `PySide6.support`,
`PySide6.support.deprecated`, `shiboken6`; the packages' `__init__` and support code), which PyInstaller freezes
into the executables' archives with BLT's own code. To replace those you rebuild the program: unpack the BLT
source of this bundle, install the build environment (`packaging/requirements-build.txt`, but with your own
PySide6 / shiboken6 in place of the pinned wheels), and run `powershell -File packaging/build.ps1`. The build
is reproducible from the source in this bundle.

What has been checked: with `Qt6Widgets.dll` removed the program refuses to start; with a different file
of the same version in its place it starts (`packaging/replaceability-test.ps1`, run for every build).
A build of Qt modified by someone else has not been tried by the BLT project.
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--version", default="0.1.0")
    args = parser.parse_args()
    for package in ("PySide6", "shiboken6"):
        installed = importlib.metadata.version(package)
        if installed != QT:
            raise SystemExit(f"{package} {installed} is installed but this script prepares Qt {QT}")
    out = args.out
    sources = out / "sources"
    sources.mkdir(parents=True, exist_ok=True)

    items: dict[str, dict[str, str]] = {}
    for name, (url, _repo, tag) in SOURCES.items():
        target = sources / url.rsplit("/", 1)[1]
        fetch(url, target)
        items[name] = {
            "file": target.name,
            "url": url,
            "tag": tag,
            "bytes": str(target.stat().st_size),
            "sha256": sha256(target),
        }
        if name in TAG_COMMITS:
            items[name]["tag_object"], items[name]["tag_commit"] = TAG_COMMITS[name]

    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if dirty:
        print(
            "warning: uncommitted changes; the BLT source in the bundle is the last commit (HEAD)"
        )
    blt_zip = sources / f"blt-source-{args.version}.zip"
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()
    subprocess.run(
        [
            "git",
            "archive",
            "--format=zip",
            f"--prefix=blt-source-{args.version}/",
            "-o",
            str(blt_zip),
            "HEAD",
        ],
        cwd=REPO,
        check=True,
    )

    third_party = json.loads(
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import json,sys;sys.path.insert(0,'host/native');import prepare;"
                "print(json.dumps({'worldline_commit': prepare.WORLDLINE_COMMIT, 'archives': prepare.ARCHIVES}))",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    manifest = {
        "schema": "blt.corresponding-source/1",
        "product": "BLT Music Generator",
        "version": args.version,
        "blt_commit": commit,
        "lgpl_components": {"qt": QT, "pyside6": QT, "shiboken6": QT},
        "sources": items,
        "blt_source": {"file": blt_zip.name, "sha256": sha256(blt_zip)},
        "pinned_third_party_sources": third_party,
        "openutau": {
            "tag": "0.1.565",
            "commit": "a60ca5830b9064556157245d4bf8f5920d93e5f8",
            "url": "https://github.com/stakira/OpenUtau",
            "modified_by": "host/patch_openutau.py",
        },
        "published": False,
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    (out / "WRITTEN-OFFER.txt").write_text(written_offer(args.version, items), encoding="utf-8")
    (out / "RELINKING.md").write_text(relinking(args.version), encoding="utf-8")

    bundle = out / f"BLT-Music-Generator-{args.version}-corresponding-source.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_STORED) as zf:  # tarballs are already compressed
        for path in (
            out / "MANIFEST.json",
            out / "WRITTEN-OFFER.txt",
            out / "RELINKING.md",
            REPO / "packaging" / "licenses" / "LGPL-3.0-only.txt",
            REPO / "packaging" / "licenses" / "GPL-3.0-only.txt",
        ):
            zf.write(path, path.name)
        for path in sorted(sources.iterdir()):
            zf.write(path, f"sources/{path.name}")
    (out / "SHA256SUMS.txt").write_text(f"{sha256(bundle)} *{bundle.name}\n", encoding="ascii")
    print(f"{bundle} ({bundle.stat().st_size / 1e6:.1f} MB)")
    print(
        "not uploaded: attach it to the GitHub release with the installer when the release is approved"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
