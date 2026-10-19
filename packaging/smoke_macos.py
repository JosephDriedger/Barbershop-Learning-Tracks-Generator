"""Smoke-test a built BLT Music Generator.app in a stripped-down environment (macOS).

    python packaging/smoke_macos.py --app "BLT Music Generator.app" [--keep]

The counterpart of ``packaging/smoke.ps1``. Every program runs with an environment that has no Python, no
.NET (no DOTNET_ROOT, PATH is only the system folders), no BLT_* build variables (BLT_HOST_DIR in
particular) and no source checkout, and with no display (Qt's offscreen platform). Two scenarios run:
the app as given in an ASCII path, and a copy of it under a path with spaces and non-ASCII characters (as
in a user name such as "Jörg Müller") with the data, settings, temp and home folders there too. The checks:

* ``blt --version``, ``blt diagnostics`` and the GUI's own start-up self-check (``--smoke-test``);
* ``blt selftest``: 13 WAVs and a verified manifest through the bundled host (no BLT_HOST_DIR);
* the per-user host runtime copy is created once and a second launch reuses it untouched;
* the host answers ``--g2p-check`` and ``--inventory`` and lists none of the removed engines;
* the app is not modified by running it (no caches, configs or temp files in it).

This proves the app works without a development environment. It is not a substitute for a real Mac that has
never had BLT or developer tools (the tester has to do that), it says nothing about how real voices sound,
and it does not exercise Gatekeeper, because a copy made here carries no quarantine flag.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ODD = "Jörg Müller 日本"
failures: list[str] = []


def check(ok: bool, text: str) -> None:
    print(f"  {'ok   ' if ok else 'FAIL '} {text}")
    if not ok:
        failures.append(text)


def clean_environment(profile: Path, data: Path) -> dict[str, str]:
    """Nothing of the developer's environment: system folders only, a private home and data folder."""
    for folder in ("tmp", "Library"):
        (profile / folder).mkdir(parents=True, exist_ok=True)
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(profile),
        "TMPDIR": str(profile / "tmp"),
        "USER": "smoke",
        "LANG": "en_US.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "BLT_DATA_DIR": str(data),
        "BLT_CONFIG": str(profile / "blt-config.json"),
    }


