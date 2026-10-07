"""Unsupported structure detection: jump markers.

Repeat signs are read by ``repeat_marks`` and endings by ``endings``; ``core.timeline`` expands
them. Jumps (D.C./D.S./segno/coda/fine) are *detected* so they are reported as generation-blocking
errors instead of being silently parsed as a single pass.
"""

import xml.etree.ElementTree as ET

UNSUPPORTED_JUMP = "UNSUPPORTED_JUMP"

# <sound> attributes that make playback jump or stop early. Never expanded in v1.
JUMP_ATTRIBUTES = ("dacapo", "dalsegno", "segno", "coda", "tocoda", "fine")


def jump_attributes_of(measure_child: ET.Element) -> list[str]:
    """Jump-related attributes on any ``<sound>`` in ``measure_child`` (a measure child)."""
    sounds = [measure_child] if measure_child.tag == "sound" else list(measure_child.iter("sound"))
    found: list[str] = []
    for sound in sounds:
        found.extend(name for name in JUMP_ATTRIBUTES if sound.get(name) is not None)
    return found
