"""Assemble the independent-review packets for human reviewers.

    python packaging/review_packets.py --out DIR [--package APP_DIR] [--compliance DIR] [--evidence DIR]
        [--openutau-src DIR] [--inventory FILE] [--host-build FILE]

``DIR`` receives one folder per packet: ``checklist/`` (the reviewer's one page), ``qt/``, ``source-history/``,
``g2p-model/``, ``ai-authorship/``, ``native-dependencies/`` and ``worldline/`` (the closing record of the retired
spline item), each each with the narrative (``README.md``, from
``docs/review``), every file the reviewer needs, a ``MANIFEST.json`` with SHA-256 of everything, and the
evidence logs named by ``--evidence``. Nothing is uploaded and nothing is signed: the packet is the
material, the sign-off is a person's (``docs/release-gate.md``).

* ``--package`` the built package folder (``research-output/release/app/BLT Music Generator``): the Qt and
  PySide6 files in it are listed with their hashes and compared with the hashes in the wheels' own RECORD
  files, which shows they are unmodified.
* ``--compliance`` the output of ``packaging/compliance.py`` (written offer, relinking text, checksums).
* ``--evidence`` a folder of logs (build, replaceability test, ...); copied with their hashes.
* ``--openutau-src`` the pinned OpenUtau checkout: the g2p model is read from it (``inspect_onnx.py``).
* ``--inventory`` the build's ``inventory.json`` (every file of the package mapped to a component).
* ``--host-build`` the host's ``blt-host-build.json`` (which native library, whether the g2p model is in).

The tk::spline source is deliberately **not** in the worldline packet: the reviewer gets it from upstream.
"""

import argparse
import base64
import hashlib
import importlib.metadata
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

WORLDLINE_FILES = (
    "docs/worldline-provenance.md",
    "host/native/effects-no-tension-spline.patch",
    "host/native/CMakeLists.txt",
    "host/native/prepare.py",
    "host/native/build.ps1",
    "host/native/verify_dll.py",
    "host/native/tests/tension_test.cpp",
    "host/native/trace_tension.ps1",
    "host/verify-host.ps1",
    "tests/golden/selftest_audio.json",
    "tests/integration/test_selftest_e2e.py",
)
QT_FILES = (
    "packaging/qt-statement.txt",
    "packaging/compliance.py",
    "packaging/replaceability-test.ps1",
    "packaging/licenses/LGPL-3.0-only.txt",
    "packaging/licenses/GPL-3.0-only.txt",
    "packaging/requirements-build.txt",
    "src/barbershop_tracks/ui/main_window.py",
)
QT_DISTRIBUTIONS = ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6")
G2P_FILES = (
    "docs/g2p-model-provenance.md",
    "docs/g2p-plus-provenance.md",
    "docs/upstream-g2p-plus-issue.md",
    "docs/upstream/g2p-inquiry-title.txt",
    "docs/upstream/g2p-inquiry-body.md",
    "compliance/host-inventory.json",
    "packaging/verify_host_inventory.py",
    "packaging/verify_absent_data.py",
    "host/patch_openutau.py",
    "host/verify-host.ps1",
    "scripts/research/inspect_onnx.py",
    "scripts/research/eval_g2p_model.py",
    "packaging/licenses/upstream_CMUdict_0.07_licence.txt",
)
HISTORY_FILES = (
    "docs/review/worldline-spline-review-packet.md",
    "docs/review/evidence/spline-text-comparison.txt",
    "docs/worldline-provenance.md",
    "host/native/effects-no-tension-spline.patch",
    "host/native/verify_dll.py",
    "scripts/research/compare_source_text.py",
)
HISTORY_PATHS = (
    "host/native/patched/natural_spline.h",
    "host/native/effects-natural-spline.patch",
    "host/native/parity",
)
LAST_COMMIT_WITH_THE_FILE = "b4b99bb"
NATIVE_FILES = (
    "packaging/components.json",
    "packaging/inventory.py",
    "packaging/notices.py",
    "packaging/verify_absent_data.py",
    "packaging/verify_host_inventory.py",
    "host/native/verify_dll.py",
    "docs/worldline-provenance.md",
    "docs/dependency-audit.md",
)
NATIVE_SUFFIXES = (".dll", ".pyd", ".exe")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_into(target: Path, source: Path, name: str, manifest: dict[str, str]) -> None:
    destination = target / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    manifest[name] = sha256_of(destination)


