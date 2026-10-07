"""Builders for the handoff package tests (in memory; nothing here touches the filesystem)."""

from barbershop_tracks.core.handoff import Preparation, PreparedHandoff, prepare_handoff
from barbershop_tracks.core.musicxml import ParseResult
from readiness_builders import quartet_assignments, ready_parsed


def prepare(
    parsed: ParseResult | None = None, *, name: str = "demo", strict: bool = False, ppq: int = 480
) -> Preparation:
    return prepare_handoff(
        parsed if parsed is not None else ready_parsed(),
        quartet_assignments(),
        name=name,
        source_name="demo.musicxml",
        source_sha256="0" * 64,
        ppq=ppq,
        strict=strict,
    )


def prepared(name: str = "demo") -> PreparedHandoff:
    handoff = prepare(name=name).handoff
    assert handoff is not None
    return handoff
