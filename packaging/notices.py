"""Generate the distributable licence notices and the generated part of docs/dependency-audit.md.

    python packaging/notices.py bundle --out DIST [--openutau-src DIR] [--nuget DIR]
    python packaging/notices.py audit [--check]

``bundle`` writes ``NOTICES.txt`` and ``licenses/`` into the package: every licence text is copied
verbatim from the package that was audited (site-packages, the NuGet cache, the OpenUtau checkout)
or from the SPDX text kept in ``packaging/licenses``. A text that cannot be found is an error, not
a silent omission. ``audit`` regenerates the tables in ``docs/dependency-audit.md`` from
``components.json``; ``--check`` fails if the file is out of date (used by CI).
"""

import argparse
import importlib.metadata
import os
import platform
import shutil
import site
import sys
from pathlib import Path
from typing import Any

from inventory import load_components, load_components_data

REPO = Path(__file__).resolve().parents[1]
LICENSES = Path(__file__).with_name("licenses")
AUDIT = REPO / "docs" / "dependency-audit.md"
BEGIN = "<!-- BEGIN GENERATED: python packaging/notices.py audit -->"
END = "<!-- END GENERATED -->"
RULE = "=" * 78

PRODUCT = "BLT Music Generator"

# the text sits in its own file so that a licence reviewer's sign-off can name its exact bytes
QT_STATEMENT = (Path(__file__).with_name("qt-statement.txt")).read_text(encoding="utf-8")
QT_STATEMENT_MACOS = (Path(__file__).with_name("qt-statement-macos.txt")).read_text(
    encoding="utf-8"
)

OPENUTAU_STATEMENT = """\
OpenUtau.Core (MIT; modified build)
-----------------------------------
The render host contains OpenUtau.Core.dll and OpenUtau.Plugin.Builtin.dll built from OpenUtau
release 0.1.565 (commit a60ca5830b9064556157245d4bf8f5920d93e5f8, MIT licence), MODIFIED by this
project: the OpenUtau.Core.Voicevox classes (which derive from the LGPL-3.0 VOICEVOX engine), the
Vogen data files, the non-English dictionaries and the English "plus" dictionary (with the
phonemizers that need it) are deleted, so no VOICEVOX code is distributed.
host\\patch_openutau.py makes the change; the revision the host reports ends in "+blt-patched".
The native worldline.dll is built by this project from the pinned World / libpyin / libgvps sources
without the tension effect, the only part that used the GPL-licensed tk::spline library; no spline
code of any kind is in it (host\\native).
The English dictionary (CMUdict 0.7b, Carnegie Mellon University licence, shipped in
licenses\\) comes with a small neural model that guesses the pronunciation of words the
dictionary lacks. The model was made by the OpenUtau project; its training data and licence
are not documented by its authors (this project's record: docs\\g2p-model-provenance.md).
Whether a build contains it is stated in host\\blt-host-build.json (g2p_model); a build
without it also lacks the native onnxruntime.dll, which exists only to run it.
Source:
  OpenUtau:         https://github.com/stakira/OpenUtau/tree/a60ca5830b9064556157245d4bf8f5920d93e5f8
  The changes:      the project source (host\\), included in the corresponding-source bundle.
"""

PYINSTALLER_STATEMENT = """\
PyInstaller bootloader (GPL-2.0-or-later with the bootloader exception)
------------------------------------------------------------------------
The two executables start from a PyInstaller bootloader. PyInstaller's licence contains an exception
that permits distributing a program built with it under terms of its own choosing; the full text is
in licenses\\third-party\\pyinstaller\\COPYING.txt.
"""


def roots(openutau_src: Path | None, nuget: Path | None) -> dict[str, Path]:
    """Where the audited packages live on this machine."""
    located = importlib.metadata.distribution("numpy").locate_file("")
    sites = [Path(str(located))] + [Path(p) for p in site.getsitepackages()]
    openutau = (
        openutau_src
        or next(
            (
                REPO / "research-output" / name / "OpenUtau.sln"
                for name in ("openutau-src", "spike/OpenUtau-src")
                if (REPO / "research-output" / name / "OpenUtau.sln").is_file()
            ),
            REPO / "research-output" / "openutau-src" / "OpenUtau.sln",
        ).parent
    )
    cache = nuget or Path(os.environ.get("NUGET_PACKAGES") or Path.home() / ".nuget" / "packages")
    return {
        "python": Path(sys.base_prefix),
        "site": sites[0],
        "nuget": cache,
        "openutau": openutau,
        # the .NET runtime pack of this Mac (a Path only so that the table of places stays one type)
        "rid": Path({"arm64": "osx-arm64", "x86_64": "osx-x64"}.get(platform.machine(), "osx-x64")),
    }


