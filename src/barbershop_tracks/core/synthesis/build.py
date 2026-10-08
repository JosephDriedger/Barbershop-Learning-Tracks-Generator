"""``PerformedSong`` + role assignments + lyric decisions -> ``SynthesisPlan``.

Nothing is guessed here. The M3 performed lyric analysis decides each note's lyric state; a note the
score leaves without a usable lyric stays ``ABSENT`` (a review item) unless a person approved a text
for it, and an inferred proposal never counts as approved. Score lyrics are never overridden.
"""

from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any

from barbershop_tracks.core.lyrics import analyze_song_lyrics
from barbershop_tracks.core.readiness.assignments import RoleAssignments
from barbershop_tracks.core.synthesis.errors import SynthesisPlanError
from barbershop_tracks.core.synthesis.plan import (
    VOICE_ORDER,
    LyricApproval,
    LyricProposal,
    LyricProvenance,
    LyricState,
    MeterPoint,
    NoteLyric,
    OutputRequirements,
    PlannedNote,
    SourceIdentity,
    SynthesisPlan,
    TempoPoint,
    VoiceEngineRef,
    VoicePlan,
    engine_refs_from,
)
from barbershop_tracks.models import (
    AttackLyric,
    AttackRole,
    LineLyricAnalysis,
    PerformanceNote,
    PerformedSong,
    VoiceRole,
)

_Key = tuple[VoiceRole, Fraction]


def sounding_midi_pitch(note: PerformanceNote) -> int:
    """The performed sounding pitch as a MIDI note number; anything else is an error."""
    pitch = note.pitch
    if pitch is None:
        raise SynthesisPlanError(
            "PLAN_PITCH_MISSING", f"a sounding note at {note.start} has no pitch"
        )
    height = pitch.absolute_semitones
    if height.denominator != 1:
        raise SynthesisPlanError(
            "PLAN_PITCH_NOT_INTEGRAL", f"{pitch} at {note.start} is microtonal"
        )
    if not 0 <= height <= 127:
        raise SynthesisPlanError(
            "PLAN_PITCH_OUT_OF_RANGE", f"{pitch} at {note.start} is outside 0..127"
        )
    return int(height)


def _resolve_lines(performed: PerformedSong, assignments: RoleAssignments) -> dict[VoiceRole, str]:
    chosen: dict[VoiceRole, str] = {}
    for role in VOICE_ORDER:
        lines = assignments.lines_for(role)
        if not lines:
            raise SynthesisPlanError(
                "PLAN_ROLE_MISSING", f"{role.display_name} has no assigned line"
            )
        if len(lines) > 1:
            raise SynthesisPlanError(
                "PLAN_ROLE_DUPLICATE", f"{role.display_name} has several lines"
            )
        if performed.line(lines[0]) is None:
            raise SynthesisPlanError("PLAN_LINE_UNKNOWN", f"unknown line {lines[0]}")
        chosen[role] = lines[0]
    values = list(chosen.values())
    shared = sorted({line for line in values if values.count(line) > 1})
    if shared:
        raise SynthesisPlanError(
            "PLAN_LINE_SHARED", f"one line has several roles: {', '.join(shared)}"
        )
    return chosen


def _index_decisions(
    proposals: Sequence[LyricProposal], approvals: Sequence[LyricApproval]
) -> tuple[dict[_Key, LyricProposal], dict[_Key, LyricApproval]]:
    proposed: dict[_Key, LyricProposal] = {}
    for proposal in proposals:
        key = (proposal.role, proposal.start)
        if key in proposed:
            raise SynthesisPlanError(
                "PLAN_PROPOSAL_DUPLICATE", f"two proposals for {key[0].value} at {key[1]}"
            )
        proposed[key] = proposal
    approved: dict[_Key, LyricApproval] = {}
    for approval in approvals:
        key = (approval.role, approval.start)
        if key in approved:
            raise SynthesisPlanError(
                "PLAN_APPROVAL_DUPLICATE", f"two approvals for {key[0].value} at {key[1]}"
            )
        approved[key] = approval
    return proposed, approved


