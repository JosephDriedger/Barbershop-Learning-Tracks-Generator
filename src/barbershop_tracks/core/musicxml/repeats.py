"""Repeat handling.

TEMPORARY (M3b): repeat expansion does not exist yet. Any repeat or ending structure is
*detected* so it can be reported as a generation-blocking error instead of being silently
parsed as a single pass. M3d replaces this module with real, deterministic expansion and
removes ``REPEAT_NOT_SUPPORTED_YET``.
"""

import xml.etree.ElementTree as ET

REPEAT_NOT_SUPPORTED_YET = "REPEAT_NOT_SUPPORTED_YET"
UNSUPPORTED_JUMP = "UNSUPPORTED_JUMP"

# <sound> attributes that make playback jump or stop early. Never expanded in v1.
JUMP_ATTRIBUTES = ("dacapo", "dalsegno", "segno", "coda", "tocoda", "fine")


def barline_has_repeat_structure(barline: ET.Element) -> bool:
    """True if a ``<barline>`` carries a repeat sign or a volta ending."""
    return barline.find("repeat") is not None or barline.find("ending") is not None


def jump_attributes_of(measure_child: ET.Element) -> list[str]:
    """Jump-related attributes on any ``<sound>`` in ``measure_child`` (a measure child)."""
    sounds = [measure_child] if measure_child.tag == "sound" else list(measure_child.iter("sound"))
    found: list[str] = []
    for sound in sounds:
        found.extend(name for name in JUMP_ATTRIBUTES if sound.get(name) is not None)
    return found