def resolve(template: str, where: dict[str, Path]) -> Path:
    for key, value in where.items():
        template = template.replace("{" + key + "}", str(value))
    path = Path(template)
    return path if path.is_absolute() else REPO / path


def spdx_text(identifier: str) -> str:
    return (LICENSES / f"{identifier}.txt").read_text(encoding="utf-8").rstrip() + "\n"


def for_macos(text: str) -> str:
    """The Windows wording of a statement with macOS names (paths with slashes, the .dylib)."""
    backslash = chr(92)
    return (
        text.replace(backslash * 2, "/")
        .replace(backslash, "/")
        .replace("worldline.dll", "libworldline.dylib")
    )


def bundle(out: Path, where: dict[str, Path], platform: str = "windows") -> list[str]:
    """Write NOTICES.txt and licenses/ into ``out``; returns the problems (missing texts)."""
    macos = platform == "macos"
    data = load_components_full(platform)
    components = data["components"]
    sep = "/" if macos else chr(92)
    problems: list[str] = []
    third = out / "licenses" / "third-party"
    spdx_used: list[str] = []
    for component in components:
        for identifier in component["texts"]:
            if identifier not in spdx_used:
                spdx_used.append(identifier)
        for extra in component["extra_texts"]:
            source = resolve(extra["path"], where)
            if not source.exists():
                problems.append(f"{component['id']}: missing licence text {source}")
                continue
            target_dir = third / component["id"]
            target_dir.mkdir(parents=True, exist_ok=True)
            if extra.get("tree"):
                for file in sorted(f for f in source.rglob("*") if f.is_file()):
                    destination = target_dir / file.relative_to(source)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(file, destination)
            else:
                shutil.copyfile(source, target_dir / source.name)
    inno = data["installer"][0] if data["installer"] else None
    spdx_dir = out / "licenses"
    spdx_dir.mkdir(parents=True, exist_ok=True)
    for identifier in ("LGPL-3.0-only", "GPL-3.0-only", *spdx_used):
        if (LICENSES / f"{identifier}.txt").is_file():
            shutil.copyfile(LICENSES / f"{identifier}.txt", spdx_dir / f"{identifier}.txt")
        else:
            problems.append(f"missing SPDX text packaging/licenses/{identifier}.txt")
    lines = [
        RULE,
        f"{PRODUCT}: third-party notices",
        RULE,
        "",
        f"{PRODUCT}, Copyright 2026 Joseph Driedger, is licensed under the Apache License 2.0",
        "(LICENSE.txt; the NOTICE file is installed beside it).",
        "It includes the third-party software listed below, each under its own licence. The",
        "licence texts are in the 'licenses' folder next to this file; per-component texts that",
        f"were copied from the original packages are in licenses{sep}third-party{sep}<component>{sep}.",
        "",
        "No voicebank and no FFmpeg are included. Voicebanks are installed by the user under their",
        "own licences; MP3 output uses an FFmpeg the user installs.",
        "",
        QT_STATEMENT_MACOS if macos else QT_STATEMENT,
        for_macos(OPENUTAU_STATEMENT) if macos else OPENUTAU_STATEMENT,
        for_macos(PYINSTALLER_STATEMENT) if macos else PYINSTALLER_STATEMENT,
        RULE,
        "Components",
        RULE,
        "",
    ]
    for component in components:
        lines.append(f"{component['name']}  {component['version']}")
        lines.append(f"    Licence:   {component['license']}")
        lines.append(f"    Copyright: {component['copyright']}")
        lines.append(f"    Source:    {component['source']}")
        folder = third / component["id"]
        if component["extra_texts"] and folder.is_dir():
            lines.append(f"    Texts:     licenses{sep}third-party{sep}{component['id']}{sep}")
        if component["texts"]:
            lines.append(
                "    See:       " + ", ".join(f"licenses{sep}{t}.txt" for t in component["texts"])
            )
        lines.append("")
    if inno is not None:
        lines += [
            f"{inno['name']}  (installer only)",
            f"    Licence:   {inno['license']}",
            f"    Copyright: {inno['copyright']}",
            "",
        ]
    lines += [RULE, "Licence texts", RULE]
    for identifier in spdx_used:
        lines += ["", f"--- {identifier} ---", "", spdx_text(identifier)]
    if inno is not None:
        lines += [
            "",
            "--- Inno Setup License ---",
            "",
            (REPO / inno["text"]).read_text(encoding="utf-8").rstrip(),
            "",
        ]
    (out / "NOTICES.txt").write_text("\n".join(lines), encoding="utf-8")
    shutil.copyfile(LICENSES / "Apache-2.0.txt", out / "licenses" / "Apache-2.0.txt")
    shutil.copyfile(REPO / "LICENSE", out / "LICENSE.txt")
    shutil.copyfile(REPO / "NOTICE", out / "NOTICE")
    if inno is not None:
        shutil.copyfile(LICENSES / "upstream_InnoSetup.txt", out / "licenses" / "InnoSetup.txt")
    return problems


