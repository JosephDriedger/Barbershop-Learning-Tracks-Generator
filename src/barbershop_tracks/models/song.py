"""The song: metadata, parts, and tempo/meter maps. No parsing or validation here."""

from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

from barbershop_tracks.models.part import Part
from barbershop_tracks.models.timing import TempoChange, TimeSignature
from barbershop_tracks.models.voice import VoiceRole


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceMetadata:
    """Where a song came from. All fields are optional."""

    path: Path | None = None
    format_name: str | None = None  # e.g. "MusicXML"
    format_version: str | None = None
    software: str | None = None  # the exporting application, if recorded


@dataclass(frozen=True, slots=True, kw_only=True)
class Song:
    """A complete score as plain data.

    Structural invariants only: part ids are unique, and the tempo and time-signature
    maps are in strictly increasing position order. Musical correctness (four voices,
    monophony, lyrics, ...) is the validator's job, not the model's.
    """

    title: str
    composer: str | None = None
    arranger: str | None = None
    parts: tuple[Part, ...] = ()
    tempo_map: tuple[TempoChange, ...] = ()
    time_signatures: tuple[TimeSignature, ...] = ()
    source: SourceMetadata = SourceMetadata()

    def __post_init__(self) -> None:
        parts = tuple(self.parts)
        tempo_map = tuple(self.tempo_map)
        time_signatures = tuple(self.time_signatures)
        part_ids = [part.part_id for part in parts]
        if len(set(part_ids)) != len(part_ids):
            raise ValueError("part ids must be unique")
        _require_strictly_increasing([t.position for t in tempo_map], "tempo_map")
        _require_strictly_increasing([s.position for s in time_signatures], "time_signatures")
        object.__setattr__(self, "parts", parts)
        object.__setattr__(self, "tempo_map", tempo_map)
        object.__setattr__(self, "time_signatures", time_signatures)

    def part_by_id(self, part_id: str) -> Part | None:
        return next((part for part in self.parts if part.part_id == part_id), None)

    def parts_for_role(self, role: VoiceRole) -> tuple[Part, ...]:
        """All parts explicitly assigned ``role`` (more than one is a validation matter)."""
        return tuple(part for part in self.parts if part.role is role)

    @property
    def duration(self) -> Fraction:
        """End of the longest part in quarter notes (0 if there are no parts)."""
        return max((part.end for part in self.parts), default=Fraction(0))


def _require_strictly_increasing(positions: list[Fraction], name: str) -> None:
    if any(later <= earlier for earlier, later in pairwise(positions)):
        raise ValueError(f"{name} positions must be strictly increasing")
