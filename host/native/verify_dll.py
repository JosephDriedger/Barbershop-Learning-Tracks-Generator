"""Checks on BLT's own worldline.dll: no spline code of any kind; the exports OpenUtau.Core calls.

    python host/native/verify_dll.py worldline.dll worldline.map

The tension effect, the only user of a spline in worldline, is not part of BLT's build. This
fails the build if the link map (every symbol that survived linking, ``/OPT:REF``, and every
object file) or the
DLL's own bytes mention a spline: the GPL ``tk::spline`` or any replacement of it.
"""

import re
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
    forbidden = re.compile(rb"spline|tk::|NaturalCubic", re.IGNORECASE)
    mapped = [line for line in link_map.read_bytes().splitlines() if forbidden.search(line)]
    if mapped:
        problems.append(f"{len(mapped)} spline mentions in the link map, e.g. {mapped[0][:100]!r}")
    in_binary = forbidden.findall(dll.read_bytes())
    if in_binary:
        problems.append(
            f"the DLL's bytes mention a spline {len(in_binary)} times: {in_binary[:3]!r}"
        )
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
        print(f"worldline.dll ok: {len(exports)} exports, no spline in the link map or the DLL")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
