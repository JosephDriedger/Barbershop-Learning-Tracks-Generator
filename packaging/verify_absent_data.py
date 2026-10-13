"""Fail if data BLT decided not to distribute is anywhere in a built folder.

    python packaging/verify_absent_data.py <folder> --openutau-src <pinned OpenUtau checkout>

The patch ``host/patch_openutau.py`` removes data from the OpenUtau sources: the English "plus"
dictionary (unverified origin, docs/g2p-plus-provenance.md), the English C+V template, the other
languages' g2p packs and the Vogen models. Looking at resource names would trust the patch; this
script does not. It takes fingerprints (a few 96-byte windows) of every one of those files as they
are in the pinned source and searches every file below ``folder`` for them, byte for byte. OpenUtau
embeds such files unchanged in the assemblies' resources, so a copy anywhere in the package (a DLL,
a renamed file, a data folder) is found. Windows of data that the supported English pack
(``g2p-arpabet.zip``, which is CMUdict) shares with a removed file are not used.
"""

import argparse
import mmap
import sys
from pathlib import Path

WINDOW = 96
FRACTIONS = (0.2, 0.5, 0.8)
# the files whose data must not be in the package (relative to the OpenUtau checkout)
REMOVED = (
    "OpenUtau.Core/G2p/Data/g2p-arpabet-plus.zip",
    "OpenUtau.Plugin.Builtin/Data/en_cPv.template.yaml",
    "OpenUtau.Core/G2p/Data/g2p-de.zip",
    "OpenUtau.Core/G2p/Data/g2p-es.zip",
    "OpenUtau.Core/G2p/Data/g2p-fr.zip",
    "OpenUtau.Core/G2p/Data/g2p-it.zip",
    "OpenUtau.Core/G2p/Data/g2p-ja-mono.zip",
    "OpenUtau.Core/G2p/Data/g2p-ko.zip",
    "OpenUtau.Core/G2p/Data/g2p-pt.zip",
    "OpenUtau.Core/G2p/Data/g2p-ru.zip",
)
REMOVED_FOLDERS = (("OpenUtau.Core/Vogen/Data", (".onnx", ".csv")),)


def fingerprints(path: Path) -> list[bytes]:
    data = path.read_bytes()
    if len(data) < WINDOW * 4:
        return []
    return [data[int(len(data) * f) : int(len(data) * f) + WINDOW] for f in FRACTIONS]


def removed_files(checkout: Path) -> list[Path]:
    files = [checkout / name for name in REMOVED]
    for folder, suffixes in REMOVED_FOLDERS:
        if not (checkout / folder).is_dir():
            raise SystemExit(
                f"{checkout / folder} is missing: is --openutau-src the pinned source?"
            )
        files += sorted(p for p in (checkout / folder).iterdir() if p.suffix in suffixes)
    return files


def scan(folder: Path, checkout: Path) -> list[str]:
    """One line per (file in folder, removed source file) pair whose bytes were found."""
    prints: dict[Path, list[bytes]] = {}
    for source in removed_files(checkout):
        if not source.is_file():
            raise SystemExit(f"{source} is missing: is --openutau-src the pinned OpenUtau 0.1.565?")
        found = fingerprints(source)
        if found:
            prints[source] = found
    if not prints:
        raise SystemExit("no fingerprints could be taken: refusing to report a clean result")
    hits: list[str] = []
    for file in sorted(p for p in folder.rglob("*") if p.is_file() and p.stat().st_size >= WINDOW):
        with (
            file.open("rb") as handle,
            mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as view,
        ):
            for source, windows in prints.items():
                if any(view.find(window) >= 0 for window in windows):
                    relative = file.relative_to(folder).as_posix()
                    hits.append(
                        f"{relative} contains data of {source.relative_to(checkout).as_posix()}"
                    )
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--openutau-src", type=Path, required=True)
    args = parser.parse_args()
    hits = scan(args.folder, args.openutau_src)
    if hits:
        for hit in hits:
            print("FOUND:", hit)
        return 1
    print(f"no data of the {len(REMOVED)} removed files and the Vogen models in {args.folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
