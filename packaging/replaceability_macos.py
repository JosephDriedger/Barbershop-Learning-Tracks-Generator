"""Prove that the Qt libraries in a built macOS app are separate, replaceable files (LGPL-3.0 section 4(d)(1)).

    python packaging/replaceability_macos.py --app "BLT Music Generator.app"

The counterpart of ``packaging/replaceability-test.ps1``. On a private copy of the app:

1. the GUI starts (offscreen Qt, ``--smoke-test``): the baseline;
2. the QtWidgets framework library is moved away: the GUI must fail, which shows the file is really
   loaded from disk and is not merged into the executable;
3. it is put back as a *different* file (the original with bytes appended) that is signed again ad hoc,
   the way anyone who replaces a library in an app has to on macOS (a changed file has lost its
   signature, and Apple silicon refuses to run unsigned code): the GUI must start again, which shows BLT
   neither checks nor pins the file.

That is the mechanism the LGPL asks for. It does not show that a Qt build somebody modified works; the
app only ever contains the unmodified Qt of the PySide6 wheel.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

failures: list[str] = []


def check(ok: bool, text: str) -> None:
    print(f"  {'ok   ' if ok else 'FAIL '} {text}")
    if not ok:
        failures.append(text)


def start_gui(app: Path, base: Path) -> int:
    """The GUI's exit code; -1 when it neither exits nor fails within the time (a modal error box)."""
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(base / "home"),
        "QT_QPA_PLATFORM": "offscreen",
        "BLT_DATA_DIR": str(base / "data"),
        "BLT_CONFIG": str(base / "config.json"),
    }
    (base / "home").mkdir(exist_ok=True)
    try:
        done = subprocess.run(
            [str(app / "Contents" / "MacOS" / "BLT Music Generator"), "--smoke-test"],
            capture_output=True,
            env=environment,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return -1
    return done.returncode


def find_library(app: Path) -> Path | None:
    for candidate in sorted(app.rglob("QtWidgets")):
        real = candidate.resolve()
        if real.is_file() and real.parent.name in ("A", "QtWidgets.framework"):
            return real
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    args = parser.parse_args()
    base = Path(tempfile.mkdtemp(prefix=f"blt-relink-{uuid.uuid4().hex[:8]}-"))
    copy = base / args.app.name
    try:
        subprocess.run(["ditto", str(args.app.resolve()), str(copy)], check=True)
        library = find_library(copy)
        if library is None:
            print(
                "QtWidgets is not a separate file in the app: the LGPL replacement mechanism is missing"
            )
            return 1
        print(f"App:     {args.app}\nLibrary: {library.relative_to(copy.resolve())}")

        check(start_gui(copy, base) == 0, "baseline: the GUI starts with the original library")

        original = library.with_name("QtWidgets.original")
        library.rename(original)
        check(
            start_gui(copy, base) != 0,
            "with the QtWidgets library removed the GUI cannot start (it is loaded from this file)",
        )

        shutil.copyfile(original, library)
        library.chmod(0o755)
        with library.open("ab") as handle:
            handle.write(b"BLT\n")  # a different file with the same contents
        different = library.read_bytes() != original.read_bytes()
        check(different, "the replacement file differs from the original")
        signed = subprocess.run(
            ["codesign", "--force", "--sign", "-", str(library)], capture_output=True, check=False
        )
        check(
            signed.returncode == 0, "the replacement is signed ad hoc, as anyone replacing it must"
        )
        check(
            start_gui(copy, base) == 0,
            "the GUI starts with the replaced library (no pinning or integrity check in BLT)",
        )
    finally:
        shutil.rmtree(base, ignore_errors=True)
    if failures:
        print(f"REPLACEABILITY TEST FAILED ({len(failures)})")
        return 1
    print("replaceability test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
