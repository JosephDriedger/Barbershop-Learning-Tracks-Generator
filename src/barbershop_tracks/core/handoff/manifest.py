"""The versioned handoff manifest: deterministic JSON, exact fractions as strings.

No timestamps, no absolute or temporary paths. ``source.sha256`` is the source identity;
``source.display_name`` is for display only.
"""

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from barbershop_tracks import __version__
from barbershop_tracks.core.midi import (
    METER_32NDS_PER_QUARTER,
    METER_CLICK_CLOCKS,
    NOTE_OFF_VELOCITY,
    NOTE_ON_VELOCITY,
    MidiExport,
)
from barbershop_tracks.core.readiness import Disposition, ReadinessReport

SCHEMA = "barbershop-tracks.handoff/1"
SUPPORTED_VERSIONS = frozenset({1})
PACKAGE_TYPE = "barbershop-tracks.handoff"
GENERATOR = "BLT Music Generator"

LYRICS_STATUS = {
    "status": "not_exported",
    "reason": "awaiting OpenUtau lyric-import validation",
}
LIMITATIONS = (
    "No lyrics are exported; the MusicXML lyrics are not used by this handoff.",
    "Note velocity is a constant; score dynamics are not exported.",
    "Tempo is stored as whole microseconds per quarter note; see tempo.events.",
    "Time-signature clocks-per-click and 32nds-per-quarter are conventional, not score data.",
    "A pickup (anacrusis) has no MIDI representation; time zero is tick zero.",
    "OpenUtau's MIDI import behaviour is not verified by this tool.",
)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_entry(name: str, kind: str, data: bytes) -> dict[str, Any]:
    return {"name": name, "kind": kind, "bytes": len(data), "sha256": sha256_hex(data)}


def build_manifest(
    *,
    midi: MidiExport,
    midi_file: str,
    other_files: Mapping[str, tuple[str, bytes]],
    source_name: str,
    source_sha256: str,
    report: ReadinessReport,
) -> dict[str, Any]:
    """``other_files`` maps a file name to ``(kind, bytes)`` for every file but the manifest."""
    plan = midi.plan
    warnings: list[dict[str, str]] = [
        {"origin": "midi", "code": w.code, "message": w.message} for w in midi.warnings
    ]
    warnings += [
        {"origin": "readiness", "code": f.code, "message": f.issue.message} for f in report.advisory
    ]
    files = [file_entry(midi_file, "midi", midi.data)]
    files += [file_entry(name, kind, data) for name, (kind, data) in sorted(other_files.items())]
    return {
        "schema": SCHEMA,
        "package_type": PACKAGE_TYPE,
        "generator": {"name": GENERATOR, "version": __version__},
        "source": {"display_name": source_name, "sha256": source_sha256},
        "midi": {
            "file": midi_file,
            "sha256": sha256_hex(midi.data),
            "bytes": len(midi.data),
            "format": 1,
            "ppq": plan.ppq,
            "tracks": [{"name": t.name, "channel": t.channel} for t in plan.tracks],
            "note_on_velocity": NOTE_ON_VELOCITY,
            "note_off_velocity": NOTE_OFF_VELOCITY,
        },
        "timing": {
            "performed_length_quarters": str(plan.end_position),
            "end_tick": plan.end_tick,
        },
        "roles": [
            {
                "role": r.role.value,
                "track": r.track_name,
                "channel": r.channel,
                "line_id": r.line_id,
                "part_name": r.part_name,
                "attacks": r.attacks,
                "lowest_midi": r.lowest_midi,
                "highest_midi": r.highest_midi,
            }
            for r in plan.roles
        ],
        "tempo": {
            "policy": "exact microseconds per quarter = 60000000 / bpm, rounded half to even",
            "events": [
                {
                    "position": str(t.position),
                    "tick": t.tick,
                    "bpm": str(t.bpm),
                    "exact_us_per_quarter": str(t.exact_us_per_quarter),
                    "encoded_us_per_quarter": t.encoded_us_per_quarter,
                    "error_us_per_quarter": str(t.error_us_per_quarter),
                    "bpm_error": str(t.bpm_error),
                }
                for t in plan.tempo
            ],
        },
        "meter": {
            "auxiliary_fields": {
                "clocks_per_click": METER_CLICK_CLOCKS,
                "notated_32nds_per_quarter": METER_32NDS_PER_QUARTER,
                "note": "conventional MIDI values, not facts from the score",
            },
            "written": [
                {
                    "position": str(m.position),
                    "tick": m.tick,
                    "beats": m.beats,
                    "beat_type": m.beat_type,
                }
                for m in plan.meter
                if m.written
            ],
            "omitted": [
                {
                    "position": str(m.position),
                    "beats": m.beats,
                    "beat_type": m.beat_type,
                    "reason": m.reason,
                }
                for m in plan.meter
                if not m.written
            ],
        },
        "lyrics": dict(LYRICS_STATUS),
        "readiness": {
            "capability": report.capability.name,
            "ready": report.ready,
            "counts": {
                d.value: n for d, n in sorted(report.counts.items(), key=lambda p: p[0].value)
            },
            "advisory_codes": sorted(
                {f.code for f in report.findings if f.disposition is Disposition.ADVISORY}
            ),
        },
        "warnings": warnings,
        "limitations": list(LIMITATIONS),
        "files": files,
    }


def render_manifest(manifest: Mapping[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, ensure_ascii=True) + "\n").encode("ascii")
