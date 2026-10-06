"""Unsupported structure detection: endings (voltas) and jump markers.

Plain repeat signs are read by ``repeat_marks`` and expanded by ``core.timeline``. Endings and
jumps are *detected* so they are reported as generation-blocking errors instead of being silently
parsed as a single pass. ``ENDING_NOT_SUPPORTED_YET`` is temporary: M3e interprets endings.
"""

import xml.etree.ElementTree as ET

ENDING_NOT_SUPPORTED_YET = "ENDING_NOT_SUPPORTED_YET"
UNSUPPORTED_JUMP = "UNSUPPORTED_JUMP"

# <sound> attributes that make playback jump or stop early. Never expanded in v1.
JUMP_ATTRIBUTES = ("dacapo", "dalsegno", "segno", "coda", "tocoda", "fine")


def barline_has_ending(barline: ET.Element) -> bool:
    """True if a ``<barline>`` carries a volta ending."""
    return barline.find("ending") is not None


def jump_attributes_of(measure_child: ET.Element) -> list[str]:
    """Jump-related attributes on any ``<sound>`` in ``measure_child`` (a measure child)."""
    sounds = [measure_child] if measure_child.tag == "sound" else list(measure_child.iter("sound"))
    found: list[str] = []
    for sound in sounds:
        found.extend(name for name in JUMP_ATTRIBUTES if sound.get(name) is not None)
    return found
