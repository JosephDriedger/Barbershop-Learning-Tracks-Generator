"""Tempo (``<sound tempo>``) helpers: value, offset rule, and cross-part reconciliation.

Rules (MusicXML 4.0, standards-correct even where MuseScore differs):

* ``tempo`` is quarter notes per minute, read as an exact ``Fraction`` (92.5 is 185/2). Nothing
  is rounded; any rounding to a MIDI tempo happens only in the exporter.
* ``tempo="0"`` means "ask the user" and is *unresolved*, never a tempo and never 120.
* A tempo with no explicit value is never invented; a score with no tempo has an empty map.
* Position = the XML cursor plus an offset (in ``divisions``, converted exactly):
  the ``<sound>``'s own ``<offset>`` if present (it overrides the direction's); otherwise the
  direction's ``<offset>`` **only if** ``sound="yes"`` (the default is ``no``: the sound then
  takes effect at the current location); otherwise zero. Offsets are never clamped.
"""

import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.musicxml.issues import IssueCollector
from barbershop_tracks.core.musicxml.values import parse_decimal
from barbershop_tracks.models import TempoChange


@dataclass(frozen=True, slots=True)
class TempoEvent:
    """One explicit, valid tempo found in a part, before cross-part reconciliation."""

    position: Fraction  # exact quarter-note position on the timeline
    bpm: Fraction
    part_id: str
    measure: int


def parse_tempo_value(raw: str) -> Fraction | None:
    """Exact non-negative decimal quarter-notes-per-minute, or ``None`` if not a plain decimal."""
    value = parse_decimal(raw)
    if value is None or value < 0:
        return None
    return value


def offset_element(sound: ET.Element, direction: ET.Element | None) -> ET.Element | None:
    """The ``<offset>`` that applies to ``sound`` under MusicXML 4.0, or ``None``.

    The sound's own offset wins. A direction's offset applies to the sound only with
    ``sound="yes"``; the default (``no``) keeps the sound at the current location.
    """
    own = sound.find("offset")
    if own is not None:
        return own
    if direction is not None:
        inherited = direction.find("offset")
        if inherited is not None and inherited.get("sound") == "yes":
            return inherited
    return None


def has_metronome_without_tempo(direction: ET.Element) -> bool:
    """A ``<metronome>`` mark whose direction carries no ``<sound tempo>`` (notation only)."""
    if direction.find("direction-type/metronome") is None:
        return False
    return not any(sound.get("tempo") is not None for sound in direction.findall("sound"))


def reconcile_tempos(
    events: Sequence[TempoEvent], issues: IssueCollector
) -> tuple[TempoChange, ...]:
    """One ``TempoChange`` per distinct position, in order.

    Identical values at the same position (from one part or several) become one event; every
    explicit event is otherwise kept, even if its value equals the previous tempo. Different
    values at the same position are ``TEMPO_CONFLICT`` and that position is left unresolved
    rather than choosing one.
    """
    by_position: dict[Fraction, list[TempoEvent]] = defaultdict(list)
    for event in events:
        by_position[event.position].append(event)
    changes: list[TempoChange] = []
    for position in sorted(by_position):
        group = by_position[position]
        values = {event.bpm for event in group}
        if len(values) == 1:
            changes.append(TempoChange(position=position, bpm=group[0].bpm))
            continue
        detail = "; ".join(f"part {e.part_id} measure {e.measure}: {_format(e.bpm)}" for e in group)
        issues.error(
            "TEMPO_CONFLICT",
            f"different tempos at the same position ({detail})",
            part_id=group[0].part_id,
            measure=group[0].measure,
        )
    return tuple(changes)


def _format(value: Fraction) -> str:
    return (
        str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"
    )
