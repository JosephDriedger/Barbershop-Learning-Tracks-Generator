"""Check what the built host really contains (it is a patched build of OpenUtau, so trust nothing).

    python host/verify_host.py HOST_DIR OPENUTAU_SRC [--allow-stock-worldline]

The macOS counterpart of ``host/verify-host.ps1`` (which does the same with .NET reflection in
PowerShell); it runs anywhere Python and the host run. It asks the host for its inventory
(``blt-render-host --inventory``: the host reads its own assemblies, nothing of OpenUtau runs) and
fails unless

* no type of OpenUtau.Core or OpenUtau.Plugin.Builtin belongs to the Voicevox classes (derived
  from the LGPL VOICEVOX engine) or to the English "plus" data (Arpasing+, English C+V), and none
  of those names is in the assemblies' bytes either;
* the embedded English dictionary (dict.txt, phones.txt) is byte-identical to the pinned
  OpenUtau's g2p-arpabet (= CMUdict 0.07); its neural model (g2p.onnx) is identical to the pinned
  one or, in the model-free build (the default), absent (``blt-host-build.json`` says which); the
  English "plus" dictionary and the C+V template are absent, and every other g2p pack and every
  Vogen data file is empty;
* the CREPE model is still there (MIT);
* the native resampler is the one recorded in ``blt-host-build.json`` (BLT's build, not the stock
  library) unless ``--allow-stock-worldline`` (local runs only).

``packaging/verify_absent_data.py`` (searches the bytes for the removed data itself) and
``packaging/verify_host_inventory.py`` (the reviewed allow-list) are the companions.
"""

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))

import verify_host_inventory as base  # noqa: E402  (a sibling script, not an installed module)
import verify_host_inventory_macos as inventory  # noqa: E402

REMOVED_NAMES = re.compile(r"Voicevox[A-Za-z_]|ArpabetPlus|ArpasingPlus|EnglishCpV|ARPAPlus")
NATIVE = "worldline.dll" if sys.platform == "win32" else "libworldline.dylib"
ENGLISH = {"g2p-arpabet": "g2p-arpabet.zip"}
PACKS = "OpenUtau.Core.G2p.Data.Resources.resources"
CREPE_SET = "OpenUtau.Core.Analysis.Crepe.Resources.resources"
VOGEN_SET = "OpenUtau.Core.Vogen.Data.VogenRes.resources"
BUILTIN_SET = "OpenUtau.Plugin.Builtin.Data.Resources.resources"
EMPTY_ZIP_LIMIT = 64


def zip_members(path: Path) -> dict[str, str]:
    members: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
        for name in archive.namelist():
            members[name] = hashlib.sha256(archive.read(name)).hexdigest()
    return members


def problems_of(host_dir: Path, openutau_src: Path, *, allow_stock_worldline: bool) -> list[str]:
    problems: list[str] = []
    report = inventory.run_inventory(host_dir)
    info_path = host_dir / "blt-host-build.json"
    info: dict[str, Any] = {}
    if info_path.is_file():
        info = json.loads(info_path.read_text(encoding="utf-8"))
    else:
        problems.append("blt-host-build.json is missing")
    g2p_model = str(info.get("g2p_model") or "included")

    for assembly in base.ASSEMBLIES:
        found = REMOVED_NAMES.search((host_dir / assembly).read_text(encoding="latin-1"))
        if found:
            problems.append(
                f"{assembly} contains the name {found.group()}: the removed Voicevox classes "
                "or the English plus code are in the build"
            )
    removed_types = [t for t in report.get("types", []) if REMOVED_NAMES.search(t)]
    if removed_types:
        problems.append(
            f"{len(removed_types)} type(s) of the removed code are in the build, "
            f"e.g. {removed_types[0]}"
        )

    resources = [r for r in report.get("resources", []) if r["set"] == PACKS]
    if not resources:
        problems.append("the g2p resources are missing")
    pinned = openutau_src / "OpenUtau.Core" / "G2p" / "Data"
    for resource in resources:
        name = str(resource["name"])
        if name in ENGLISH:
            reference = zip_members(pinned / ENGLISH[name])
            built = {m["name"]: m["sha256"] for m in resource.get("zip_members", [])}
            for member in ("dict.txt", "phones.txt"):
                if built.get(member) != reference.get(member):
                    problems.append(
                        f"{name}/{member} differs from the pinned OpenUtau's {ENGLISH[name]}"
                    )
            if g2p_model == "excluded":
                if "g2p.onnx" in built:
                    problems.append(
                        f"{name} still has g2p.onnx, but this host was built without the model "
                        "(blt-host-build.json)"
                    )
            elif built.get("g2p.onnx") != reference.get("g2p.onnx"):
                problems.append(f"{name}/g2p.onnx differs from the pinned OpenUtau's")
            extra = sorted(set(built) - {"dict.txt", "phones.txt", "g2p.onnx"})
            if extra:
                problems.append(f"{name} has unexpected members: {', '.join(extra)}")
        elif "plus" in name:
            problems.append(
                f"the English 'plus' dictionary ({name}) is in the build: "
                "its origin is unverified (docs/g2p-plus-provenance.md)"
            )
        elif int(resource.get("size", 0)) > EMPTY_ZIP_LIMIT:
            problems.append(f"g2p pack {name} is not empty ({resource['size']} bytes)")
    present = {str(r["name"]) for r in resources}
    for name in ENGLISH:
        if resources and name not in present:
            problems.append(f"English dictionary {name} is missing")
    for resource in report.get("resources", []):
        if resource["set"] == BUILTIN_SET and resource["name"] == "en_cPv_template":
            problems.append(
                "the English C+V template is in the build (omitted with the plus dictionary)"
            )
        if resource["set"] == VOGEN_SET and int(resource.get("size", 0)) > 0:
            problems.append(f"Vogen data {resource['name']} is not empty")
    if not any(r["set"] == CREPE_SET and r["name"] == "tiny" for r in report.get("resources", [])):
        problems.append("the CREPE model is missing")

    # the native runtime exists only to run the g2p model
    runtime = inventory.ONNXRUNTIME
    beside = (host_dir / runtime).is_file()
    nested = any((host_dir / "runtimes").glob(f"*/native/{runtime}"))
    if g2p_model == "excluded":
        if beside:
            problems.append(f"{runtime} is shipped although the host has no g2p model to run on it")
    elif not (beside or nested):
        problems.append(
            f"{runtime} is missing: the English g2p fallback needs it (blt-render-host --g2p-check)"
        )

    if info:
        native = host_dir / NATIVE
        if not native.is_file():
            problems.append(f"{NATIVE} is missing")
        elif hashlib.sha256(native.read_bytes()).hexdigest() != info.get("worldline_sha256"):
            problems.append(f"{NATIVE} does not match blt-host-build.json")
        if not allow_stock_worldline and not str(info.get("worldline", "")).startswith("BLT build"):
            problems.append(f"{NATIVE} is not BLT's own build ({info.get('worldline')})")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("host_dir", type=Path)
    parser.add_argument("openutau_src", type=Path)
    parser.add_argument("--allow-stock-worldline", action="store_true")
    args = parser.parse_args()
    found = problems_of(
        args.host_dir.resolve(),
        args.openutau_src.resolve(),
        allow_stock_worldline=args.allow_stock_worldline,
    )
    if found:
        for problem in found:
            print(f"FAIL: {problem}")
        return 1
    print(
        "host ok: no Voicevox types, CMUdict pack identical to the pinned source, no English plus "
        "dictionary or Arpasing+/English C+V, other dictionaries and Vogen data empty, "
        "BLT's own native resampler"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
