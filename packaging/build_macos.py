"""Build BLT Music Generator for macOS: the app, its audit, its smoke tests and an unsigned disk image.

    python packaging/build_macos.py [options]

The counterpart of ``packaging/build.ps1``. Run it on the kind of Mac it builds for (Apple silicon builds
an arm64 app, an Intel Mac an x64 one): the native resampler and the .NET host are built for the machine.

Steps: publish the self-contained render host (pinned OpenUtau, ``host/build.sh --publish``) and verify
what it contains -> PyInstaller builds ``BLT Music Generator.app`` -> the host goes into
``Contents/Helpers/host``, NOTICES.txt and licenses/ into ``Contents/Resources`` -> every file of the app is
audited against ``packaging/components.json`` plus ``packaging/components-macos.json`` -> smoke tests in a
stripped environment and the Qt replaceability test (LGPL) -> a ``.dmg`` -> SHA-256 and release metadata.
Everything is written under ``--out-dir`` (default ``research-output/release-macos``, git-ignored). Nothing
is uploaded or published anywhere.

The app is UNSIGNED and NOT NOTARISED: the owner has not decided on an Apple Developer account. Signing and
notarisation exist below as steps that are off unless asked for (``--sign-identity``, ``--notarize``); they
have never been run by the project. An unsigned app is opened the first time through right-click > Open (see
docs/INSTALL.md).

Options:
  --out-dir DIR          output root
  --skip-host            reuse the host published by an earlier run
  --no-smoke             skip the smoke tests and the replaceability test
  --no-dmg               stop after the app
  --allow-audit-gaps     DEVELOPMENT ONLY: print the audit's gaps and go on (a release build never does)
  --fail-on-blockers     exit non-zero when the licence audit has open release blockers
  --for-release          refuse to build unless the release gate is open (docs/release-gate.md)
  --sign-identity ID     OFF BY DEFAULT: sign with this Developer ID (or BLT_MACOS_SIGN_IDENTITY)
  --notarize PROFILE     OFF BY DEFAULT: notarise the disk image with this notarytool keychain profile
                         (or BLT_MACOS_NOTARY_PROFILE); needs --sign-identity
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script's folder out

import release_gate  # noqa: E402

APP_NAME = "BLT Music Generator.app"
VOLUME = "BLT Music Generator"
README_FIRST = """\
BLT Music Generator for macOS (unsigned)

Drag "BLT Music Generator" onto the Applications folder.

This app is not signed with an Apple Developer ID and not notarised, so macOS will not open it with a
double-click the first time. Open it once with right-click (or Control-click) > Open, then Open again in
the dialog; on newer macOS releases: try to open it, then System Settings > Privacy & Security > "Open
Anyway". If macOS says the app is damaged, remove the download flag in Terminal:

    xattr -dr com.apple.quarantine "/Applications/BLT Music Generator.app"

Voicebanks are not included; add your own with Add voice... in the app. MP3 output needs FFmpeg
(for example: brew install ffmpeg).

This build has had no test on a real Mac by the project's people yet. Please report what you see:
https://github.com/JosephDriedger/Barbershop-Learning-Tracks-Generator/issues
"""


def step(text: str) -> None:
    print(f"\n== {text}", flush=True)


def run(command: list[str], **kwargs: object) -> None:
    done = subprocess.run(command, check=False, **kwargs)  # type: ignore[call-overload]
    if done.returncode != 0:
        raise SystemExit(
            f"{' '.join(str(c) for c in command[:3])} failed with exit code {done.returncode}"
        )


def run_logged(log: Path, command: list[str]) -> None:
    """Like ``run``, and keeps the output as a UTF-8 log (evidence for the review packets)."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8"
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            handle.write(line)
        if process.wait() != 0:
            raise SystemExit(f"{command[0]} failed with exit code {process.returncode}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def version() -> str:
    text = (ROOT / "src" / "barbershop_tracks" / "__init__.py").read_text(encoding="utf-8")
    found = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if found is None:
        raise SystemExit("no __version__ found")
    return found.group(1)


def git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments], capture_output=True, text=True, check=True
    ).stdout.strip()


