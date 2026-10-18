"""Checks on BLT's own libworldline.dylib (macOS): no spline code of any kind; the exports
OpenUtau.Core calls.

    python host/native/verify_dylib.py libworldline.dylib worldline.map

The macOS counterpart of ``verify_dll.py``. The tension effect, the only user of a spline in
worldline, is not part of BLT's build. This fails if the link map (every object file and symbol
the linker kept) or the library's own bytes mention a spline: the GPL ``tk::spline`` or any
replacement of it. It also fails if the library exports anything but the functions OpenUtau.Core
calls, or depends on a library other than the system's C and C++ runtimes. Needs ``nm`` and
``otool`` (Xcode command line tools)."""

import re
import subprocess
import sys
from pathlib import Path

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
# What the library may link against besides itself: the C and C++ runtimes that come with macOS.
ALLOWED_LIBRARIES = ("/usr/lib/libSystem.B.dylib", "/usr/lib/libc++.1.dylib")


def run(*command: str) -> str:
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SystemExit(f"{' '.join(command)} failed: {done.stderr.strip()}")
    return done.stdout


def exports(library: Path) -> set[str]:
    names: set[str] = set()
    for line in run("nm", "-gU", str(library)).splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] in ("T", "S", "D", "B", "A"):
            names.add(parts[2].removeprefix("_"))
    return names


def libraries(library: Path) -> list[str]:
    """The libraries the dylib loads (its own install name is the first line and is skipped)."""
    lines = run("otool", "-L", str(library)).splitlines()[1:]
    return [line.split(" (", 1)[0].strip() for line in lines if line.strip()]


def main() -> int:
    library, link_map = Path(sys.argv[1]), Path(sys.argv[2])
    problems: list[str] = []
    forbidden = re.compile(rb"spline|tk::|NaturalCubic", re.IGNORECASE)
    mapped = [line for line in link_map.read_bytes().splitlines() if forbidden.search(line)]
    if mapped:
        problems.append(f"{len(mapped)} spline mentions in the link map, e.g. {mapped[0][:100]!r}")
    in_binary = forbidden.findall(library.read_bytes())
    if in_binary:
        problems.append(
            f"the library's bytes mention a spline {len(in_binary)} times: {in_binary[:3]!r}"
        )
    found = exports(library)
    if found != EXPECTED_EXPORTS:
        problems.append(
            "exports differ: "
            f"extra {sorted(found - EXPECTED_EXPORTS)}, missing {sorted(EXPECTED_EXPORTS - found)}"
        )
    for name in libraries(library):
        if name not in ALLOWED_LIBRARIES:
            problems.append(f"unexpected library dependency {name}")
    for problem in problems:
        print("FAIL:", problem)
    if not problems:
        print(
            f"{library.name} ok: {len(found)} exports, no spline in the link map or the library, "
            "only the system C and C++ runtimes"
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
