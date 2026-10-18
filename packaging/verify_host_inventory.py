"""Compare what a built render host really contains with the reviewed allow-list.

    python packaging/verify_host_inventory.py HOST_DIR [--g2p-model included|excluded|auto]
    python packaging/verify_host_inventory.py --write-expected HOST_DIR_WITH_MODEL HOST_DIR_WITHOUT_MODEL

``blt-render-host --inventory`` reads the host's own assemblies (nothing of OpenUtau runs) and reports every
phonemizer class and every embedded resource with its size and SHA-256. ``compliance/host-inventory.json``
is the reviewed allow-list. The check fails when

* a phonemizer or an embedded resource appears that the list does not name (so a removed engine, a removed
  dictionary or an unreviewed data file cannot come back by accident, whatever it is called);
* something the list names is missing or has different bytes;
* a phonemizer that BLT calls removed (``core.pipeline.config.REMOVED_PHONEMIZERS``) is present, or one that
  BLT supports (``ENGLISH_PHONEMIZERS``, the default phonemizer) is not;
* the neural English model (``g2p.onnx``) is present with bytes other than the reviewed ones, is present when
  ``--g2p-model excluded`` was asked for, is absent when ``included`` was asked for, or disagrees with
  ``blt-host-build.json`` or with the presence of the native ``onnxruntime.dll`` (which exists only to run it).

This is a check of the PACKAGED artifact (it runs the host that is in the package), complementary to
``packaging/verify_absent_data.py`` (searches the bytes of every file for known removed data) and
``host/verify-host.ps1`` (reflection on the build). The allow-list is a reviewed file: changing it is a visible
change under compliance/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = ROOT / "compliance" / "host-inventory.json"
SCHEMA = "blt.host-inventory/1"
ENGLISH_PACK = "g2p-arpabet"
# type or file names that mean removed code or data has come back (Voicevox: LGPL-derived classes; the others
# need the English "plus" dictionary or the C+V template, whose origin is unknown)
FORBIDDEN_NAMES = re.compile(
    r"Voicevox|ArpabetPlus|ArpasingPlus|EnglishCpV|ARPAPlus", re.IGNORECASE
)
ASSEMBLIES = ("OpenUtau.Core.dll", "OpenUtau.Plugin.Builtin.dll")
FORBIDDEN_BYTES = re.compile(rb"Voicevox[A-Za-z_]|ArpabetPlus|ArpasingPlus|EnglishCpV|ARPAPlus")
MODEL_MEMBER = "g2p.onnx"
WINDOWS = sys.platform == "win32"
HOST_EXE = "blt-render-host.exe" if WINDOWS else "blt-render-host"
# the native runtime that exists only to run the g2p model
ONNXRUNTIME = "onnxruntime.dll" if WINDOWS else "libonnxruntime.dylib"
DEFAULT_PHONEMIZER = "OpenUtau.Core.DefaultPhonemizer"


def run_inventory(host_dir: Path) -> dict[str, Any]:
    """Run ``blt-render-host --inventory`` and return its result object."""
    exe = host_dir / HOST_EXE
    if not exe.is_file():
        raise SystemExit(f"{exe} does not exist")
    done = subprocess.run(
        [str(exe), "--inventory"], capture_output=True, text=True, timeout=120, check=False
    )
    result: dict[str, Any] | None = None
    for line in done.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "result":
                result = event
    if done.returncode != 0 or result is None or result.get("status") != "ok":
        raise SystemExit(
            f"the host did not report its inventory (exit {done.returncode}): "
            f"{(done.stderr or done.stdout).strip()[-400:]}"
        )
    return result


def type_digest(names: list[str]) -> dict[str, Any]:
    """Count and SHA-256 of the sorted type names (one per line)."""
    joined = "\n".join(sorted(names)).encode("utf-8")
    return {"count": len(names), "sha256": hashlib.sha256(joined).hexdigest()}


def resource_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (str(item["assembly"]), str(item["set"]), str(item["name"]))


def describe(key: tuple[str, str, str]) -> str:
    return f"{key[0]}: {key[2]}"


def members_without_model(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [m for m in item.get("zip_members", []) if m["name"] != MODEL_MEMBER]


def model_member(item: dict[str, Any]) -> dict[str, Any] | None:
    for member in item.get("zip_members", []):
        if member["name"] == MODEL_MEMBER:
            return dict(member)
    return None


def compare(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    g2p_model: str = "auto",
    removed: dict[str, str] | None = None,
    required: tuple[str, ...] = (),
) -> list[str]:
    """Every difference between ``actual`` (the host's report) and ``expected`` (the allow-list)."""
    problems: list[str] = []
    if g2p_model not in ("included", "excluded", "auto"):
        raise ValueError(g2p_model)

    # 1. phonemizers: exact set
    have = set(actual.get("phonemizers", []))
    allowed = set(expected["phonemizers"])
    for name in sorted(have - allowed):
        problems.append(f"phonemizer not on the allow-list: {name}")
    for name in sorted(allowed - have):
        problems.append(f"phonemizer on the allow-list is missing: {name}")
    for name in sorted(have):
        short = name.rsplit(".", 1)[-1]
        if removed and short in removed:
            problems.append(f"{name} is a phonemizer BLT removed ({removed[short]}) and it is back")
    for name in required:
        if name not in have:
            problems.append(f"{name} is a phonemizer BLT supports and the host lacks it")

    # 1b. every type of the two assemblies: none that must not return, and the whole set as reviewed
    names = actual.get("types")
    if names is not None:
        for name in sorted(n for n in names if FORBIDDEN_NAMES.search(n))[:10]:
            problems.append(
                f"type {name} is code BLT removed (Voicevox, or the English plus data) and it is back"
            )
        wanted = expected.get("types")
        if wanted is not None and type_digest(names) != wanted:
            problems.append(
                f"the set of types of OpenUtau.Core and OpenUtau.Plugin.Builtin changed: "
                f"{len(names)} types, the reviewed list has {wanted['count']}"
            )

    # 2. embedded resources: exact set, exact bytes
    actual_resources = {resource_key(r): r for r in actual.get("resources", [])}
    expected_resources = {resource_key(r): r for r in expected["resources"]}
    for key in sorted(set(actual_resources) - set(expected_resources)):
        problems.append(f"embedded resource not on the allow-list: {describe(key)}")
    for key in sorted(set(expected_resources) - set(actual_resources)):
        problems.append(f"embedded resource on the allow-list is missing: {describe(key)}")
    for key in sorted(set(actual_resources) & set(expected_resources)):
        a, e = actual_resources[key], expected_resources[key]
        if key[2] == ENGLISH_PACK:
            if members_without_model(a) != e.get("zip_members"):
                problems.append(
                    f"the English pack's dictionary files differ from the reviewed ones "
                    f"(expected {[m['name'] for m in e.get('zip_members', [])]}, "
                    f"found {[m['name'] for m in members_without_model(a)]} or other bytes)"
                )
            continue
        if a.get("size") != e.get("size") or a.get("sha256") != e.get("sha256"):
            problems.append(f"embedded resource changed: {describe(key)}")
        if a.get("zip_members") != e.get("zip_members"):
            problems.append(f"the members of the embedded archive changed: {describe(key)}")

    # 3. the neural model: reviewed bytes only, and only when asked for
    pack: dict[str, Any] | None = None
    for key, item in actual_resources.items():
        if key[2] == ENGLISH_PACK:
            pack = item
    model = model_member(pack) if pack else None
    reported = actual.get("g2p_model")
    if (reported == "included") != (model is not None):
        problems.append(
            f"the host reports g2p_model={reported!r} but the English pack {'has' if model else 'lacks'} {MODEL_MEMBER}"
        )
    if model is not None:
        reviewed = expected.get("g2p_model", {})
        if model.get("sha256") != reviewed.get("sha256") or model.get("size") != reviewed.get(
            "size"
        ):
            problems.append(
                f"{MODEL_MEMBER} in the English pack is not the reviewed model (sha256 {model.get('sha256')})"
            )
    if g2p_model == "included" and model is None:
        problems.append("the g2p model is excluded, but this build was meant to include it")
    if g2p_model == "excluded" and model is not None:
        problems.append("the g2p model is in the host, but this build was meant to exclude it")
    return problems


def file_problems(host_dir: Path, model_present: bool) -> list[str]:
    """Files beside the host that must agree with whether the neural model is there."""
    problems: list[str] = []
    # independent of the host's own report: the names are in the assemblies' metadata if the code is.
    # The bare word "Voicevox" stays (a member of the USingerType enum); the removed classes are
    # VoicevoxSinger, VoicevoxRenderer, ...
    for dll in ASSEMBLIES:
        path = host_dir / dll
        if path.is_file():
            found = FORBIDDEN_BYTES.search(path.read_bytes())
            if found:
                name = found.group().decode("ascii")
                problems.append(f"{dll} contains the name {name}: removed code is in the build")
    # the published host keeps onnxruntime.dll beside the exe; a plain `dotnet build` under runtimes/
    beside = host_dir / ONNXRUNTIME
    nested = tuple((host_dir / "runtimes").glob(f"*/native/{ONNXRUNTIME}"))
    if model_present and not (beside.is_file() or nested):
        problems.append(f"the g2p model is present but {ONNXRUNTIME} is not beside the host")
    if not model_present and beside.is_file():
        problems.append(
            f"the g2p model is excluded but the native {ONNXRUNTIME} is still shipped "
            "(it only runs that model)"
        )
    info_path = host_dir / "blt-host-build.json"
    if info_path.is_file():
        recorded = json.loads(info_path.read_text(encoding="utf-8")).get("g2p_model")
        expected = "included" if model_present else "excluded"
        if recorded is not None and recorded != expected:
            problems.append(
                f"blt-host-build.json says g2p_model={recorded!r}, the host contains {expected!r}"
            )
    return problems


def build_expected(with_model: dict[str, Any], without_model: dict[str, Any]) -> dict[str, Any]:
    """The allow-list from two reports (host with and host without the model); they may differ only in the model."""
    if with_model["phonemizers"] != without_model["phonemizers"]:
        raise SystemExit("the two hosts have different phonemizers")
    if type_digest(with_model.get("types", [])) != type_digest(without_model.get("types", [])):
        raise SystemExit("the two hosts have different types")
    packs = []
    for report in (with_model, without_model):
        packs.append({k: v for k, v in resource_map(report).items() if k[2] != ENGLISH_PACK})
    if packs[0] != packs[1]:
        raise SystemExit("the two hosts differ in resources other than the English pack")
    pack = next(r for r in with_model["resources"] if r["name"] == ENGLISH_PACK)
    other = next(r for r in without_model["resources"] if r["name"] == ENGLISH_PACK)
    model = model_member(pack)
    if (
        model is None
        or members_without_model(pack) != members_without_model(other)
        or model_member(other)
    ):
        raise SystemExit("the English packs do not differ exactly by the model")
    resources = []
    for r in with_model["resources"]:
        if r["name"] == ENGLISH_PACK:
            resources.append(
                {
                    "assembly": r["assembly"],
                    "set": r["set"],
                    "name": r["name"],
                    "zip_members": members_without_model(r),
                }
            )
        else:
            resources.append(r)
    return {
        "schema": SCHEMA,
        "about": (
            "Reviewed allow-list of what blt-render-host may contain (packaging/verify_host_inventory.py). "
            "Generated from the pinned, patched OpenUtau build; edit only with a reviewer."
        ),
        "openutau_commit": str(with_model.get("openutau_commit", "")).split("+")[0],
        "phonemizers": with_model["phonemizers"],
        "types": type_digest(with_model["types"]),
        "resources": resources,
        "g2p_model": {k: model[k] for k in ("name", "size", "sha256")},
    }


def resource_map(report: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {resource_key(r): r for r in report["resources"]}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("hosts", nargs="+", type=Path)
    parser.add_argument("--g2p-model", choices=("included", "excluded", "auto"), default="auto")
    parser.add_argument(
        "--write-expected", action="store_true", help="HOST_WITH_MODEL HOST_WITHOUT_MODEL"
    )
    args = parser.parse_args(argv)
    if args.write_expected:
        if len(args.hosts) != 2:
            parser.error("--write-expected needs the host with the model and the host without it")
        expected = build_expected(run_inventory(args.hosts[0]), run_inventory(args.hosts[1]))
        EXPECTED.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {EXPECTED}")
        return 0
    if len(args.hosts) != 1:
        parser.error("one host directory")
    sys.path.insert(0, str(ROOT / "src"))
    from barbershop_tracks.core.pipeline.config import ENGLISH_PHONEMIZERS, REMOVED_PHONEMIZERS

    host_dir = args.hosts[0]
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    if expected.get("schema") != SCHEMA:
        raise SystemExit(f"{EXPECTED}: unexpected schema")
    actual = run_inventory(host_dir)
    problems = compare(
        actual,
        expected,
        g2p_model=args.g2p_model,
        removed=REMOVED_PHONEMIZERS,
        required=(*ENGLISH_PHONEMIZERS, DEFAULT_PHONEMIZER),
    )
    problems += file_problems(host_dir, actual.get("g2p_model") == "included")
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1
    print(
        f"host inventory ok: {len(actual['phonemizers'])} phonemizers and {len(actual['resources'])} embedded resources, "
        f"all on the allow-list; none of the removed engines; g2p model {actual['g2p_model']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
