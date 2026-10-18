"""The host inventory check for a macOS host: ``verify_host_inventory.py`` with the macOS names.

    python packaging/verify_host_inventory_macos.py HOST_DIR [--g2p-model included|excluded|auto]

``verify_host_inventory.py`` is covered by a recorded sign-off of the release gate (it decides
what a released host may contain), so it is not edited for macOS. This script imports it and uses
its comparison unchanged (``compare``: the exact set of phonemizers, types and embedded resources,
the removed engines, the neural model); only what is platform-specific is redone here: the
executable (``blt-render-host``, no ``.exe``), the native onnxruntime (``libonnxruntime.dylib``),
and the allow-list, which is ``compliance/host-inventory.json`` unless
``compliance/host-inventory-macos.json`` exists (a macOS host has no NAudio output code, so the
set of types may differ; the file is written by ``--write-expected`` exactly as the Windows one is
and needs the same review)."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script's folder out

import verify_host_inventory as base

ROOT = base.ROOT
HOST_EXE = "blt-render-host"
ONNXRUNTIME = "libonnxruntime.dylib"
EXPECTED_MACOS = ROOT / "compliance" / "host-inventory-macos.json"


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


def file_problems(host_dir: Path, model_present: bool) -> list[str]:
    """Files beside the host that must agree with whether the neural model is there."""
    problems: list[str] = []
    for dll in base.ASSEMBLIES:
        path = host_dir / dll
        if path.is_file():
            found = base.FORBIDDEN_BYTES.search(path.read_bytes())
            if found:
                name = found.group().decode("ascii")
                problems.append(f"{dll} contains the name {name}: removed code is in the build")
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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", type=Path)
    parser.add_argument("--g2p-model", choices=("included", "excluded", "auto"), default="auto")
    parser.add_argument(
        "--write-expected",
        action="store_true",
        help="write compliance/host-inventory-macos.json from this host (a reviewer's job)",
    )
    args = parser.parse_args(argv)
    actual = run_inventory(args.host)
    if args.write_expected:
        if actual.get("g2p_model") != "excluded":
            raise SystemExit("write the allow-list from the model-free host")
        windows = json.loads(base.EXPECTED.read_text(encoding="utf-8"))
        expected = dict(windows)
        expected["about"] = (
            "Reviewed allow-list of what the macOS blt-render-host may contain "
            "(packaging/verify_host_inventory_macos.py). Generated from the pinned, patched "
            "OpenUtau build on macOS; edit only with a reviewer."
        )
        expected["types"] = base.type_digest(actual["types"])
        EXPECTED_MACOS.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {EXPECTED_MACOS}")
        return 0
    sys.path.insert(0, str(ROOT / "src"))
    from barbershop_tracks.core.pipeline.config import ENGLISH_PHONEMIZERS, REMOVED_PHONEMIZERS

    path = EXPECTED_MACOS if EXPECTED_MACOS.is_file() else base.EXPECTED
    expected = json.loads(path.read_text(encoding="utf-8"))
    if expected.get("schema") != base.SCHEMA:
        raise SystemExit(f"{path}: unexpected schema")
    problems = base.compare(
        actual,
        expected,
        g2p_model=args.g2p_model,
        removed=REMOVED_PHONEMIZERS,
        required=(*ENGLISH_PHONEMIZERS, base.DEFAULT_PHONEMIZER),
    )
    problems += file_problems(args.host, actual.get("g2p_model") == "included")
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1
    print(
        f"host inventory ok ({path.name}): {len(actual['phonemizers'])} phonemizers and "
        f"{len(actual['resources'])} embedded resources, all on the allow-list; none of the "
        f"removed engines; g2p model {actual['g2p_model']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
