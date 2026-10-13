"""Prepare the sources of BLT's own ``worldline.dll`` (OpenUtau's native resampler, rebuilt by us).

OpenUtau ships a prebuilt ``worldline.dll`` that statically contains ``tk::spline``
(GPL-2.0-or-later). BLT builds the DLL itself from the same pinned sources with that one component
replaced by ``patched/natural_spline.h`` (see docs/worldline-provenance.md). This script downloads
the exact third-party archives OpenUtau's own build pins (SHA-256 checked), applies OpenUtau's three
upstream patches and BLT's patch, and lays out a work folder that CMakeLists.txt builds with MSVC.

    python host/native/prepare.py WORKDIR --openutau-src SRC

``SRC`` is the pinned OpenUtau checkout (``host/build.ps1`` creates it). Needs git and network
access to github.com. ``-DPATCH_SPLINE=OFF`` builds what upstream compiles (comparison only).
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CRLF, LF = bytes([13, 10]), bytes([10])
# The commit that last changed the shipped runtimes/win-x64/native/worldline.dll (2024-07-28).
WORLDLINE_COMMIT = "6958d68b648bdd734d1eafa9e49b02657ca9d18e"
# name -> (url, sha256 of the archive); the same pins as cpp/WORKSPACE.bazel and MODULE.bazel
ARCHIVES = {
    "world": (
        "https://github.com/mmorise/World/archive/f8dd5fb289db6a7f7f704497752bf32b258f9151.zip",
        "2054f12a8961ed391b089c401c390f983f7ef7e31f63eabcb15a135563001c95",
    ),
    "libgvps": (
        "https://github.com/Sleepwalking/libgvps/archive/2f1b4106d72f8f8138dc447bf0123820c0772cbd.zip",
        "eacc4ae7b1b2ba412be8a659120f77ee37de8d03e5ab6cf9990e099cb5351f7c",
    ),
    "libpyin": (
        "https://github.com/Sleepwalking/libpyin/archive/b38135390b335c3e8cea6ef35cf5093789b36dac.zip",
        "0510a68a09ceaa2282022a1d2e84e9d37d73e93e0e74d8d28956a2d370f6520a",
    ),
    "spline": (
        "https://github.com/ttk592/spline/archive/5894beaf91e9adbfdbe5c6c9a1c60770e380e8e8.zip",
        "0d42b77d0f398c9ad2b7290587b625c49c39a2337f6cfa88b6a7930207d91a33",
    ),
    "libnpy": (
        "https://github.com/llohse/libnpy/archive/refs/tags/v1.0.1.zip",
        "3c9864c1bf7af08c88f2056478a2c6d2539674673bab9f9b4a0042a84a857f19",
    ),
    "miniaudio": (
        "https://github.com/mackron/miniaudio/archive/refs/tags/0.11.21.zip",
        "cbde908871e2619115fd216c74235265348060fe7d340f980cd14342e88d7f72",
    ),
    "xxhash": (
        "https://github.com/Cyan4973/xxHash/archive/refs/tags/v0.8.2.zip",
        "a33d7e8798bebb297095b715f93a71c5e535919434ce27ddc65e72e4e0fda3b9",
    ),
    "abseil": (
        "https://github.com/abseil/abseil-cpp/archive/refs/tags/20240116.1.zip",
        "edc6a93163af5b2a186d468717f6fe23653a5cb31a1e6932f0aba05af7d762e9",
    ),
}
UPSTREAM_PATCHES = {"world": "world.patch", "libpyin": "libpyin.patch", "spline": "spline.patch"}
TEXT_SUFFIXES = {".c", ".h", ".cpp", ".hpp", ".hc", ".cc", ".txt", ".cmake"}


def download(name: str, url: str, expected: str, cache: Path) -> Path:
    target = cache / f"{name}.zip"
    if not target.exists():
        with urllib.request.urlopen(url) as response:
            target.write_bytes(response.read())
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"{name}: archive hash {actual} differs from the pinned {expected}")
    return target


def unpack(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        top = {n.split("/", 1)[0] for n in zf.namelist()}
        (root,) = top
        scratch = destination.parent / f".unpack-{destination.name}"
        shutil.rmtree(scratch, ignore_errors=True)
        zf.extractall(scratch)
    shutil.rmtree(destination, ignore_errors=True)
    (scratch / root).rename(destination)
    shutil.rmtree(scratch, ignore_errors=True)
    for path in destination.rglob("*"):  # LF endings, so the upstream patches apply on Windows too
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            data = path.read_bytes()
            if b"\r\n" in data:
                path.write_bytes(data.replace(b"\r\n", b"\n"))


def apply_patch(patch: Path, directory: Path) -> None:
    """Apply a unified diff (paths with one leading component) inside ``directory``.

    The work folder lives under a git repository that ignores it, and ``git apply`` silently skips
    ignored paths there; the ceiling makes git behave as it does outside any repository, and a
    "Skipped" line in its report is treated as a failure.
    """
    done = subprocess.run(
        ["git", "apply", "--ignore-whitespace", "-p1", "-v", str(patch)],
        cwd=directory,
        env={**os.environ, "GIT_CEILING_DIRECTORIES": str(directory.resolve().parent)},
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0 or "Skipped" in done.stderr or "Applied patch" not in done.stderr:
        raise SystemExit(f"applying {patch.name} failed: {done.stdout} {done.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("workdir", type=Path)
    parser.add_argument(
        "--openutau-src", type=Path, required=True, help="the pinned OpenUtau checkout"
    )
    args = parser.parse_args()
    work = args.workdir.resolve()
    cache = work / "downloads"
    cache.mkdir(parents=True, exist_ok=True)

    # OpenUtau's cpp/ at the commit that built the shipped worldline.dll
    cpp = work / "worldline-src"
    shutil.rmtree(cpp, ignore_errors=True)
    cpp.mkdir()
    src = args.openutau_src.resolve()
    subprocess.run(
        ["git", "-C", str(src), "fetch", "--depth", "1", "origin", WORLDLINE_COMMIT], check=True
    )
    tar = cache / "cpp.tar"
    subprocess.run(
        ["git", "-C", str(src), "archive", "-o", str(tar), "FETCH_HEAD", "cpp"], check=True
    )
    shutil.unpack_archive(str(tar), str(cpp))

    sources = work / "wl"
    sources.mkdir(exist_ok=True)
    for name, (url, digest) in ARCHIVES.items():
        unpack(download(name, url, digest, cache), sources / name)
    patches = work / "patches"
    patches.mkdir(exist_ok=True)
    for name, patch in UPSTREAM_PATCHES.items():
        text = (cpp / "cpp" / "third_party" / patch).read_bytes().replace(CRLF, LF)
        (patches / patch).write_bytes(text)
        apply_patch(patches / patch, sources / name)

    shutil.copy(HERE / "CMakeLists.txt", work / "CMakeLists.txt")
    shutil.copytree(HERE / "patched", work / "patched", dirs_exist_ok=True)
    own_patch = (HERE / "effects-natural-spline.patch").read_bytes().replace(CRLF, LF)
    (patches / "effects-natural-spline.patch").write_bytes(
        own_patch
    )  # LF whatever the checkout did
    # patched/worldline/model/effects.cpp = upstream effects.cpp + BLT's patch
    target = work / "patched" / "worldline" / "model"
    target.mkdir(parents=True, exist_ok=True)
    original = cpp / "cpp" / "worldline" / "model" / "effects.cpp"
    (target / "effects.cpp").write_bytes(original.read_bytes().replace(CRLF, LF))
    apply_patch(patches / "effects-natural-spline.patch", work / "patched")
    print(
        f"prepared {work}",
        f"build: cmake -S {work} -B {work}/build -G Ninja -DPATCH_SPLINE=ON",
        sep="\n",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
