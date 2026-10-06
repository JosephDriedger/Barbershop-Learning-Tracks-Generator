"""Reading ``<tie>`` (sound) and ``<tied>`` (notation) from a ``<note>``.

MusicXML 4.0: ``<tie>`` is "the tie sound" and is authoritative for playback; ``<tied>`` is
"the notated tie". The two are read separately and only *compared* for diagnostics; ``<tied>``
never creates a tie by itself.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass

_TIE_TYPES = ("start", "stop")
# <tied> also has "continue" (system breaks) and "let-ring" (unpaired); both are notation only.


@dataclass(frozen=True, slots=True)
class TieInfo:
    tie_types: tuple[str, ...]  # valid <tie type> values, document order
    invalid_tie_types: tuple[str, ...]  # <tie> elements with a missing or unknown type
    tied_types: tuple[str, ...]  # <tied type> start/stop values, document order

    @property
    def starts(self) -> bool:
        return "start" in self.tie_types

    @property
    def stops(self) -> bool:
        return "stop" in self.tie_types


def read_tie_info(note: ET.Element) -> TieInfo:
    valid: list[str] = []
    invalid: list[str] = []
    for tie in note.findall("tie"):
        kind = tie.get("type")
        if kind in _TIE_TYPES:
            valid.append(kind)
        else:
            invalid.append(kind if kind is not None else "(missing)")
    tied = [
        kind
        for element in note.findall("notations/tied")
        if (kind := element.get("type")) in _TIE_TYPES
    ]
    return TieInfo(tuple(valid), tuple(invalid), tuple(tied))
