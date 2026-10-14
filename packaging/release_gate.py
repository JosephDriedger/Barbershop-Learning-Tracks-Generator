"""The release gate: refuses publication while a required review, acceptance or decision is open.

    python packaging/release_gate.py status
    python packaging/release_gate.py check [--release --package-dir DIR]
    python packaging/release_gate.py sign ITEM --by NAME --role ROLE --evidence PATH [...]

(``sign`` also takes ``--decision VALUE`` for an item that records one.)

The gate's data is ``compliance/release-gate.json``. Every required item needs a recorded human
sign-off that

* names a person (not a bot or CI) and a role, a date and a conclusion of approved;
* is tied to the exact bytes it judged: the SHA-256 of every ``subjects`` file at sign-off time must
  equal the file's hash now, so changing a reviewed file re-opens the item;
* points to evidence that exists (a file in the repository, or an https URL);
* for acceptance items, names the SHA-256 of the installer that was tested, which must be the one
  being released (checked against the build's SHA256SUMS.txt in ``--release`` mode).

* for an item that records a decision of the reviewer (``decision_field`` in the gate file, e.g.
  which variant of the build was approved), carries one of the allowed values; in ``--release``
  mode the build being released must be that variant (``release-info.json`` agrees).

Passing CI is not an input here. The gate reads no test results: a green pipeline and a passing gate
are independent facts, and publication needs both. ``check`` exits 1 on anything open, so any
automation that publishes must run ``check --release`` first and stop on a non-zero exit.
"""

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "compliance" / "release-gate.json"
COMPONENTS = REPO / "packaging" / "components.json"
CONCLUSIONS = ("approved", "approved-with-conditions")
BOT_WORDS = re.compile(
    r"claude|anthropic|\bai\b|\bbot\b|github-actions|\bci\b|copilot|automat", re.I
)
KINDS = ("review", "publication", "acceptance", "decision")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def text_sha256(path: Path) -> str:
    """SHA-256 of a reviewed file, with Windows line endings read as line feeds when it is text.

    A git checkout on Windows may turn LF into CRLF; the same sign-off must hold on any machine.
    """
    data = path.read_bytes()
    if bytes([0]) not in data[:8192]:
        data = data.replace(bytes([13, 10]), bytes([10]))
    return hashlib.sha256(data).hexdigest()


def load_gate(path: Path | None = None) -> dict[str, Any]:
    path = path or GATE
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "blt.release-gate/1":
        raise SystemExit(f"{path}: unknown schema {data.get('schema')!r}")
    return data  # type: ignore[no-any-return]


def subject_hashes(item: dict[str, Any], repo: Path | None = None) -> dict[str, str]:
    root = repo or REPO
    return {name: text_sha256(root / name) for name in item.get("subjects", [])}


def valid_date(text: object) -> bool:
    try:
        datetime.date.fromisoformat(str(text))
    except ValueError:
        return False
    return len(str(text)) == 10


def installer_hash(package_dir: Path) -> str | None:
    sums = package_dir / "SHA256SUMS.txt"
    if not sums.is_file():
        return None
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition(" *")
        if name.endswith("-Setup.exe"):
            return digest.strip().lower()
    return None


