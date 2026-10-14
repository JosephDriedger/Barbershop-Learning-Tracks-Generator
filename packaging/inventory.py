"""Classify every file of the built package into an audited component (``components.json``).

The licensing audit is only as good as its coverage, so the build fails when:

* a file in the package belongs to no component (something was added without being audited),
* a component lists files that are not in the package (the table is stale; except a component marked
  ``absent_when_g2p_model_excluded``, which must be absent in a build without the g2p model), or
* an installed Python package / NuGet package version differs from the one that was audited.

    python packaging/inventory.py DIST --runtime-pack DIR [--deps-json FILE] [--out FILE]

Exit status 0: complete. 1: gaps (listed). Blockers are reported but are not gaps: they are the
audit's findings, decided on by a person (``--fail-on-blockers`` turns them into a failure for a
release build).
"""

import argparse
import hashlib
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from typing import Any

Component = dict[str, Any]

COMPONENTS = Path(__file__).with_name("components.json")


def glob_regex(pattern: str) -> re.Pattern[str]:
    """``*`` and ``?`` stay inside one path segment; ``**`` crosses segments."""
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def load_components(path: Path = COMPONENTS) -> list[Component]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "blt.components/1":
        raise SystemExit(f"{path}: unexpected schema {data.get('schema')!r}")
    components: list[Component] = data["components"]
    return components


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_pack_hashes(pack: Path) -> dict[str, str]:
    """name -> sha256 for every file in the .NET runtime pack (runtimes/win-x64/{lib,native})."""
    return {f.name: sha256(f) for f in pack.rglob("*") if f.is_file()}


def classify(
    dist: Path, components: list[Component], runtime_pack: dict[str, str] | None
) -> dict[str, Any]:
    files = sorted(p for p in dist.rglob("*") if p.is_file())
    compiled = [(c["id"], [glob_regex(pat) for pat in c["patterns"]]) for c in components]
    owners: dict[str, str] = {}
    unowned: list[str] = []
    matched: dict[str, int] = {c["id"]: 0 for c in components}
    runtime_component = next((c["id"] for c in components if c.get("match_runtime_pack")), None)
    for path in files:
        rel = path.relative_to(dist).as_posix()
        owner = None
        if runtime_pack is not None and runtime_component and rel.startswith("host/"):
            name = rel.rsplit("/", 1)[-1]
            if name in runtime_pack and runtime_pack[name] == sha256(path):
                owner = runtime_component
        if owner is None:
            for component_id, expressions in compiled:
                if any(expression.match(rel) for expression in expressions):
                    owner = component_id
                    break
        if owner is None:
            unowned.append(rel)
        else:
            owners[rel] = owner
            matched[owner] += 1
    stale = [c["id"] for c in components if c["patterns"] and not matched[c["id"]]]
    return {"owners": owners, "unowned": unowned, "stale": stale, "files": files}


def version_problems(components: list[Component], deps_json: Path | None) -> list[str]:
    problems = []
    for component in components:
        wanted = component.get("pypi")
        if wanted:
            try:
                have = importlib.metadata.version(wanted)
            except importlib.metadata.PackageNotFoundError:
                problems.append(f"{component['id']}: Python package {wanted} is not installed")
                continue
            if have != component["version"]:
                problems.append(
                    f"{component['id']}: installed {have}, audited {component['version']}"
                )
    if deps_json is not None:
        libraries = json.loads(deps_json.read_text(encoding="utf-8")).get("libraries", {})
        have_nuget = {key.split("/")[0]: key.split("/")[1] for key in libraries if "/" in key}
        for component in components:
            package = component.get("package")
            if package and have_nuget.get(package) != component["version"]:
                problems.append(
                    f"{component['id']}: host has {have_nuget.get(package)}, "
                    f"audited {component['version']}"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("dist", type=Path)
    parser.add_argument(
        "--runtime-pack", type=Path, help="runtimes/win-x64 folder of the .NET runtime pack"
    )
    parser.add_argument("--deps-json", type=Path, help="the host's blt-render-host.deps.json")
    parser.add_argument("--out", type=Path, help="write the per-file inventory (JSON) here")
    parser.add_argument("--fail-on-blockers", action="store_true")
    args = parser.parse_args(argv)

    components = load_components()
    pack = runtime_pack_hashes(args.runtime_pack) if args.runtime_pack else None
    if pack is None and (args.dist / "host").is_dir():
        print(
            "error: --runtime-pack is required to attribute the .NET runtime files", file=sys.stderr
        )
        return 1
    result = classify(args.dist, components, pack)
    problems = version_problems(components, args.deps_json)
    # the model-free build (the default) is recorded in the build; components serving only the model must be gone
    record = args.dist / "host" / "blt-host-build.json"
    excluded = (
        record.is_file()
        and json.loads(record.read_text(encoding="utf-8")).get("g2p_model") == "excluded"
    )
    variant_problems: list[str] = []
    only_for_model = {c["id"] for c in components if c.get("absent_when_g2p_model_excluded")}
    if excluded:
        present = sorted(only_for_model & set(result["owners"].values()))
        for component_id in present:
            variant_problems.append(
                f"{component_id} is in the package, but the g2p model is excluded"
            )
        result["stale"] = [c for c in result["stale"] if c not in only_for_model]

    failed = False
    if result["unowned"]:
        failed = True
        print(f"{len(result['unowned'])} file(s) belong to no audited component:")
        for rel in result["unowned"]:
            print("   ", rel)
    if result["stale"]:
        failed = True
        print(
            "components whose files are not in the package (stale audit entries):",
            ", ".join(result["stale"]),
        )
    if variant_problems:
        failed = True
        print("the build without the g2p model still contains:")
        for line in variant_problems:
            print("   ", line)
    if problems:
        failed = True
        print("version drift since the audit:")
        for line in problems:
            print("   ", line)

    blockers = [c for c in components if c["status"] == "blocker"]
    print(
        f"{len(result['files'])} files in {len(set(result['owners'].values()))} components; "
        f"{len(blockers)} release blocker(s):"
    )
    for component in blockers:
        print(f"    {component['id']}: {component['notes'] or component['obligations']}"[:240])
    if args.out:
        listing = [
            {
                "path": rel,
                "component": result["owners"].get(rel),
                "sha256": sha256(args.dist / rel),
                "bytes": (args.dist / rel).stat().st_size,
            }
            for rel in (p.relative_to(args.dist).as_posix() for p in result["files"])
        ]
        args.out.write_text(
            json.dumps(
                {
                    "schema": "blt.inventory/1",
                    "files": listing,
                    "release_blockers": [c["id"] for c in blockers],
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
    if failed:
        return 1
    return 1 if (args.fail_on_blockers and blockers) else 0


if __name__ == "__main__":
    sys.exit(main())