def run(
    program: Path, arguments: list[str], environment: dict[str, str], timeout: int = 600
) -> tuple[int, str, str, float]:
    start = time.monotonic()
    done = subprocess.run(
        [str(program), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=timeout,
        check=False,
    )
    return done.returncode, done.stdout, done.stderr, round(time.monotonic() - start, 1)


def snapshot(folder: Path) -> list[tuple[str, int, int]]:
    """Every file below ``folder`` (symbolic links as links) with its size and modification time."""
    listing = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            listing.append((str(path), -1, 0))
        elif path.is_file():
            info = path.stat()
            listing.append((str(path), info.st_size, info.st_mtime_ns))
    return listing


def last_json(text: str) -> dict[str, object] | None:
    found = None
    for line in text.splitlines():
        if line.startswith("{"):
            try:
                found = json.loads(line)
            except json.JSONDecodeError:
                continue
    return found


def copy_app(source: Path, destination: Path) -> Path:
    """A faithful copy (symbolic links, modes and extended attributes kept), like dragging the app."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ditto", str(source), str(destination)], check=True)
    return destination


def scenario(name: str, app: Path, profile: Path, data: Path) -> None:
    print(f"\n[{name}]\n  app:  {app}\n  data: {data}")
    environment = clean_environment(profile, data)
    macos = app / "Contents" / "MacOS"
    blt = macos / "blt"
    gui = macos / "BLT Music Generator"
    before = snapshot(app)

    code, out, err, _ = run(blt, ["diagnostics"], environment)
    check(
        code == 0 and "installed build" in out and "MISSING" not in out,
        f"blt diagnostics sees an installed build with its host (exit {code})",
    )
    code, out, err, _ = run(blt, ["--version"], environment)
    check(code == 0 and re.search(r"\d+\.\d+", out) is not None, f"blt --version ({out.strip()})")

    gui_environment = {**environment, "QT_QPA_PLATFORM": "offscreen"}
    code, out, err, _ = run(gui, ["--smoke-test"], gui_environment, timeout=120)
    check(code == 0, f"the GUI executable starts and builds its main window (exit {code})")
    if code != 0:
        print(out, err)

    keep = profile / "selftest-1"
    code, out, err, seconds = run(blt, ["selftest", "--keep", str(keep)], environment)
    check(
        code == 0 and "selftest passed" in out,
        f"selftest passes through the bundled host, first launch ({seconds} s)",
    )
    if code != 0:
        print(out, err)
    wavs = list((keep / "out").rglob("*.wav")) if (keep / "out").is_dir() else []
    check(len(wavs) == 13, f"13 WAV files were written ({len(wavs)})")
    check(any(keep.rglob("manifest.json")), "a manifest.json was written")

    runtime = data / "runtime"
    hosts = sorted(runtime.glob("host-*")) if runtime.is_dir() else []
    check(
        len(hosts) == 1,
        f"one per-user host runtime copy exists under the data folder ({len(hosts)})",
    )
    if len(hosts) != 1:
        return
    host_exe = hosts[0] / "blt-render-host"
    check(host_exe.is_file(), "the runtime copy holds the host")
    stamp, created = host_exe.stat().st_mtime_ns, hosts[0].stat().st_ctime_ns

    code, out, err, seconds = run(
        blt, ["selftest", "--keep", str(profile / "selftest-2")], environment
    )
    check(
        code == 0 and "selftest passed" in out,
        f"selftest passes again, second launch ({seconds} s)",
    )
    after = sorted(runtime.glob("host-*"))
    check(
        len(after) == 1
        and host_exe.stat().st_mtime_ns == stamp
        and after[0].stat().st_ctime_ns == created,
        "the second launch reused the host copy instead of reinstalling it",
    )

    # the model-free host: a word of the dictionary is phonemized, one outside it gets no guess, and no
    # onnxruntime is loaded (docs/g2p-model-provenance.md)
    code, out, err, _ = run(host_exe, ["--g2p-check"], environment)
    result = last_json(out) or {}
    record = json.loads((host_exe.parent / "blt-host-build.json").read_text(encoding="utf-8"))
    check(
        result.get("g2p_model") == record.get("g2p_model"),
        f"the host's g2p model state ({result.get('g2p_model')}) is the one its build record names "
        f"({record.get('g2p_model')})",
    )
    if result.get("g2p_model") == "excluded":
        check(
            code == 0
            and not result.get("onnxruntime")
            and not result.get("g2p_phonemes")
            and bool(result.get("g2p_known_phonemes")),
            "no g2p model: a dictionary word is phonemized, a word outside it gets no guess, "
            "onnxruntime is not loaded",
        )
    code, out, err, _ = run(host_exe, ["--inventory"], environment)
    inventory = last_json(out) or {}
    names = [str(n) for n in inventory.get("phonemizers", [])]  # type: ignore[attr-defined]
    removed = re.compile(r"ArpasingPlus|ARPAPlus|EnglishCpV|Voicevox")
    check(
        code == 0 and bool(names) and not any(removed.search(n) for n in names),
        f"the installed host's own inventory lists {len(names)} phonemizers, none of the removed ones",
    )

    check(
        snapshot(app) == before,
        "the app is unchanged after running (no caches, settings or temp files in it)",
    )
    helpers = app / "Contents" / "Resources" / "host"
    check(
        not (helpers / "OpenUtau").exists() and not (helpers / "Logs").exists(),
        "no OpenUtau cache, prefs or logs were created beside the shipped host",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    app = args.app.resolve()
    base = Path(tempfile.mkdtemp(prefix=f"blt-smoke-{uuid.uuid4().hex[:8]}-"))
    print(f"App: {app}")
    try:
        plain = copy_app(app, base / "plain" / app.name)
        profile = base / "profile"
        scenario("plain paths", plain, profile, profile / "BLT data")
        odd_root = base / ODD
        odd_app = copy_app(app, odd_root / "Applications" / app.name)
        scenario(
            "spaces and non-ASCII in every path",
            odd_app,
            odd_root / "Users" / ODD,
            odd_root
            / "Users"
            / ODD
            / "Library"
            / "Application Support"
            / "BarbershopLearningTracks",
        )
    finally:
        if args.keep:
            print(f"kept: {base}")
        else:
            shutil.rmtree(base, ignore_errors=True)
    print()
    if failures:
        print(f"SMOKE TEST FAILED ({len(failures)}):")
        for text in failures:
            print(f"  - {text}")
        return 1
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
