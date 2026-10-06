"""Fail if generated audio, OpenUtau projects, or FFmpeg binaries are tracked by Git.

Run from anywhere inside the repository:  python scripts/check_no_audio_in_repo.py
Exit code 0 means clean; 1 means forbidden files were found.
"""

import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath

FORBIDDEN_SUFFIXES = frozenset(
    {
        ".wav",
        ".mp3",
        ".flac",
        ".ogg",
        ".opus",
        ".m4a",
        ".aac",
        ".aiff",
        ".aif",
        ".wma",
        ".ustx",
        ".ust",
        ".vsqx",
    }
)
FORBIDDEN_NAMES = frozenset({"ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"})


def find_forbidden(paths: Iterable[str]) -> list[str]:
    """Return the paths whose suffix or file name is forbidden (case-insensitive)."""
    bad: list[str] = []
    for raw in paths:
        path = PurePosixPath(raw)
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name.lower() in FORBIDDEN_NAMES:
            bad.append(raw)
    return bad


def tracked_files() -> list[str]:
    """List files in the Git index (tracked or staged)."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [name for name in result.stdout.split("\0") if name]


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    bad = find_forbidden(tracked_files())
    if bad:
        print("Forbidden files are tracked by Git:", file=sys.stderr)
        for name in bad:
            print(f"  {name}", file=sys.stderr)
        return 1
    print("OK: no audio, OpenUtau project, or FFmpeg files are tracked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
