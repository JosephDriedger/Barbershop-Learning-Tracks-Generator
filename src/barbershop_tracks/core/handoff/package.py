"""Build and verify the package contents in memory (no filesystem)."""

import json
from dataclasses import dataclass
from typing import Any

from barbershop_tracks.core.handoff.errors import HandoffError
from barbershop_tracks.core.handoff.instructions import instructions_text
from barbershop_tracks.core.handoff.manifest import (
    PACKAGE_TYPE,
    SCHEMA,
    build_manifest,
    render_manifest,
    sha256_hex,
)
from barbershop_tracks.core.handoff.names import (
    INSTRUCTIONS_NAME,
    MANIFEST_NAME,
    midi_filename,
    package_dirname,
)
from barbershop_tracks.core.midi import (
    MidiExport,
    MidiExportError,
    MidiVerificationError,
    export_midi,
    verify_midi_bytes,
)
from barbershop_tracks.core.midi.ticks import DEFAULT_PPQ
from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.readiness import (
    MIDI_QUARTET,
    ReadinessReport,
    RoleAssignments,
    assess_readiness,
)


@dataclass(frozen=True, slots=True)
class PreparedHandoff:
    """A package fully built and verified in memory: ready to be written, nothing on disk yet."""

    name: str
    dirname: str
    files: dict[str, bytes]  # file name -> bytes, the manifest last
    manifest: dict[str, Any]
    midi: MidiExport
    report: ReadinessReport


@dataclass(frozen=True, slots=True)
class Preparation:
    """The outcome of preparing a handoff. ``handoff`` is set only when everything succeeded."""

    report: ReadinessReport
    handoff: PreparedHandoff | None = None
    export_error: MidiExportError | None = None


def verify_package_files(files: dict[str, bytes], midi: MidiExport) -> None:
    """Check the in-memory package against its own manifest and the MIDI plan."""
    try:
        manifest = json.loads(files[MANIFEST_NAME].decode("ascii"))
    except (KeyError, ValueError) as error:
        raise HandoffError("HANDOFF_VERIFY_FAILED", f"manifest unreadable: {error}") from error
    if manifest.get("schema") != SCHEMA or manifest.get("package_type") != PACKAGE_TYPE:
        raise HandoffError("HANDOFF_VERIFY_FAILED", "manifest identifiers are wrong")
    listed = {entry["name"]: entry for entry in manifest["files"]}
    if set(listed) | {MANIFEST_NAME} != set(files):
        raise HandoffError("HANDOFF_VERIFY_FAILED", "manifest and package files differ")
    for name, entry in listed.items():
        data = files[name]
        if entry["bytes"] != len(data) or entry["sha256"] != sha256_hex(data):
            raise HandoffError("HANDOFF_VERIFY_FAILED", f"{name} does not match its manifest entry")
    if manifest["midi"]["sha256"] != sha256_hex(files[manifest["midi"]["file"]]):
        raise HandoffError("HANDOFF_VERIFY_FAILED", "the manifest MIDI hash is wrong")
    try:
        verify_midi_bytes(files[manifest["midi"]["file"]], midi.plan)
    except MidiVerificationError as error:
        raise HandoffError("HANDOFF_VERIFY_FAILED", f"MIDI read-back failed: {error}") from error


def prepare_handoff(
    parsed: ParseResult,
    assignments: RoleAssignments,
    *,
    name: str,
    source_name: str,
    source_sha256: str,
    ppq: int = DEFAULT_PPQ,
    strict: bool = False,
) -> Preparation:
    """Readiness first (``MIDI_QUARTET``), then the MIDI export, then the package, all in memory."""
    report = assess_readiness(parsed, assignments, MIDI_QUARTET)
    if not (report.clean if strict else report.ready) or parsed.performed is None:
        return Preparation(report)
    try:
        midi = export_midi(parsed.performed, assignments, ppq=ppq)
    except MidiExportError as error:
        return Preparation(report, export_error=error)
    midi_file = midi_filename(name)
    others = {INSTRUCTIONS_NAME: ("instructions", instructions_text(midi_file).encode("ascii"))}
    manifest = build_manifest(
        midi=midi,
        midi_file=midi_file,
        other_files=others,
        source_name=source_name,
        source_sha256=source_sha256,
        report=report,
    )
    files = {midi_file: midi.data, INSTRUCTIONS_NAME: others[INSTRUCTIONS_NAME][1]}
    files[MANIFEST_NAME] = render_manifest(manifest)
    verify_package_files(files, midi)
    handoff = PreparedHandoff(
        name=name,
        dirname=package_dirname(name),
        files=files,
        manifest=manifest,
        midi=midi,
        report=report,
    )
    return Preparation(report, handoff)