def load_components_full(platform: str = "windows") -> dict[str, Any]:
    return load_components_data(platform)


def md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def audit_region() -> str:
    data = load_components_full()
    components = load_components()
    blockers = [c for c in components if c["status"] == "blocker"]
    out = [BEGIN, ""]
    out.append(
        f"{len(components)} components are shipped in the package; **{len(blockers)} are release "
        "blockers** (unverified or conflicting licence obligations). A person must resolve each "
        "one before a public release; this table is regenerated from `packaging/components.json`."
    )
    out += [
        "",
        "### Release blockers",
        "",
        "| Component | Version | Licence | What is unresolved |",
        "|---|---|---|---|",
    ]
    for c in blockers:
        out.append(
            f"| {md_cell(c['name'])} | {md_cell(c['version'])} | {md_cell(c['license'])} | "
            f"{md_cell(c['obligations'] + ' ' + c['notes'])} |"
        )
    out += ["", "### Shipped components", ""]
    out += [
        "| Component | Version | Licence | Copyright holder | Status |",
        "|---|---|---|---|---|",
    ]
    for c in components:
        status = "**blocker**" if c["status"] == "blocker" else "ok"
        out.append(
            f"| {md_cell(c['name'])} | {md_cell(c['version'])} | {md_cell(c['license'])} | "
            f"{md_cell(c['copyright'])} | {status} |"
        )
    out += ["", "### Obligations and sources", ""]
    out += ["| Component | Source | Obligations / notes |", "|---|---|---|"]
    for c in components:
        note = (c["obligations"] + " " + c["notes"]).strip()
        out.append(f"| {md_cell(c['name'])} | {md_cell(c['source'])} | {md_cell(note)} |")
    out += ["", "### Deliberately not shipped", ""]
    out += ["| Item | Licence | Why | How it is excluded |", "|---|---|---|---|"]
    for e in data["excluded"]:
        out.append(
            "| " + " | ".join(md_cell(e[k]) for k in ("name", "license", "why", "how")) + " |"
        )
    out += ["", "### External, user-supplied or build-time", ""]
    out += ["| Item | Licence | Decision | Reason |", "|---|---|---|---|"]
    for e in data["external"]:
        out.append(
            "| "
            + " | ".join(md_cell(e[k]) for k in ("name", "license", "decision", "reason"))
            + " |"
        )
    out += ["", "### Inside the installer only", ""]
    for e in data["installer"]:
        out.append(f"- **{e['name']}**: {e['license']}. {e['copyright']}. {e['obligation']}")
    out += ["", END]
    return "\n".join(out)


def update_audit(check: bool) -> int:
    text = AUDIT.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        print(f"{AUDIT}: generated-region markers are missing", file=sys.stderr)
        return 1
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    updated = head + audit_region() + tail
    if check:
        if updated != text:
            print(
                "docs/dependency-audit.md is out of date: run python packaging/notices.py audit",
                file=sys.stderr,
            )
            return 1
        return 0
    AUDIT.write_text(updated, encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    bundle_cmd = commands.add_parser(
        "bundle", help="write NOTICES.txt and licenses/ into a package folder"
    )
    bundle_cmd.add_argument("--out", type=Path, required=True)
    bundle_cmd.add_argument("--platform", choices=("windows", "macos"), default="windows")
    bundle_cmd.add_argument("--openutau-src", type=Path)
    bundle_cmd.add_argument("--nuget", type=Path)
    audit_cmd = commands.add_parser(
        "audit", help="regenerate the tables in docs/dependency-audit.md"
    )
    audit_cmd.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "audit":
        return update_audit(args.check)
    problems = bundle(args.out, roots(args.openutau_src, args.nuget), args.platform)
    for problem in problems:
        print("error:", problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
