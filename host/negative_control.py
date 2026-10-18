"""Prove that the package checks can fail: build the render host from the UNPATCHED pinned OpenUtau
(with the Voicevox classes, the English "plus" dictionary, Arpasing+, English C+V, the other
languages' dictionaries) and run the three checks on it. Each of them must REFUSE this host. If
one passes it, the check is blind and this script fails.

    python host/negative_control.py [--openutau-src DIR] [--out DIR]

The macOS counterpart of ``host/negative-control.ps1`` (and usable anywhere .NET 8 and Python
are). Needs the pinned OpenUtau checkout (``host/build.sh`` fetches it) and a .NET 8 SDK. Nothing
is published; the control host is built into ``research-output/host/unpatched-control`` and is
never packaged."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import patch_openutau  # noqa: E402  (a sibling script, not an installed module)


def expect_refusal(
    name: str, command: list[str], must_mention: list[str], failures: list[str]
) -> None:
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    text = done.stdout + done.stderr
    if done.returncode == 0:
        failures.append(f"{name} PASSED the unpatched host: it is blind")
        return
    for needle in must_mention:
        if needle not in text:
            failures.append(f"{name} refused the host but never mentioned '{needle}'")
    print(f"ok: {name} refused the unpatched host (exit {done.returncode})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--openutau-src", type=Path, default=ROOT / "research-output" / "openutau-src"
    )
    parser.add_argument(
        "--out", type=Path, default=ROOT / "research-output" / "host" / "unpatched-control"
    )
    args = parser.parse_args()
    source = args.openutau_src.resolve()
    out = args.out.resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    os.environ.setdefault("DOTNET_CLI_TELEMETRY_OPTOUT", "1")
    os.environ.setdefault("DOTNET_NOLOGO", "1")
    if not os.environ.get("DOTNET_ROOT"):  # the control host is framework-dependent
        dotnet = shutil.which("dotnet")
        if dotnet:
            os.environ["DOTNET_ROOT"] = str(Path(dotnet).resolve().parent)
    env = dict(os.environ)
    print(f"building the host from the UNPATCHED {source} ...")
    # the host reports words the dictionary lacks through an interface that only BLT's patch adds to
    # OpenUtau; the control host gets that interface as a stub (no phonemizer implements it there)
    stub = out / "BltMissingWordsStub.cs"
    stub.write_text(patch_openutau.MISSING_WORDS_API, encoding="utf-8")
    build = subprocess.run(
        [
            "dotnet",
            "build",
            str(HERE / "BltRenderHost" / "BltRenderHost.csproj"),
            "-c",
            "Release",
            "-o",
            str(out),
            f"-p:OpenUtauSrc={source}",
            "-p:OpenUtauCommit=unpatched-control",
            f"-p:BltMissingWordsStub={stub}",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if build.returncode != 0:
        print("\n".join((build.stdout + build.stderr).splitlines()[-30:]))
        print("FAIL: the control host did not build")
        return 1
    # the checks read blt-host-build.json; this host has BLT's native library absent on purpose
    info = {
        "schema": "blt.host-build/1",
        "worldline": "stock (control)",
        "worldline_sha256": "",
        "g2p_model": "included",
    }
    (out / "blt-host-build.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")

    failures: list[str] = []
    python = sys.executable
    expect_refusal(
        "verify_host_inventory_macos.py",
        [python, "-I", str(ROOT / "packaging" / "verify_host_inventory_macos.py"), str(out)],
        [
            "ArpasingPlusPhonemizer",
            "EnglishCpVPhonemizer",
            "DiffSingerARPAPlusEnglishPhonemizer",
            "g2p_arpabet_plus",
            "Voicevox",
            "BLT removed",
            "set of types",
        ],
        failures,
    )
    expect_refusal(
        "verify_absent_data.py",
        [
            python,
            "-I",
            str(ROOT / "packaging" / "verify_absent_data.py"),
            str(out),
            "--openutau-src",
            str(source),
        ],
        ["g2p-arpabet-plus.zip", "en_cPv.template.yaml"],
        failures,
    )
    expect_refusal(
        "verify_host.py",
        [
            python,
            str(HERE / "verify_host.py"),
            str(out),
            str(source),
            "--allow-stock-worldline",
        ],
        ["Voicevox", "plus", "contains the name"],
        failures,
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "negative control passed: all three checks refuse a host that still has the removed "
        "engines and data"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