def record_hashes() -> dict[str, tuple[str, str]]:
    """Wheel-relative path -> (distribution, sha256 hex) from the installed wheels' RECORD files."""
    result: dict[str, tuple[str, str]] = {}
    for name in QT_DISTRIBUTIONS:
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        for entry in dist.files or []:
            if entry.hash is None or entry.hash.mode != "sha256":
                continue
            padded = entry.hash.value + "=" * (-len(entry.hash.value) % 4)
            result[entry.as_posix()] = (name, base64.urlsafe_b64decode(padded).hex())
    return result


def qt_files_in_package(package: Path) -> list[dict[str, Any]]:
    """Every file of the package below PySide6 and shiboken6, with its hash and the wheel's hash."""
    record = record_hashes()
    rows: list[dict[str, Any]] = []
    for top in ("PySide6", "shiboken6"):
        for file in sorted((package / "_internal" / top).rglob("*")):
            if not file.is_file():
                continue
            relative = file.relative_to(package / "_internal").as_posix()
            digest = sha256_of(file)
            wheel = record.get(relative)
            rows.append(
                {
                    "path": f"_internal/{relative}",
                    "bytes": file.stat().st_size,
                    "sha256": digest,
                    "wheel": wheel[0] if wheel else None,
                    "wheel_record_sha256": wheel[1] if wheel else None,
                    "identical_to_wheel": bool(wheel and wheel[1] == digest),
                }
            )
    return rows


def versions() -> dict[str, str]:
    found: dict[str, str] = {}
    for name in QT_DISTRIBUTIONS:
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        found[name] = f"{dist.version} ({dist.metadata.get('License')})"
    return found


def wheel_metadata() -> dict[str, Any]:
    """Licence-relevant metadata and licence files of the installed Qt for Python wheels."""
    result: dict[str, Any] = {}
    for name in QT_DISTRIBUTIONS:
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        md = dist.metadata
        licence_files = []
        for entry in dist.files or []:
            low = entry.name.lower()
            if any(word in low for word in ("licen", "copying", "notice")):
                located = Path(str(dist.locate_file(entry)))
                if located.is_file():
                    licence_files.append(
                        {
                            "path": entry.as_posix(),
                            "bytes": located.stat().st_size,
                            "sha256": sha256_of(located),
                        }
                    )
        result[name] = {
            "version": dist.version,
            "license_field": md.get("License"),
            "license_expression": md.get("License-Expression"),
            "license_classifiers": [c for c in (md.get_all("Classifier") or []) if "License" in c],
            "author": md.get("Author") or md.get("Author-email"),
            "home_page": md.get("Home-page") or md.get("Project-URL"),
            "licence_files_in_the_wheel": licence_files,
        }
    return result


def runtime_versions() -> dict[str, str]:
    """What the loaded libraries say about themselves (nothing about commits: Qt does not embed them)."""
    import PySide6
    import shiboken6
    from PySide6 import QtCore

    return {
        "PySide6.__version__": str(PySide6.__version__),
        "shiboken6.__version__": str(shiboken6.__version__),
        "QtCore.qVersion()": str(QtCore.qVersion()),
        "QLibraryInfo.build()": str(QtCore.QLibraryInfo.build()),
    }


def attribution_index() -> list[dict[str, Any]]:
    """The Qt third-party attribution files BLT ships (verbatim from qtbase v6.11.2), with hashes."""
    root = REPO / "packaging" / "licenses" / "qt-6.11.2"
    return [
        {"path": f.relative_to(root).as_posix(), "bytes": f.stat().st_size, "sha256": sha256_of(f)}
        for f in sorted(root.rglob("*"))
        if f.is_file()
    ]


def write_json(out: Path, name: str, data: Any, manifest: dict[str, str]) -> None:
    path = out / "evidence" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1) + chr(10), encoding="utf-8")
    manifest[f"evidence/{name}"] = sha256_of(path)


