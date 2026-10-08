"""Builders for the synthesis-plan and USTX tests: hand-built performed quartets, no engine."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from fractions import Fraction

from barbershop_tracks.core.synthesis import (
    LyricApproval,
    LyricProposal,
    MeterPoint,
    SourceIdentity,
    SynthesisPlan,
    VoiceEngineRef,
    build_synthesis_plan,
)
from barbershop_tracks.models import (
    Lyric,
    LyricKind,
    Melisma,
    Note,
    PerformedSong,
    Pitch,
    VoiceRole,
)
from midi_builders import performed_of
from readiness_builders import PITCHES, note, quartet_assignments, quartet_lines

SOURCE = SourceIdentity(display_name="demo.musicxml", sha256="ab" * 32, title="Demo")
ROLES = (VoiceRole.TENOR, VoiceRole.LEAD, VoiceRole.BARITONE, VoiceRole.BASS)


def refs(**overrides: VoiceEngineRef) -> dict[VoiceRole, VoiceEngineRef]:
    """Four stated engine references (a made-up singer id; nothing here is a real voicebank)."""
    base = VoiceEngineRef(
        singer="test-singer", phonemizer="OpenUtau.Core.DefaultPhonemizer", renderer="WORLDLINE-R"
    )
    return {role: overrides.get(role.value, base) for role in ROLES}


def text(value: str, *, melisma: Melisma = Melisma.NONE) -> tuple[Lyric, ...]:
    return (Lyric(text=value, melisma=melisma),)


def sung(
    role: VoiceRole,
    words: Sequence[str | None],
    *,
    pitch: Pitch | None = None,
    duration: Fraction | int = 1,
    start: Fraction | int = 0,
) -> list[Note]:
    """Back-to-back notes of ``duration``; ``None`` is a sounding note without any lyric."""
    pitch = pitch or PITCHES[role]
    notes: list[Note] = []
    position = Fraction(start)
    for word in words:
        notes.append(note(position, duration, pitch, lyrics=() if word is None else text(word)))
        position += Fraction(duration)
    return notes


def full_lyrics(
    words: Sequence[str | None] = ("one", "two", "three", "four"),
) -> dict[str, list[Note]]:
    return {role.value: sung(role, words) for role in ROLES}


def performed(**voices: Sequence[Note]) -> PerformedSong:
    """A performed quartet (4/4, 100 BPM, 16 quarters); named voices replace the default melody."""
    lines = quartet_lines(**{k: list(v) for k, v in voices.items()})
    return performed_of(lines)


def plan_of(
    song: PerformedSong | None = None,
    *,
    proposals: Sequence[LyricProposal] = (),
    approvals: Sequence[LyricApproval] = (),
    engine_refs: dict[VoiceRole, VoiceEngineRef] | None = None,
    voices: Mapping[str, Sequence[Note]] | None = None,
) -> SynthesisPlan:
    if song is None:
        song = performed(**(voices or full_lyrics()))
    plan = build_synthesis_plan(
        song,
        quartet_assignments(),
        source=SOURCE,
        engine_refs=engine_refs or refs(),
        proposals=proposals,
        approvals=approvals,
    )
    if not plan.meter:  # the hand-built scores carry no meter event; state the 4/4 they are in
        plan = replace(plan, meter=(MeterPoint(position=Fraction(0), beats=4, beat_type=4),))
    return plan


def humming(start: int | Fraction, pitch: Pitch) -> Note:
    return note(start, 1, pitch, lyrics=(Lyric(kind=LyricKind.HUMMING),))


__all__ = [
    "ROLES",
    "SOURCE",
    "full_lyrics",
    "humming",
    "performed",
    "plan_of",
    "refs",
    "replace",
    "sung",
    "text",
]
