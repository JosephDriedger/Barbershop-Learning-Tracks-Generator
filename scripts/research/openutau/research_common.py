"""Shared constants and helpers for the M6 OpenUtau research tooling (throwaway; not production).

Nothing here drives the OpenUtau GUI. The tooling generates controlled input files, writes expected
event tables, and validates/compares the structured observations a person records by hand.
"""

import hashlib
import subprocess
from pathlib import Path

SCHEMA = "barbershop-tracks.research.openutau/1"
INDEX_SCHEMA = "barbershop-tracks.research.openutau.index/1"

CLASSIFICATIONS = (
    "MATCH",  # behaviour matches the handoff contract
    "BENIGN_DIFFERENCE",  # different representation, no musical corruption
    "WORKFLOW_REQUIREMENT",  # a manual action is required
    "INTEROPERABILITY_PROBLEM",  # the artifact cannot safely carry the required semantics
    "UNKNOWN",  # the experiment could not establish the behaviour
)
AUTOMATION_CLASSIFICATIONS = (
    "DOCUMENTED_STABLE",
    "DOCUMENTED_EXPERIMENTAL",
    "UNDOCUMENTED",
    "NOT_FOUND",
)
EVIDENCE_METHODS = ("project_file", "ui_numeric", "ui_visual", "documentation", "source")
PARTS = ("A", "B", "C")

# generated artifacts go here; the directory is git-ignored (see .gitignore)
DEFAULT_OUTPUT = Path("research-output") / "openutau"
OBSERVATIONS_DIR = Path("tests") / "fixtures" / "openutau" / "observations"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_commit() -> str | None:
    """The current commit (full hash), or ``None`` when git is unavailable."""
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def blt_version() -> str:
    from barbershop_tracks import __version__

    return __version__
