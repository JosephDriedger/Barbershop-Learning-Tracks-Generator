"""Consistency check between ``<duration>`` and the notated ``<type>``.

``<duration>`` is authoritative for timing and is never changed. ``<type>`` (graphic note
type), ``<dot>`` and ``<time-modification>`` only let us verify that the notated value agrees.
"""

import xml.etree.ElementTree as ET
from fractions import Fraction
from typing import Final

from barbershop_tracks.core.musicxml.values import child_text, parse_int

# Note types in quarter-note units (quarter = 1).
TYPE_QUARTERS: Final[dict[str, Fraction]] = {
    "maxima": Fraction(32),
    "long": Fraction(16),
    "breve": Fraction(8),
    "whole": Fraction(4),
    "half": Fraction(2),
    "quarter": Fraction(1),
    "eighth": Fraction(1, 2),
    "16th": Fraction(1, 4),
    "32nd": Fraction(1, 8),
    "64th": Fraction(1, 16),
    "128th": Fraction(1, 32),
    "256th": Fraction(1, 64),
    "512th": Fraction(1, 128),
    "1024th": Fraction(1, 256),
}


def notated_quarters(note: ET.Element) -> Fraction | None:
    """The duration the ``<type>``, dots and tuplet ratio imply, or ``None`` if not checkable.

    ``None`` (no check) for: no ``<type>`` (permitted), an unknown type, a whole-measure rest,
    and a ``<time-modification>`` that is incomplete or uses ``<normal-type>``/``<normal-dot>``
    (where the expected value is ambiguous without more context).
    """
    rest = note.find("rest")
    if rest is not None and rest.get("measure") == "yes":
        return None
    base = TYPE_QUARTERS.get(child_text(note, "type") or "")
    if base is None:
        return None
    value = base * (2 - Fraction(1, 2 ** len(note.findall("dot"))))
    modification = note.find("time-modification")
    if modification is not None:
        if (
            modification.find("normal-type") is not None
            or modification.find("normal-dot") is not None
        ):
            return None
        actual = parse_int(child_text(modification, "actual-notes"))
        normal = parse_int(child_text(modification, "normal-notes"))
        if actual is None or normal is None or actual <= 0 or normal <= 0:
            return None
        value = value * Fraction(normal, actual)
    return value