def mach_o_files(folder: Path) -> list[Path]:
    """Every real file below ``folder`` that is Mach-O code, deepest first (the order to sign in)."""
    found = []
    for path in folder.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as handle:
            magic = handle.read(4)
        if magic in (
            b"\xfe\xed\xfa\xce",
            b"\xfe\xed\xfa\xcf",
            b"\xce\xfa\xed\xfe",
            b"\xcf\xfa\xed\xfe",
            b"\xca\xfe\xba\xbe",
        ):
            found.append(path)
    return sorted(found, key=lambda p: len(p.parts), reverse=True)


def sign_app(app: Path, identity: str) -> None:
    """OFF BY DEFAULT and never run by the project: sign every Mach-O file, then the app.

    Developer ID signing with the hardened runtime. The render host is .NET and the program is Python, so
    both need the entitlements in ``packaging/macos-entitlements.plist`` (JIT, unsigned executable memory,
    libraries signed by someone else). Treat this as a starting point for whoever holds the account.
    """
    entitlements = ROOT / "packaging" / "macos-entitlements.plist"
    for path in mach_o_files(app):
        run(
            [
                "codesign", "--force", "--timestamp", "--options", "runtime",
                "--entitlements", str(entitlements), "--sign", identity, str(path),
            ]
        )  # fmt: skip
    run(
        [
            "codesign", "--force", "--timestamp", "--options", "runtime",
            "--entitlements", str(entitlements), "--sign", identity, str(app),
        ]
    )  # fmt: skip
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)])