def zip_packet(folder: Path, target: Path) -> None:
    """One file per packet, byte-for-byte reproducible from the folder (sorted, fixed timestamps)."""
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(p for p in folder.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(file.relative_to(folder).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, file.read_bytes())


def build_worldline(out: Path, evidence: Path | None) -> dict[str, str]:
    manifest: dict[str, str] = {}
    copy_into(out, REPO / "docs/review/worldline-spline-review-packet.md", "README.md", manifest)
    for name in WORLDLINE_FILES:
        copy_into(out, REPO / name, name, manifest)
    if evidence and evidence.is_dir():
        for log in sorted(evidence.glob("worldline-*.log")):
            copy_into(out, log, f"evidence/{log.name}", manifest)
    return manifest


def build_qt(
    out: Path, package: Path | None, compliance: Path | None, evidence: Path | None
) -> dict[str, str]:
    manifest: dict[str, str] = {}
    copy_into(out, REPO / "docs/review/qt-pyside6-review-packet.md", "README.md", manifest)
    for name in QT_FILES:
        copy_into(out, REPO / name, name, manifest)
    copy_into(out, REPO / "packaging/qt-statement.txt", "evidence/notices-qt-section.txt", manifest)
    write_json(out, "qt-wheel-metadata.json", wheel_metadata(), manifest)
    write_json(out, "qt-runtime-versions.json", runtime_versions(), manifest)
    write_json(out, "qt-attribution-index.json", attribution_index(), manifest)
    if compliance and compliance.is_dir():
        for name in ("WRITTEN-OFFER.txt", "RELINKING.md", "MANIFEST.json", "SHA256SUMS.txt"):
            if (compliance / name).is_file():
                copy_into(out, compliance / name, name, manifest)
    if package and package.is_dir():
        rows = qt_files_in_package(package)
        report = out / "evidence" / "qt-files-in-package.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps({"versions": versions(), "files": rows}, indent=1) + "\n", encoding="utf-8"
        )
        manifest["evidence/qt-files-in-package.json"] = sha256_of(report)
        compare = [r for r in rows if r["wheel"] is not None]
        summary: dict[str, Any] = {
            "files_in_package": len(rows),
            "found_in_a_wheel_record": len(compare),
            "identical_to_the_wheel": sum(1 for r in compare if r["identical_to_wheel"]),
            "differing": [r["path"] for r in compare if not r["identical_to_wheel"]],
            "not_in_any_wheel_record": [r["path"] for r in rows if r["wheel"] is None],
        }
        summary_path = out / "evidence" / "qt-files-vs-wheel-record.json"
        summary_path.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
        manifest["evidence/qt-files-vs-wheel-record.json"] = sha256_of(summary_path)
        print(
            f"qt: {summary['identical_to_the_wheel']} of {summary['files_in_package']} package files "
            f"identical to their wheel RECORD hash; differing {summary['differing']}; "
            f"not in a RECORD {len(summary['not_in_any_wheel_record'])}"
        )
    if evidence and evidence.is_dir():
        for log in sorted(evidence.glob("qt-*.log")):
            copy_into(out, log, f"evidence/{log.name}", manifest)
    return manifest


