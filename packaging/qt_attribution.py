"""Collect Qt's third-party attribution for the Qt libraries BLT ships (run by hand, needs `gh`).

The PySide6 wheels carry Qt 6.11.2 binaries (Core, Gui, Widgets and the windows / offscreen / ico
plugins, all from the qtbase repository). Qt documents what it bundles in ``qt_attribution.json``
files beside the bundled code, naming the licence, licence file and copyright holders. This tool
downloads, for the exact tag, the attribution files that can apply to those modules on Windows (a
deliberate superset: Wayland, XCB, Android, WebAssembly, macOS, SQL, networking and the test library
are left out), the licence files they point at, and the SPDX texts from qtbase's LICENSES folder,
verbatim into ``packaging/licenses/qt-<version>/``, plus a readable ``INDEX.txt``.

    python packaging/qt_attribution.py [--tag v6.11.2]

The result is committed; rerun it when the Qt version changes (the build checks the version).
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = "qt/qtbase"
WANTED_DIRS = (
    "src/3rdparty/D3D12MemoryAllocator",
    "src/3rdparty/VulkanMemoryAllocator",
    "src/3rdparty/blake2",
    "src/3rdparty/double-conversion",
    "src/3rdparty/easing",
    "src/3rdparty/emoji-segmenter",
    "src/3rdparty/forkfd",
    "src/3rdparty/freetype",
    "src/3rdparty/harfbuzz-ng",
    "src/3rdparty/icc",
    "src/3rdparty/libjpeg",
    "src/3rdparty/libpng",
    "src/3rdparty/md4",
    "src/3rdparty/md4c",
    "src/3rdparty/md5",
    "src/3rdparty/pcre2",
    "src/3rdparty/pixman",
    "src/3rdparty/rfc6234",
    "src/3rdparty/sha1",
    "src/3rdparty/sha3",
    "src/3rdparty/siphash",
    "src/3rdparty/tinycbor",
    "src/3rdparty/wintab",
    "src/3rdparty/zlib",
    "src/corelib/global",
    "src/corelib/kernel",
    "src/corelib/mimetypes/3rdparty",
    "src/corelib/text",
    "src/gui/opengl",
    "src/gui/painting",
    "src/gui/rhi",
    "src/gui/text",
    "src/gui/vulkan",
)


def fetch(tag: str, path: str) -> str | None:
    done = subprocess.run(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github.raw",
            f"repos/{REPO}/contents/{path}?ref={tag}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return done.stdout if done.returncode == 0 else None


def entries_of(text: str) -> list[dict[str, object]]:
    data = json.loads(text, strict=False)  # Qt's own files carry raw tabs inside strings
    return data if isinstance(data, list) else [data]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tag", default="v6.11.2")
    args = parser.parse_args()
    out = Path(__file__).with_name("licenses") / f"qt-{args.tag.lstrip('v')}"
    out.mkdir(parents=True, exist_ok=True)
    index = [
        f"Qt {args.tag.lstrip('v')} third-party components that can be part of Qt6Core, Qt6Gui,",
        "Qt6Widgets and the windows / offscreen / ico plugins (a superset), from the",
        f"qt_attribution.json files of qtbase at tag {args.tag}. The verbatim attribution and",
        "licence texts are in this folder.",
        "",
    ]
    wanted_licences: set[str] = set()
    for folder in WANTED_DIRS:
        text = fetch(args.tag, f"{folder}/qt_attribution.json")
        if text is None:
            print(f"error: no attribution file in {folder}", file=sys.stderr)
            return 1
        flat = folder.replace("/", "__")
        (out / "attribution").mkdir(exist_ok=True)
        (out / "attribution" / f"{flat}.json").write_text(text, encoding="utf-8")
        for entry in entries_of(text):
            licence_id = str(entry.get("LicenseId", ""))
            wanted_licences.update(
                i for i in re.split(r"\s+(?:AND|OR|WITH)\s+|[()]", licence_id) if i.strip()
            )
            licence_file = str(entry.get("LicenseFile", ""))
            if licence_file:
                body = fetch(args.tag, f"{folder}/{licence_file}")
                if body is None:
                    print(f"error: {folder}/{licence_file} not found", file=sys.stderr)
                    return 1
                target = out / "files" / flat / licence_file
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
            index.append(f"{entry.get('Name')}  {entry.get('Version', '')}".rstrip())
            index.append(f"    Source:    {folder}")
            index.append(f"    Used in:   {entry.get('QtUsage', '')}")
            index.append(f"    Licence:   {entry.get('License', '')}  [{licence_id}]")
            copyright_lines = entry.get("Copyright", "")
            if isinstance(copyright_lines, list):
                copyright_lines = " | ".join(str(line) for line in copyright_lines)
            index.append(f"    Copyright: {copyright_lines}")
            index.append(f"    Homepage:  {entry.get('Homepage', '')}")
            index.append("")
    for licence_id in sorted(i.strip() for i in wanted_licences):
        body = fetch(args.tag, f"LICENSES/{licence_id}.txt")
        if body is None:
            print(f"note: no LICENSES/{licence_id}.txt in qtbase (its own licence file is used)")
            continue
        (out / "LICENSES").mkdir(exist_ok=True)
        (out / "LICENSES" / f"{licence_id}.txt").write_text(body, encoding="utf-8")
    (out / "INDEX.txt").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
