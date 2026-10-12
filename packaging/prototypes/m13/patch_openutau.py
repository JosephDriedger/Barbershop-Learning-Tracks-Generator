"""M13 prototype (not part of the product build): a copy of the pinned OpenUtau source without the
LGPL-derived Voicevox classes and without the embedded data whose licence is unknown.

    python packaging/prototypes/m13/patch_openutau.py <pinned OpenUtau checkout> <output folder>

Changes to the copy (the pinned checkout itself is never touched):
* delete ``OpenUtau.Core/Voicevox`` (code "partially based on" the LGPL-3.0 VOICEVOX engine) and
  ``OpenUtau.Plugin.Builtin/SimpleVoicevoxENtoJAPhonemizer.cs``, and remove the two places that
  referenced them (``ClassicSingerLoader.cs``, ``Renderers.cs``);
* replace the g2p packs other than ``g2p-arpabet`` (CMUdict) and ``g2p-arpabet-plus`` by empty zips,
  and the Vogen models and ``yue.csv`` by empty files.
Build it like the product host: ``dotnet publish host/BltRenderHost
-p:OpenUtauSrc=<output folder>``.
"""

import io
import shutil
import sys
import zipfile
from pathlib import Path

KEEP_G2P = {"g2p-arpabet.zip", "g2p-arpabet-plus.zip"}


def replace_once(path: Path, old: str, new: str) -> None:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    crlf = "\r\n" in text
    text = text.replace("\r\n", "\n")
    if old not in text:
        raise SystemExit(f"{path}: expected text not found (is this the pinned OpenUtau 0.1.565?)")
    text = text.replace(old, new, 1)
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "bin", "obj", ".vs"))
    shutil.rmtree(target / "OpenUtau.Core" / "Voicevox")
    (target / "OpenUtau.Plugin.Builtin" / "SimpleVoicevoxENtoJAPhonemizer.cs").unlink()
    replace_once(
        target / "OpenUtau.Core" / "Classic" / "ClassicSingerLoader.cs",
        "                case USingerType.Voicevox:\n"
        "                    return new Core.Voicevox.VoicevoxSinger(v) as USinger;\n",
        "",
    )
    replace_once(
        target / "OpenUtau.Core" / "Render" / "Renderers.cs",
        "            } else if (renderer == VOICEVOX) {\n"
        "                return new Voicevox.VoicevoxRenderer();\n",
        "",
    )
    empty = io.BytesIO()
    zipfile.ZipFile(empty, "w").close()
    for pack in (target / "OpenUtau.Core" / "G2p" / "Data").glob("*.zip"):
        if pack.name not in KEEP_G2P:
            pack.write_bytes(empty.getvalue())
    for data in (target / "OpenUtau.Core" / "Vogen" / "Data").iterdir():
        if data.suffix in (".onnx", ".csv"):
            data.write_bytes(b"")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