def check_item(
    item: dict[str, Any], repo: Path | None = None, package_dir: Path | None = None
) -> list[str]:
    """What is wrong with one required item (empty list: its sign-off stands)."""
    repo = repo or REPO
    signoff = item.get("signoff")
    if not isinstance(signoff, dict):
        return ["no sign-off recorded"]
    problems: list[str] = []
    by = str(signoff.get("by", "")).strip()
    if not by or BOT_WORDS.search(by):
        problems.append(f"sign-off 'by' must name a person, not {by!r}")
    if not str(signoff.get("role", "")).strip():
        problems.append("sign-off has no role")
    if not valid_date(signoff.get("date")):
        problems.append("sign-off date is not YYYY-MM-DD")
    if signoff.get("conclusion") not in CONCLUSIONS:
        problems.append(f"conclusion is {signoff.get('conclusion')!r}, not one of {CONCLUSIONS}")
    elif (
        signoff["conclusion"] == "approved-with-conditions"
        and not str(signoff.get("conditions", "")).strip()
    ):
        problems.append("approved-with-conditions needs the conditions written down")
    field = item.get("decision_field")
    if field and signoff.get(field) not in item.get("decision_values", []):
        problems.append(
            f"the sign-off must state {field} as one of {item.get('decision_values')}, "
            f"not {signoff.get(field)!r}"
        )
    recorded = signoff.get("subjects", {})
    for name, digest in subject_hashes(item, repo).items():
        if recorded.get(name) != digest:
            problems.append(f"{name} changed since the sign-off (or was never covered)")
    evidence = signoff.get("evidence", [])
    if not evidence:
        problems.append("no evidence listed")
    for entry in evidence:
        text = str(entry)
        if text.startswith("https://"):
            continue
        if not (repo / text).is_file():
            problems.append(f"evidence file {text} does not exist")
    if item.get("kind") == "acceptance":
        tested = str(signoff.get("installer_sha256", "")).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", tested):
            problems.append("acceptance sign-off must name the SHA-256 of the installer tested")
        elif package_dir is not None and tested != installer_hash(package_dir):
            problems.append("the installer tested is not the installer being released")
    if item.get("kind") == "publication" and not any(
        str(e).startswith("https://") for e in evidence
    ):
        problems.append("a publication item needs the URL of the published asset as evidence")
    return problems


def component_blockers(components: Path | None = None) -> list[str]:
    data = json.loads((components or COMPONENTS).read_text(encoding="utf-8"))
    return [str(c["id"]) for c in data["components"] if c.get("status") == "blocker"]


def git_head(repo: Path | None = None) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo or REPO, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def package_problems(package_dir: Path, repo: Path | None = None) -> list[str]:
    """Checks on the build that is to be released (only with --release)."""
    problems: list[str] = []
    if not package_dir.is_dir():
        return [f"{package_dir} is not a folder"]
    if installer_hash(package_dir) is None:
        problems.append("no installer with a checksum in SHA256SUMS.txt")
    info_path = package_dir / "release-info.json"
    if not info_path.is_file():
        return [*problems, "release-info.json is missing"]
    info = json.loads(info_path.read_text(encoding="utf-8"))
    if info.get("uncommitted_changes"):
        problems.append("the build was made from a working tree with uncommitted changes")
    if info.get("commit") != git_head(repo):
        problems.append("the build is not of the commit that is checked out")
    if info.get("worldline_spline_free") is not True:
        problems.append("the build does not record that its worldline.dll has no spline in it")
    if info.get("g2p_model") not in ("included", "excluded"):
        problems.append("release-info.json does not say whether the g2p model is in the build")
    if info.get("release_blockers"):
        problems.append(f"the build lists licensing blockers: {info['release_blockers']}")
    return problems


