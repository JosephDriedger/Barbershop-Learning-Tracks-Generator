"""A copy of the pinned OpenUtau source without the LGPL-derived Voicevox classes and without the
embedded data whose licence is unknown (see docs/m13-compliance.md). ``host/build.ps1`` runs this.

    python host/patch_openutau.py <pinned OpenUtau checkout> <output folder>

Changes to the copy (the pinned checkout itself is never touched):
* delete ``OpenUtau.Core/Voicevox`` (code "partially based on" the LGPL-3.0 VOICEVOX engine) and
  ``OpenUtau.Plugin.Builtin/SimpleVoicevoxENtoJAPhonemizer.cs``, and remove the two places that
  referenced them (``ClassicSingerLoader.cs``, ``Renderers.cs``);
* replace the g2p packs other than ``g2p-arpabet`` (CMUdict) by empty zips, and the Vogen models and
  ``yue.csv`` by empty files;
* omit the English "plus" dictionary (``g2p-arpabet-plus.zip``, 120k+ entries of unstated origin,
  docs/g2p-plus-provenance.md) together with everything that only exists to use it: the Arpasing+
  and English C+V phonemizers, the DiffSinger English+ phonemizer, ``ArpabetPlusG2p`` and its lyrics
  helper, and the 1.2 MB English C+V template. The data is removed from the sources and from the
  resource tables, so it is not in the built assemblies at all (host/verify-host.ps1 checks that).
Everything that BLT's supported rendering uses (the classic WORLDLINE-R path and the English
phonemizers that run on the CMUdict pack: Arpasing, VCCV, X-SAMPA, ...) is untouched.
"""

import io
import re
import shutil
import sys
import zipfile
from pathlib import Path

KEEP_G2P = {"g2p-arpabet.zip"}
# source files that exist only for the plus dictionary or the English C+V template
PLUS_FILES = (
    "OpenUtau.Core/G2p/ArpabetPlusG2p.cs",
    "OpenUtau.Core/G2p/Data/g2p-arpabet-plus.zip",
    "OpenUtau.Core/DiffSinger/Phonemizers/DiffSingerARPAPlusEnglishPhonemizer.cs",
    "OpenUtau.Plugin.Builtin/ArpasingPlusPhonemizer.cs",
    "OpenUtau.Plugin.Builtin/EnglishCpVPhonemizer.cs",
    "OpenUtau.Plugin.Builtin/Data/en_cPv.template.yaml",
)
# (resource table, name of the resource) to drop from Resources.resx and Resources.Designer.cs
PLUS_RESOURCES = (
    ("OpenUtau.Core/G2p/Data", "g2p_arpabet_plus"),
    ("OpenUtau.Plugin.Builtin/Data", "en_cPv_template"),
)


def remove_resource(folder: Path, name: str) -> None:
    """Delete the ``name`` entry from Resources.resx and its property from Resources.Designer.cs."""
    comment = r"[ \t]*/// <summary>(?:(?!</summary>).)*</summary>\s*"
    prop = rf"internal static byte\[\] {name} " + r"\{.*?\r?\n        \}\r?\n[ \t]*\r?\n?"
    for file, pattern in (
        (folder / "Resources.resx", rf'[ \t]*<data name="{name}" type=.*?</data>\r?\n'),
        (folder / "Resources.Designer.cs", comment + prop),
    ):
        raw = file.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        text, count = re.subn(pattern, "", text, count=1, flags=re.DOTALL)
        if count != 1:
            raise SystemExit(
                f"{file}: resource {name} not found (is this the pinned OpenUtau 0.1.565?)"
            )
        file.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


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
    for relative in PLUS_FILES:
        (target / relative).unlink()
    for folder, name in PLUS_RESOURCES:
        remove_resource(target / folder, name)
    replace_once(
        target / "OpenUtau.Core" / "Util" / "LyricsHelper.cs",
        "            typeof(ArpabetPlusG2pLyricsHelper),\n",
        "",
    )
    replace_once(
        target / "OpenUtau.Core" / "Util" / "LyricsHelper.cs",
        "    public class ArpabetPlusG2pLyricsHelper : G2pLyricsHelper {\n"
        "        public ArpabetPlusG2pLyricsHelper() : base(new ArpabetPlusG2p()) { }\n"
        "    }\n",
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
