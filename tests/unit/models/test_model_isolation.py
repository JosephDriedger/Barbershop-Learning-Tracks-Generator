"""The models package must stay pure: no Qt, UI, workers, core, or external-tool code."""

import subprocess
import sys

FORBIDDEN_PREFIXES = (
    "PySide6",
    "barbershop_tracks.ui",
    "barbershop_tracks.workers",
    "barbershop_tracks.core",
    "barbershop_tracks.config",
    "defusedxml",
    "mido",
)

_SCRIPT = """
import sys
import barbershop_tracks.models
prefixes = {prefixes!r}
loaded = sorted(m for m in sys.modules if m.startswith(prefixes))
print("\\n".join(loaded))
"""


def test_importing_models_loads_no_forbidden_modules() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT.format(prefixes=FORBIDDEN_PREFIXES)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert result.stdout.strip() == ""
