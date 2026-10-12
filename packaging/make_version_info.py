"""Write the Windows version resource PyInstaller embeds in both executables."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPANY = "The BLT Music Generator authors"


def version() -> str:
    text = (ROOT / "src" / "barbershop_tracks" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__ = "(\d+)\.(\d+)\.(\d+)"', text)
    if match is None:
        raise SystemExit("no x.y.z __version__ found")
    return ".".join(match.groups())


def render(number: str) -> str:
    parts = (*(int(p) for p in number.split(".")), 0)
    strings = {
        "CompanyName": COMPANY,
        "FileDescription": "BLT Music Generator",
        "FileVersion": number,
        "InternalName": "blt",
        "LegalCopyright": f"(c) {COMPANY}. Apache-2.0. Third-party notices: NOTICES.txt.",
        "OriginalFilename": "BLT Music Generator.exe",
        "ProductName": "BLT Music Generator",
        "ProductVersion": number,
    }
    rows = ",\n          ".join(f"StringStruct('{k}', '{v}')" for k, v in strings.items())
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={parts}, prodvers={parts}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
          {rows}])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main() -> None:
    target = ROOT / "research-output" / "work" / "version_info.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(version()), encoding="utf-8")
    print(f"{target} (version {version()})")


if __name__ == "__main__":
    main()