def notarize(dmg: Path, profile: str) -> None:
    """OFF BY DEFAULT and never run by the project: submit the disk image to Apple and staple the ticket."""
    run(["xcrun", "notarytool", "submit", str(dmg), "--keychain-profile", profile, "--wait"])
    run(["xcrun", "stapler", "staple", str(dmg)])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "research-output" / "release-macos")
    parser.add_argument("--skip-host", action="store_true")
    parser.add_argument("--no-smoke", action="store_true")
    parser.add_argument("--no-dmg", action="store_true")
    parser.add_argument("--allow-audit-gaps", action="store_true")
    parser.add_argument("--fail-on-blockers", action="store_true")
    parser.add_argument("--for-release", action="store_true")
    parser.add_argument("--sign-identity", default=os.environ.get("BLT_MACOS_SIGN_IDENTITY", ""))
    parser.add_argument("--notarize", default=os.environ.get("BLT_MACOS_NOTARY_PROFILE", ""))
    args = parser.parse_args()
    if platform.system() != "Darwin":  # (not sys.platform: mypy would skip the rest on Windows)
        raise SystemExit("this builds the macOS app and must run on a Mac")
    if args.notarize and not args.sign_identity:
        raise SystemExit("--notarize needs --sign-identity: Apple only notarises signed code")

    machine = platform.machine()
    arch, rid = {"arm64": ("arm64", "osx-arm64"), "x86_64": ("x64", "osx-x64")}[machine]
    out = args.out_dir.resolve()
    work, host_out, dist, artifacts, evidence = (
        out / "work",
        out / "host",
        out / "app",
        out / "artifacts",
        out / "evidence",
    )
    app = dist / APP_NAME
    contents = app / "Contents"
    python = sys.executable
    number = version()
    commit = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    os.environ["SOURCE_DATE_EPOCH"] = git("log", "-1", "--format=%ct")
    nuget = Path(os.environ.get("NUGET_PACKAGES") or Path.home() / ".nuget" / "packages")
    suffix = f"macos-{arch}"
    print(
        f"BLT Music Generator {number} for macOS {arch}, commit {commit}"
        + (" (uncommitted changes)" if dirty else "")
    )
    if args.for_release:
        step("Release gate (--for-release)")
        run([python, "packaging/release_gate.py", "check"], cwd=ROOT)

    # 1. the render host -----------------------------------------------------------------------
    openutau = ROOT / "research-output" / "openutau-src"
    if not args.skip_host:
        step("Publishing the self-contained render host")
        run_logged(
            evidence / "worldline-host-build.log",
            [str(ROOT / "host" / "build.sh"), "--publish", "--out", str(host_out), "--rid", rid],
        )
    if not (host_out / "blt-render-host").is_file():
        raise SystemExit(f"no published host in {host_out} (run without --skip-host)")
    step("Verifying what the host contains")
    run([python, "host/verify_host.py", str(host_out), str(openutau)], cwd=ROOT)
    run(
        [
            python,
            "-I",
            "packaging/verify_absent_data.py",
            str(host_out),
            "--openutau-src",
            str(openutau),
            "--without-g2p-model",
        ],
        cwd=ROOT,
    )
    run_logged(
        evidence / "g2p-host-inventory.log",
        [
            python,
            "-I",
            "packaging/verify_host_inventory_macos.py",
            str(host_out),
            "--g2p-model",
            "excluded",
        ],
    )

    # 2. the Python application ------------------------------------------------------------------
    step("Freezing the application with PyInstaller")
    shutil.rmtree(dist, ignore_errors=True)
    run(
        [python, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(dist),
         "--workpath", str(work), "packaging/blt.spec"],
        cwd=ROOT,
    )  # fmt: skip
    if not app.is_dir():
        raise SystemExit(f"PyInstaller did not make {app}")

    # 3. the host and the notices go in ---------------------------------------------------------
    step("Adding the render host")
    helpers = contents / "Helpers"
    helpers.mkdir(parents=True, exist_ok=True)
    run(["ditto", str(host_out), str(helpers / "host")])
    resources = contents / "Resources"
    resources.mkdir(parents=True, exist_ok=True)
    step(
        "Searching the whole app for the removed data (English plus dictionary, C+V template, other packs)"
    )
    run(
        [
            python,
            "-I",
            "packaging/verify_absent_data.py",
            str(app),
            "--openutau-src",
            str(openutau),
            "--without-g2p-model",
        ],
        cwd=ROOT,
    )
    step("Comparing the packaged host with the reviewed allow-list")
    run_logged(
        evidence / "g2p-host-inventory-packaged.log",
        [
            python,
            "-I",
            "packaging/verify_host_inventory_macos.py",
            str(helpers / "host"),
            "--g2p-model",
            "excluded",
        ],
    )

    step("Writing NOTICES.txt and licenses")
    run(
        [python, "packaging/notices.py", "bundle", "--platform", "macos", "--out", str(resources),
         "--nuget", str(nuget), "--openutau-src", str(openutau)],
        cwd=ROOT,
    )  # fmt: skip

    # 4. the audit -----------------------------------------------------------------------------------
    step(
        "Auditing every file of the app against packaging/components.json and components-macos.json"
    )
    artifacts.mkdir(parents=True, exist_ok=True)
    components = json.loads((ROOT / "packaging" / "components.json").read_text(encoding="utf-8"))
    runtime_version = next(
        c["version"].split(" ")[0] for c in components["components"] if c["id"] == "dotnet-runtime"
    )
    pack = nuget / f"microsoft.netcore.app.runtime.{rid}" / runtime_version / "runtimes" / rid
    inventory = artifacts / f"inventory-{suffix}.json"
    audit = [
        python, "packaging/inventory.py", str(app), "--platform", "macos", "--runtime-pack", str(pack),
        "--deps-json", str(host_out / "blt-render-host.deps.json"), "--out", str(inventory),
    ]  # fmt: skip
    if args.fail_on_blockers:
        audit.append("--fail-on-blockers")
    try:
        run(audit, cwd=ROOT)
    except SystemExit:
        if not args.allow_audit_gaps:
            raise
        print("(--allow-audit-gaps: going on)")
    overlay = json.loads((ROOT / "packaging" / "components-macos.json").read_text(encoding="utf-8"))
    blockers = [
        c["id"]
        for c in release_gate_components(components, overlay)
        if c.get("status") == "blocker"
    ]

    # 5. signing, off by default -----------------------------------------------------------------------
    if args.sign_identity:
        step("Signing (--sign-identity; not part of the project's builds)")
        sign_app(app, args.sign_identity)

    # 6. smoke tests --------------------------------------------------------------------------------
    if not args.no_smoke:
        step("Smoke-testing the app")
        run([python, "packaging/smoke_macos.py", "--app", str(app)], cwd=ROOT)
        step("Checking that the Qt libraries are replaceable (LGPL)")
        run_logged(
            evidence / "qt-replaceability-test.log",
            [python, "packaging/replaceability_macos.py", "--app", str(app)],
        )

    # 7. the disk image ------------------------------------------------------------------------------
    dmg = None
    if not args.no_dmg:
        step("Building the disk image")
        stage = work / "dmg-stage"
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        run(["ditto", str(app), str(stage / APP_NAME)])
        (stage / "Applications").symlink_to("/Applications")
        (stage / "READ ME FIRST.txt").write_text(README_FIRST, encoding="utf-8")
        dmg = artifacts / f"BLT-Music-Generator-{number}-{suffix}.dmg"
        dmg.unlink(missing_ok=True)
        run(
            [
                "hdiutil",
                "create",
                "-volname",
                VOLUME,
                "-srcfolder",
                str(stage),
                "-ov",
                "-format",
                "UDZO",
                str(dmg),
            ]
        )
        if args.sign_identity:
            run(["codesign", "--force", "--timestamp", "--sign", args.sign_identity, str(dmg)])
        if args.notarize:
            step("Notarising (--notarize; not part of the project's builds)")
            notarize(dmg, args.notarize)

    # 8. checksums and release metadata ------------------------------------------------------------
    step("Checksums and metadata")
    shutil.copyfile(resources / "NOTICES.txt", artifacts / f"NOTICES-{suffix}.txt")
    status = (
        f"NOT FOR RELEASE: {len(blockers)} open licensing blocker(s): {', '.join(blockers)}. See docs/dependency-audit.md."
        if blockers
        else "No open licensing blockers recorded."
    )
    (artifacts / f"RELEASE-STATUS-{suffix}.txt").write_text(status, encoding="utf-8")
    host_build = json.loads((host_out / "blt-host-build.json").read_text(encoding="utf-8"))
    shutil.copyfile(host_out / "blt-host-build.json", artifacts / f"blt-host-build-{suffix}.json")
    info = {
        "product": "BLT Music Generator",
        "platform": "macos",
        "architecture": arch,
        "macos_build_machine": platform.mac_ver()[0],
        "version": number,
        "commit": commit,
        "uncommitted_changes": dirty,
        "worldline_spline_free": bool(host_build["worldline_spline_free"]),
        "worldline_sha256": host_build["worldline_sha256"],
        "g2p_model": host_build["g2p_model"],
        "distribution": host_build["distribution"],
        "openutau": "0.1.565 a60ca5830b9064556157245d4bf8f5920d93e5f8",
        "dotnet_runtime": runtime_version,
        "python": platform.python_version(),
        "pyinstaller": subprocess.run(
            [python, "-m", "PyInstaller", "--version"], capture_output=True, text=True, check=True
        ).stdout.strip(),
        "disk_image": dmg.name if dmg else None,
        "disk_image_bytes": dmg.stat().st_size if dmg else None,
        "signed": bool(args.sign_identity),
        "notarized": bool(args.notarize),
        "tested_on_a_real_mac": False,
        "release_blockers": blockers,
        "status": status,
    }
    (artifacts / f"release-info-{suffix}.json").write_text(
        json.dumps(info, indent=2) + "\n", encoding="utf-8"
    )
    sums = [
        f"{sha256(f)} *{f.name}"
        for f in (dmg, artifacts / f"NOTICES-{suffix}.txt", inventory)
        if f is not None and f.is_file()
    ]
    (artifacts / f"SHA256SUMS-{suffix}.txt").write_text("\n".join(sums) + "\n", encoding="ascii")
    print("\n".join(sums))
    gate_text = subprocess.run(
        [python, "packaging/release_gate.py", "status"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    (artifacts / f"release-gate-status-{suffix}.txt").write_text(gate_text, encoding="utf-8")
    if args.for_release:
        step("Checking the finished build against the release gate")
        problems = release_gate.macos_package_problems(artifacts)
        if problems:
            raise SystemExit("not releasable: " + "; ".join(problems))
    print(f"\n{gate_text}\n{status}\nApp:        {app}")
    if dmg:
        print(
            f"Disk image: {dmg} ({dmg.stat().st_size / 1e6:.1f} MB, "
            + ("signed" if args.sign_identity else "unsigned")
            + ")"
        )
    return 0


def release_gate_components(
    components: dict[str, Any], overlay: dict[str, Any]
) -> list[dict[str, Any]]:
    """The macOS component table (the audit's own merge, so the build and the audit agree)."""
    import inventory

    merged = inventory.apply_overlay(components, overlay)
    result: list[dict[str, Any]] = merged["components"]
    return result


if __name__ == "__main__":
    sys.exit(main())
