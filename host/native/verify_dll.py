"""Checks on BLT's own worldline.dll: no GPL spline inside, and the exports OpenUtau.Core calls.

    python host/native/verify_dll.py worldline.dll worldline.map

The link map lists every symbol that survived linking (``/OPT:REF``); a symbol of ``tk::spline``
there would mean the GPL code is in the binary, so any such symbol fails the build.
"""

import sys
from pathlib import Path

import pefile

EXPECTED_EXPORTS = {
    "DecodeBap",
    "DecodeMgc",
    "F0",
    "PhraseSynthAddRequest",
    "PhraseSynthDelete",
    "PhraseSynthNew",
    "PhraseSynthSetCurves",
    "PhraseSynthSynth",
    "Resample",
    "WorldSynthesis",
    "ou_audio_device_start",
    "ou_audio_device_stop",
    "ou_audio_get_error_message",
    "ou_free_audio_device",
    "ou_free_audio_device_infos",
    "ou_get_audio_device_infos",
    "ou_init_audio_device",
}
# What the DLL may import besides the Windows system libraries: the Visual C++ runtime BLT requires
# the user to have, and the universal CRT.
ALLOWED_IMPORT_PREFIXES = ("kernel32", "msvcp140", "vcruntime140", "api-ms-win-crt-")


def main() -> int:
    dll, link_map = Path(sys.argv[1]), Path(sys.argv[2])
    problems: list[str] = []
    symbols = sum(
        1 for line in link_map.read_text(errors="replace").splitlines() if "@spline@tk@" in line
    )
    if symbols:
        problems.append(f"{symbols} tk::spline symbols are in the link map")
    pe = pefile.PE(str(dll))
    exports = {e.name.decode() for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
    if exports != EXPECTED_EXPORTS:
        problems.append(
            "exports differ: "
            f"extra {sorted(exports - EXPECTED_EXPORTS)}, "
            f"missing {sorted(EXPECTED_EXPORTS - exports)}"
        )
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        name = entry.dll.decode().lower()
        if not name.startswith(ALLOWED_IMPORT_PREFIXES):
            problems.append(f"unexpected import library {name}")
    for problem in problems:
        print("FAIL:", problem)
    if not problems:
        print(f"worldline.dll ok: {len(exports)} exports, no tk::spline symbol in the link map")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