def decision_problems(gate: dict[str, Any], package_dir: Path) -> list[str]:
    """A reviewer who approved one variant of the build has not approved the other."""
    info_path = package_dir / "release-info.json"
    if not info_path.is_file():
        return []
    info = json.loads(info_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for item in gate["items"]:
        field = item.get("decision_field")
        signoff = item.get("signoff")
        if not field or not item.get("required", True) or not isinstance(signoff, dict):
            continue
        if signoff.get(field) != info.get(field):
            problems.append(
                f"{item['id']} was approved for {field}={signoff.get(field)!r}, but this build "
                f"has {field}={info.get(field)!r}"
            )
    return problems


def evaluate(
    gate: dict[str, Any],
    repo: Path | None = None,
    package_dir: Path | None = None,
    components: Path | None = None,
) -> dict[str, list[str]]:
    """Everything open, keyed by item id (empty dict: the gate is open to publication)."""
    open_items: dict[str, list[str]] = {}
    for item in gate["items"]:
        if not item.get("required", True):
            continue
        problems = check_item(item, repo, package_dir)
        if problems:
            open_items[str(item["id"])] = problems
    blockers = component_blockers(components)
    if blockers:
        open_items["components.json"] = [f"components with status blocker: {', '.join(blockers)}"]
    if package_dir is not None:
        problems = package_problems(package_dir, repo)
        problems += decision_problems(gate, package_dir)
        if problems:
            open_items["package"] = problems
    return open_items


def print_status(gate: dict[str, Any], open_items: dict[str, list[str]]) -> None:
    for item in gate["items"]:
        mark = "ok  " if item["id"] not in open_items else "OPEN"
        required = "" if item.get("required", True) else " (not required)"
        print(f"  {mark} {item['id']:<32} [{item['kind']}] {item['title']}{required}")
        for problem in open_items.get(str(item["id"]), []):
            print(f"         - {problem}")
    for extra in ("components.json", "package"):
        if extra in open_items:
            print(f"  OPEN {extra}")
            for problem in open_items[extra]:
                print(f"         - {problem}")


def sign(args: argparse.Namespace) -> int:
    gate = load_gate()
    item = next((i for i in gate["items"] if i["id"] == args.item), None)
    if item is None:
        raise SystemExit(f"no item {args.item!r}; items: {[i['id'] for i in gate['items']]}")
    if BOT_WORDS.search(args.by):
        raise SystemExit("a sign-off must name a person; automation and AI assistants cannot sign")
    signoff: dict[str, Any] = {
        "by": args.by,
        "role": args.role,
        "date": datetime.date.today().isoformat(),
        "conclusion": args.conclusion,
        "subjects": subject_hashes(item),
        "evidence": args.evidence,
    }
    if args.conditions:
        signoff["conditions"] = args.conditions
    if args.installer_sha256:
        signoff["installer_sha256"] = args.installer_sha256.lower()
    if item.get("decision_field"):
        signoff[item["decision_field"]] = args.decision
    item["signoff"] = signoff
    problems = check_item(item)
    if problems:
        item["signoff"] = None
        raise SystemExit("not recorded: " + "; ".join(problems))
    GATE.write_text(json.dumps(gate, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"recorded the sign-off of {args.item} by {args.by}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="list every item and what is open (always exits 0)")
    check = sub.add_parser("check", help="exit 1 unless the gate is open")
    check.add_argument("--release", action="store_true", help="also check the build to be released")
    check.add_argument(
        "--package-dir", type=Path, help="the build's artifacts folder (needed with --release)"
    )
    sign_cmd = sub.add_parser("sign", help="record a person's sign-off (hashes the subjects now)")
    sign_cmd.add_argument("item")
    sign_cmd.add_argument("--by", required=True)
    sign_cmd.add_argument("--role", required=True)
    sign_cmd.add_argument("--conclusion", choices=CONCLUSIONS, default="approved")
    sign_cmd.add_argument("--conditions", default="")
    sign_cmd.add_argument("--evidence", nargs="+", required=True)
    sign_cmd.add_argument("--installer-sha256", default="")
    sign_cmd.add_argument("--decision", default="", help="the value of the item's decision_field")
    args = parser.parse_args(argv)
    if args.command == "sign":
        return sign(args)
    gate = load_gate()
    package_dir = args.package_dir if args.command == "check" and args.release else None
    if args.command == "check" and args.release and package_dir is None:
        raise SystemExit("--release needs --package-dir")
    open_items = evaluate(gate, package_dir=package_dir)
    print_status(gate, open_items)
    if args.command == "status":
        return 0
    if open_items:
        print(f"\nRELEASE GATE CLOSED: {len(open_items)} open. Publication must not proceed.")
        return 1
    print("\nrelease gate open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
