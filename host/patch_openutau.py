"""A copy of the pinned OpenUtau source without the LGPL-derived Voicevox classes and without the
embedded data whose licence is unknown (see docs/m13-compliance.md). ``host/build.ps1`` runs this.

    python host/patch_openutau.py <pinned OpenUtau checkout> <output folder> [--exclude-g2p-model]

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
Always (M18): the two dictionary-based phonemizer bases (``PhonemeBasedPhonemizer``, which Arpasing uses, and
``SyllableBasedPhonemizer``, which English VCCV and X-SAMPA use) record the words their dictionary could not look up
(``OpenUtau.Api.IMissingWordReporter``, a new file). Upstream silently turns such a word into a voicebank alias (Arpasing)
or into the text "word not found" (the syllable phonemizers), i.e. into silence. The host reads the records after
phonemizing and refuses to render (exit 11, naming each word and voice). How a word that IS found is phonemized is unchanged.

With ``--exclude-g2p-model`` (M17, docs/g2p-model-provenance.md) the neural fallback of the English
pack is omitted as well: ``g2p-arpabet.zip`` keeps only ``dict.txt`` (CMUdict) and ``phones.txt``, and
``G2pPack.LoadPack`` accepts a pack without ``g2p.onnx`` (no inference session). Words that are in
CMUdict are phonemized exactly as before; a word that is not in it gets no guess and the phonemizers
treat it as "not found" (a warning, the note stays silent unless the user gives a phonetic hint).
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


MISSING_WORDS_API = """// BLT patch (host/patch_openutau.py): phonemizers that look words up in a dictionary report the words
// they could not find, so that the host can refuse to render instead of silently dropping them.
using System.Collections.Generic;

namespace OpenUtau.Api {
    public struct MissingWord {
        public int position;   // of the note, in ticks of the project
        public string lyric;   // the note's lyric as the phonemizer saw it
        public string word;    // the part of it that has no entry
    }

    public interface IMissingWordReporter {
        List<MissingWord> MissingWords { get; }
    }
}
"""


def report_missing_words(target: Path) -> None:
    """Make both dictionary phonemizer bases record the words their dictionary lacks."""
    api = target / "OpenUtau.Core" / "Api" / "BltMissingWords.cs"
    api.write_text(MISSING_WORDS_API, encoding="utf-8")
    builtin = target / "OpenUtau.Plugin.Builtin"
    phoneme_based = builtin / "PhonemeBasedPhonemizer.cs"
    replace_once(
        phoneme_based,
        "    public abstract class PhonemeBasedPhonemizer : Phonemizer\n    {\n",
        "    public abstract class PhonemeBasedPhonemizer : Phonemizer, IMissingWordReporter\n    {\n"
        "        public List<MissingWord> MissingWords { get; } = new List<MissingWord>();\n"
        "        void ReportMissing(Note note) {  // BLT patch\n"
        "            if (string.IsNullOrEmpty(note.lyric) || !note.lyric.Any(char.IsLetterOrDigit)) return;\n"
        "            lock (MissingWords) {\n"
        "                if (!MissingWords.Any(m => m.position == note.position && m.lyric == note.lyric)) {\n"
        "                    MissingWords.Add(new MissingWord { position = note.position, lyric = note.lyric, word = note.lyric });\n"
        "                }\n"
        "            }\n"
        "        }\n",
    )
    replace_once(
        phoneme_based,
        "                return g2p.Query(note.lyric.ToLowerInvariant());\n",
        "                var found = g2p.Query(note.lyric.ToLowerInvariant());\n"
        "                if (found == null) {\n"
        "                    ReportMissing(note);  // BLT patch\n"
        "                }\n"
        "                return found;\n",
    )
    syllable_based = builtin / "SyllableBasedPhonemizer.cs"
    replace_once(
        syllable_based,
        "    public abstract class SyllableBasedPhonemizer : Phonemizer {\n",
        "    public abstract class SyllableBasedPhonemizer : Phonemizer, IMissingWordReporter {\n"
        "        public List<MissingWord> MissingWords { get; } = new List<MissingWord>();\n"
        "        void ReportMissing(Note note, string word) {  // BLT patch\n"
        "            if (string.IsNullOrEmpty(word) || !word.Any(char.IsLetterOrDigit)) return;\n"
        "            lock (MissingWords) {\n"
        "                if (!MissingWords.Any(m => m.position == note.position && m.word == word)) {\n"
        "                    MissingWords.Add(new MissingWord { position = note.position, lyric = note.lyric, word = word });\n"
        "                }\n"
        "            }\n"
        "        }\n",
    )
    replace_once(
        syllable_based,
        "                    if (subResult == null) {\n                        Log.Warning(",
        "                    if (subResult == null) {\n"
        "                        ReportMissing(note, subword);  // BLT patch\n"
        "                        Log.Warning(",
    )


def exclude_g2p_model(target: Path) -> None:
    """Remove ``g2p.onnx`` from the English pack and let ``G2pPack`` work without a model."""
    pack = target / "OpenUtau.Core" / "G2p" / "Data" / "g2p-arpabet.zip"
    kept = io.BytesIO()
    with zipfile.ZipFile(pack) as source, zipfile.ZipFile(kept, "w", zipfile.ZIP_DEFLATED) as out:
        names = [info.filename for info in source.infolist()]
        if sorted(names) != ["dict.txt", "g2p.onnx", "phones.txt"]:
            raise SystemExit(
                f"{pack}: unexpected members {names} (is this the pinned OpenUtau 0.1.565?)"
            )
        for info in source.infolist():
            if info.filename != "g2p.onnx":
                out.writestr(info, source.read(info.filename))
    pack.write_bytes(kept.getvalue())
    replace_once(
        target / "OpenUtau.Core" / "Api" / "G2pPack.cs",
        "            var session = new InferenceSession(g2pData);\n",
        "            // BLT: a pack without g2p.onnx has no neural fallback (docs/g2p-model-provenance.md)\n"
        "            var session = g2pData == null ? null : new InferenceSession(g2pData);\n",
    )


def main() -> int:
    arguments = [a for a in sys.argv[1:] if a != "--exclude-g2p-model"]
    if len(arguments) != 2 or len(sys.argv) - 1 - len(arguments) > 1:
        print(__doc__)
        return 2
    source, target = Path(arguments[0]), Path(arguments[1])
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
    report_missing_words(target)
    empty = io.BytesIO()
    zipfile.ZipFile(empty, "w").close()
    for pack in (target / "OpenUtau.Core" / "G2p" / "Data").glob("*.zip"):
        if pack.name not in KEEP_G2P:
            pack.write_bytes(empty.getvalue())
    for data in (target / "OpenUtau.Core" / "Vogen" / "Data").iterdir():
        if data.suffix in (".onnx", ".csv"):
            data.write_bytes(b"")
    if "--exclude-g2p-model" in sys.argv[1:]:
        exclude_g2p_model(target)
    print(
        f"wrote {target}"
        + (" (without the g2p model)" if "--exclude-g2p-model" in sys.argv[1:] else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
