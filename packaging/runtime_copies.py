"""Which Microsoft runtime DLLs does the package import without carrying them?

BLT does not ship Microsoft's Visual C++ runtime (the installer requires Microsoft's own
redistributable, see ``core/runtime/vcruntime.py``). Two kinds of import then have to be satisfied
from the user's PC:

* plain names (``VCRUNTIME140.dll``, ``MSVCP140.dll``...): the installed redistributable has them;
* names a wheel builder renamed with a hash (NumPy: ``msvcp140-<hash>.dll``): no such file exists on
  a PC, so the installer copies the PC's own ``msvcp140.dll`` under that name. That is a copy of a
  file the user already has, not a redistribution.

    python packaging/runtime_copies.py DIST                    # prints the hashed names
    python packaging/runtime_copies.py DIST --check NAME...   # fails unless exactly these

The check also fails if the package contains any Visual C++ runtime file itself.
"""

import re
import sys
from pathlib import Path

import pefile

FAMILY = re.compile(
    r"^(vcruntime|msvcp|concrt|vcomp|vccorlib)\d+(_\d+|_[a-z_]+)?(-[0-9a-f]{32})?\.dll$"
)
HASHED = re.compile(r"^(?P<base>[a-z]+\d+(?:_\d+)?)-[0-9a-f]{32}\.dll$")


def scan(dist: Path) -> tuple[set[str], set[str], set[str]]:
    """(hashed imports, plain imports, runtime files present in the package)."""
    hashed: set[str] = set()
    plain: set[str] = set()
    present: set[str] = set()
    for path in dist.rglob("*"):
        if not path.is_file():
            continue
        if FAMILY.match(path.name.lower()):
            present.add(path.relative_to(dist).as_posix())
        if path.suffix.lower() not in (".dll", ".pyd", ".exe"):
            continue
        try:
            pe = pefile.PE(str(path), fast_load=True)
            pe.parse_data_directories(
                directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
            )
        except pefile.PEFormatError:
            continue
        for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
            name = entry.dll.decode().lower()
            if FAMILY.match(name):
                (hashed if HASHED.match(name) else plain).add(name)
    return hashed, plain, present


def system_source(hashed_name: str) -> str:
    """The plain system file a hashed copy stands for (msvcp140-<hash>.dll -> msvcp140.dll)."""
    match = HASHED.match(hashed_name)
    if match is None:
        raise ValueError(hashed_name)
    return match.group("base") + ".dll"


def main() -> int:
    dist = Path(sys.argv[1])
    hashed, _plain, present = scan(dist)
    if "--check" not in sys.argv:
        for name in sorted(hashed):
            print(name)
        return 0
    expected = set(sys.argv[sys.argv.index("--check") + 1 :])
    problems = []
    if present:
        problems.append(f"the package carries Microsoft runtime files: {sorted(present)}")
    if hashed != expected:
        problems.append(
            f"hashed runtime imports {sorted(hashed)} differ from the installer's "
            f"{sorted(expected)}"
        )
    for problem in problems:
        print("FAIL:", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
