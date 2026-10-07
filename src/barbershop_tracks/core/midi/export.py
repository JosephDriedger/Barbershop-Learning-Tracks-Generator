"""The pure, in-memory MIDI export: plan, encode, verify. No filesystem, no file names."""

from barbershop_tracks.core.midi.build import build_midi_plan
from barbershop_tracks.core.midi.encode import encode_midi
from barbershop_tracks.core.midi.model import MidiExport
from barbershop_tracks.core.midi.ticks import DEFAULT_PPQ
from barbershop_tracks.core.midi.verify import verify_midi_bytes
from barbershop_tracks.core.readiness.assignments import RoleAssignments
from barbershop_tracks.models import PerformedSong


def export_midi(
    performed: PerformedSong, assignments: RoleAssignments, *, ppq: int = DEFAULT_PPQ
) -> MidiExport:
    """The quartet MIDI for ``performed``; raises ``MidiExportError`` if it cannot be exact."""
    plan = build_midi_plan(performed, assignments, ppq=ppq)
    data = encode_midi(plan)
    verify_midi_bytes(data, plan)  # the bytes decode to exactly the intended semantics
    return MidiExport(plan=plan, data=data)