def _note_lyric(
    role: VoiceRole,
    line_id: str,
    attack: AttackLyric,
    by_index: Mapping[int, AttackLyric],
    proposals: Mapping[_Key, LyricProposal],
    approvals: Mapping[_Key, LyricApproval],
    used: set[_Key],
) -> NoteLyric:
    start = attack.performed.start
    key = (role, start)
    base: dict[str, Any] = {
        "line_id": line_id,
        "performed_start": start,
        "analysis_role": attack.role.value,
    }
    if attack.role is AttackRole.SYLLABLE and attack.lyric is not None:
        if not attack.lyric.elided:
            if key in approvals or key in proposals:
                raise SynthesisPlanError(
                    "PLAN_APPROVAL_OVERRIDES_SCORE",
                    f"{role.display_name} at {start} has a score lyric; it is never overridden",
                )
            return NoteLyric(
                state=LyricState.SCORE_LYRIC,
                text=attack.lyric.text,
                provenance=LyricProvenance(
                    **base, source_text=attack.lyric.text, syllabic=attack.lyric.syllabic.value
                ),
            )
        detail = "unsupported: elision (two syllables on one note)"
    elif attack.role is AttackRole.MELISMA_CONTINUATION:
        if key in approvals or key in proposals:
            raise SynthesisPlanError(
                "PLAN_APPROVAL_OVERRIDES_SCORE",
                f"{role.display_name} at {start} is a score melisma continuation",
            )
        origin = by_index.get(attack.melisma_origin) if attack.melisma_origin is not None else None
        return NoteLyric(
            state=LyricState.SCORE_CONTINUATION,
            text=None,
            provenance=LyricProvenance(
                **base,
                melisma_origin_start=None if origin is None else origin.performed.start,
                melisma_basis=None if attack.melisma_basis is None else attack.melisma_basis.value,
            ),
        )
    elif attack.role in (AttackRole.HUMMING, AttackRole.LAUGHING):
        detail = f"unsupported: {attack.role.value} has no sung text"
    elif attack.role is AttackRole.CONFLICT:
        detail = "the score gives conflicting lyrics for this note"
    else:
        detail = "the score gives this sounding note no lyric"
    provenance = LyricProvenance(**base, detail=detail)
    approval = approvals.get(key)
    proposal = proposals.get(key)
    if approval is not None:
        used.add(key)
        return NoteLyric(
            state=LyricState.USER_APPROVED,
            text=approval.text,
            provenance=provenance,
            approval=approval,
        )
    if proposal is not None:
        used.add(key)
        return NoteLyric(
            state=LyricState.INFERRED_PROPOSAL, text=None, provenance=provenance, proposal=proposal
        )
    return NoteLyric(state=LyricState.ABSENT, text=None, provenance=provenance)


def _voice_plan(
    role: VoiceRole,
    line_id: str,
    performed: PerformedSong,
    analysis: LineLyricAnalysis,
    proposals: Mapping[_Key, LyricProposal],
    approvals: Mapping[_Key, LyricApproval],
    used: set[_Key],
) -> VoicePlan:
    sounding = sorted(
        (a for a in performed.attacks(line_id) if not a.is_rest), key=lambda a: a.start
    )
    attacks = sorted(
        (a for a in analysis.attacks if a.role is not AttackRole.REST),
        key=lambda a: a.performed.start,
    )
    if [a.start for a in sounding] != [a.performed.start for a in attacks]:
        raise SynthesisPlanError(
            "PLAN_LYRIC_ANALYSIS_MISMATCH",
            f"{role.display_name}: lyric analysis and notes disagree",
        )
    by_index = {a.index: a for a in analysis.attacks}
    notes = tuple(
        PlannedNote(
            index=i,
            start=note.start,
            duration=note.duration,
            midi_pitch=sounding_midi_pitch(note),
            lyric=_note_lyric(role, line_id, attack, by_index, proposals, approvals, used),
        )
        for i, (note, attack) in enumerate(zip(sounding, attacks, strict=True))
    )
    line = performed.line(line_id)
    name = line.part.name if line is not None else line_id
    return VoicePlan(role=role, line_id=line_id, part_name=name, notes=notes)


def build_synthesis_plan(
    performed: PerformedSong,
    assignments: RoleAssignments,
    *,
    source: SourceIdentity,
    engine_refs: Mapping[VoiceRole, VoiceEngineRef],
    verse: str | None = None,
    proposals: Sequence[LyricProposal] = (),
    approvals: Sequence[LyricApproval] = (),
) -> SynthesisPlan:
    """Build the plan; unresolved lyrics become review items, never default syllables."""
    lines = _resolve_lines(performed, assignments)
    refs = engine_refs_from(engine_refs)
    proposed, approved = _index_decisions(proposals, approvals)
    song_analysis = analyze_song_lyrics(performed, verse=verse)
    by_line = {line.part_id: line for line in song_analysis.lines}
    used: set[_Key] = set()
    voices = []
    for role in VOICE_ORDER:
        analysis = by_line.get(lines[role])
        if analysis is None:
            raise SynthesisPlanError(
                "PLAN_LYRIC_ANALYSIS_MISSING", f"no lyric analysis for {lines[role]}"
            )
        voices.append(_voice_plan(role, lines[role], performed, analysis, proposed, approved, used))
    for key in (*proposed, *approved):
        if key not in used:
            raise SynthesisPlanError(
                "PLAN_LYRIC_TARGET_INVALID",
                f"no note of {key[0].display_name} at {key[1]} lacks a score lyric",
            )
    tempo = tuple(TempoPoint(position=t.position, bpm=t.bpm) for t in performed.tempo_events)
    if not tempo or tempo[0].position != 0:
        raise SynthesisPlanError("PLAN_TEMPO_MISSING", "no tempo is declared at position zero")
    meter = tuple(
        MeterPoint(
            position=e.signature.position, beats=e.signature.beats, beat_type=e.signature.beat_type
        )
        for e in performed.meter_events
    )
    played = performed.plan
    length = played.end if played.played else performed.song.duration
    return SynthesisPlan(
        source=source,
        voices=tuple(voices),
        tempo=tempo,
        meter=meter,
        engine_refs=refs,
        output=OutputRequirements(performed_length=length),
    )