def git(*arguments: str) -> str | None:
    """Output of a git command in the repository, or None when git or the history is not there."""
    try:
        done = subprocess.run(
            ["git", *arguments], cwd=REPO, capture_output=True, text=True, check=False, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def write_text(out: Path, name: str, text: str, manifest: dict[str, str]) -> None:
    path = out / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    manifest[name] = sha256_of(path)


def build_checklist(out: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    copy_into(out, REPO / "docs/review/INDEPENDENT-REVIEWER-CHECKLIST.md", "README.md", manifest)
    copy_into(out, REPO / "docs/release-gate.md", "docs/release-gate.md", manifest)
    copy_into(out, REPO / "compliance/release-gate.json", "compliance/release-gate.json", manifest)
    return manifest


def build_history(out: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    copy_into(out, REPO / "docs/review/source-history-review-packet.md", "README.md", manifest)
    for name in HISTORY_FILES:
        copy_into(out, REPO / name, name, manifest)
    log = git("log", "--all", "--format=%H %cI %an %s", "--", *HISTORY_PATHS)
    note = "git history is not available in this checkout (a shallow clone?); run the command on a full clone"
    write_text(
        out,
        "evidence/git-history-of-the-replacement.txt",
        "git log --all --format='%H %cI %an %s' -- "
        + " ".join(HISTORY_PATHS)
        + "\n\n"
        + (log or note)
        + "\n",
        manifest,
    )
    old = git("show", f"{LAST_COMMIT_WITH_THE_FILE}:host/native/patched/natural_spline.h")
    if old is not None:
        write_text(
            out, f"evidence/natural_spline.h.at-{LAST_COMMIT_WITH_THE_FILE}.txt", old, manifest
        )
    return manifest


def build_g2p(
    out: Path, openutau_src: Path | None, host_build: Path | None, evidence: Path | None
) -> dict[str, str]:
    manifest: dict[str, str] = {}
    copy_into(out, REPO / "docs/g2p-model-provenance.md", "README.md", manifest)
    for name in G2P_FILES:
        copy_into(out, REPO / name, name, manifest)
    if openutau_src is not None:
        pack = openutau_src / "OpenUtau.Core" / "G2p" / "Data" / "g2p-arpabet.zip"
        if pack.is_file():
            spec = importlib.util.spec_from_file_location(
                "inspect_onnx", REPO / "scripts" / "research" / "inspect_onnx.py"
            )
            assert spec is not None
            assert spec.loader is not None
            inspect_onnx = importlib.util.module_from_spec(spec)
            sys.modules["inspect_onnx"] = (
                inspect_onnx  # dataclass-free, but keeps tracebacks readable
            )
            spec.loader.exec_module(inspect_onnx)

            with zipfile.ZipFile(pack) as archive, tempfile.TemporaryDirectory() as scratch:
                target = Path(scratch) / "g2p.onnx"
                target.write_bytes(archive.read("g2p.onnx"))
                report = inspect_onnx.inspect(target)
                members = {i.filename: i.file_size for i in archive.infolist()}
            report["pack_members"] = members
            report["pack_sha256"] = sha256_of(pack)
            write_json(out, "g2p-onnx-report.json", report, manifest)
    if host_build is not None and host_build.is_file():
        copy_into(out, host_build, "evidence/blt-host-build.json", manifest)
    if evidence and evidence.is_dir():
        for log in sorted(evidence.glob("g2p-*.log")):
            copy_into(out, log, f"evidence/{log.name}", manifest)
    return manifest


def build_authorship(out: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    copy_into(out, REPO / "docs/review/ai-authorship-review-packet.md", "README.md", manifest)
    copy_into(
        out, REPO / "docs/review/evidence/spline-text-comparison.txt",
        "evidence/spline-text-comparison.txt", manifest,
    )  # fmt: skip
    copy_into(
        out,
        REPO / "scripts/research/compare_source_text.py",
        "scripts/compare_source_text.py",
        manifest,
    )
    listing = git("ls-files")
    if listing is not None:
        sizes: dict[str, list[int]] = {}
        for name in listing.splitlines():
            file = REPO / name
            if not file.is_file() or file.suffix.lower() not in {
                ".py", ".cs", ".cpp", ".h", ".ps1", ".iss", ".md", ".yml", ".json", ".txt", ".patch",
            }:  # fmt: skip
                continue
            top = name.split("/", 1)[0] if "/" in name else "(root)"
            lines = sum(1 for _ in file.open(encoding="utf-8", errors="replace"))
            entry = sizes.setdefault(top, [0, 0])
            entry[0] += 1
            entry[1] += lines
        write_json(
            out, "size-by-directory.json",
            {k: {"files": v[0], "lines": v[1]} for k, v in sorted(sizes.items())}, manifest,
        )  # fmt: skip
    authors = git("log", "--format=%an")
    if authors is not None:
        counts: dict[str, int] = {}
        for name in authors.splitlines():
            counts[name] = counts.get(name, 0) + 1
        write_json(out, "commit-authors.json", counts, manifest)
    return manifest


def build_native(out: Path, package: Path | None, inventory: Path | None) -> dict[str, str]:
    manifest: dict[str, str] = {}
    copy_into(out, REPO / "docs/review/native-dependencies-review-packet.md", "README.md", manifest)
    for name in NATIVE_FILES:
        copy_into(out, REPO / name, name, manifest)
    if inventory is not None and inventory.is_file():
        copy_into(out, inventory, "evidence/inventory.json", manifest)
        files = json.loads(inventory.read_text(encoding="utf-8"))["files"]
        native = [f for f in files if str(f["path"]).lower().endswith(NATIVE_SUFFIXES)]
        write_json(out, "native-binaries.json", native, manifest)
    if package is not None and package.is_dir():
        present = sorted(
            p.relative_to(package).as_posix()
            for p in package.rglob("*")
            if p.is_file() and p.suffix.lower() in NATIVE_SUFFIXES
        )
        write_json(out, "native-files-in-package.json", present, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--compliance", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--openutau-src", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--host-build", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)
    packets = {
        "checklist": build_checklist(args.out / "checklist"),
        "qt": build_qt(args.out / "qt", args.package, args.compliance, args.evidence),
        "source-history": build_history(args.out / "source-history"),
        "g2p-model": build_g2p(
            args.out / "g2p-model", args.openutau_src, args.host_build, args.evidence
        ),
        "ai-authorship": build_authorship(args.out / "ai-authorship"),
        "native-dependencies": build_native(
            args.out / "native-dependencies", args.package, args.inventory
        ),
        "worldline": build_worldline(args.out / "worldline", args.evidence),
    }
    for name, manifest in packets.items():
        (args.out / name / "MANIFEST.json").write_text(
            json.dumps(
                {"schema": "blt.review-packet/1", "packet": name, "files": manifest}, indent=1
            )
            + "\n",
            encoding="utf-8",
        )
        archive = args.out / f"{name}-review-packet.zip"
        zip_packet(args.out / name, archive)
        print(
            f"{name}: {len(manifest)} files -> {args.out / name} ; one file: {archive.name} ({sha256_of(archive)[:16]}...)"
        )
    print("not signed, not uploaded: a person signs, with packaging/release_gate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
