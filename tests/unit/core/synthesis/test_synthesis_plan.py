"""The engine-neutral SynthesisPlan: construction, roles, lyric states, review, provenance."""

from collections.abc import Callable, Sequence
from dataclasses import FrozenInstanceError
from fractions import Fraction
from functools import partial

import pytest

from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.core.synthesis import (
    VOICE_ORDER,
    LyricApproval,
    LyricProposal,
    LyricProvenance,
    LyricState,
    NoteLyric,
    ReviewReason,
    SynthesisPlan,
    SynthesisPlanError,
    VoiceEngineRef,
    build_synthesis_plan,
)
from barbershop_tracks.models import Melisma, Pitch, Step, VoiceRole
from midi_builders import performed_of
from readiness_builders import LINE_IDS, PITCHES, note, quartet_assignments, quartet_lines
from synth_builders import SOURCE, full_lyrics, humming, performed, plan_of, refs, sung, text

C4 = Pitch(Step.C, 4)


def code_of(call: Callable[[], object]) -> str:
    with pytest.raises(SynthesisPlanError) as info:
        call()
    return info.value.code


# --- construction and immutability ---


def test_a_complete_plan_is_immutable_and_ready() -> None:
    plan = plan_of()
    assert plan.is_ready
    assert plan.review_items == ()
    assert [v.role for v in plan.voices] == list(VOICE_ORDER)
    assert all(isinstance(v.notes, tuple) for v in plan.voices)
    with pytest.raises(FrozenInstanceError):
        plan.voices = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.voices[0].notes[0].midi_pitch = 1  # type: ignore[misc]


def test_exact_fraction_timing_and_the_sounding_pitch_are_preserved() -> None:
    third = Fraction(1, 3)
    lead = [note(i * third, third, PITCHES[VoiceRole.LEAD], lyrics=text("la")) for i in range(3)]
    plan = plan_of(voices={**full_lyrics(), "lead": lead})
    notes = plan.voice(VoiceRole.LEAD).notes
    assert [(n.start, n.duration) for n in notes] == [(i * third, third) for i in range(3)]
    assert all(isinstance(n.start, Fraction) for n in notes)
    assert {n.midi_pitch for n in notes} == {PITCHES[VoiceRole.LEAD].midi_note}


def test_tempo_meter_and_the_performed_length_come_from_the_performed_score() -> None:
    plan = build_synthesis_plan(
        performed(**full_lyrics()), quartet_assignments(), source=SOURCE, engine_refs=refs()
    )
    assert [(t.position, t.bpm) for t in plan.tempo] == [(Fraction(0), Fraction(100))]
    assert plan.meter == ()  # the builder never invents a meter the score does not state
    assert plan.output.performed_length == 16


# --- roles ---


def test_every_ttbb_role_must_be_mapped_once_to_a_known_unshared_line() -> None:
    song = performed(**full_lyrics())
    full = quartet_assignments()

    def build(entries: Sequence[tuple[VoiceRole, str]]) -> SynthesisPlan:
        return build_synthesis_plan(
            song, RoleAssignments(entries=tuple(entries)), source=SOURCE, engine_refs=refs()
        )

    assert code_of(lambda: build(full.entries[:3])) == "PLAN_ROLE_MISSING"
    assert code_of(lambda: build((*full.entries, (VoiceRole.LEAD, LINE_IDS[VoiceRole.BASS])))) == (
        "PLAN_ROLE_DUPLICATE"
    )
    assert code_of(lambda: build(((VoiceRole.TENOR, "P9/s1/v1"), *full.entries[1:]))) == (
        "PLAN_LINE_UNKNOWN"
    )
    shared = ((VoiceRole.TENOR, LINE_IDS[VoiceRole.LEAD]), *full.entries[1:])
    assert code_of(lambda: build(shared)) == "PLAN_LINE_SHARED"


def test_engine_references_are_required_per_voice_and_never_hard_coded() -> None:
    song = performed(**full_lyrics())
    incomplete: dict[VoiceRole, VoiceEngineRef] = {
        role: ref for role, ref in refs().items() if role is not VoiceRole.BASS
    }
    assert (
        code_of(
            lambda: build_synthesis_plan(
                song, quartet_assignments(), source=SOURCE, engine_refs=incomplete
            )
        )
        == "PLAN_ENGINE_REF"
    )

    def make(singer: str) -> VoiceEngineRef:
        return VoiceEngineRef(singer=singer, phonemizer="p.P", renderer="R")

    for bad in ("", " x", "a\nb"):
        assert code_of(partial(make, bad)) == "PLAN_ENGINE_REF"
    plan = plan_of(
        engine_refs=refs(lead=VoiceEngineRef(singer="other", phonemizer="a.B", renderer="CLASSIC"))
    )
    assert plan.engine_ref(VoiceRole.LEAD).singer == "other"
    assert plan.engine_ref(VoiceRole.TENOR).singer == "test-singer"


# --- lyric states ---


def test_score_lyrics_and_melisma_continuations_are_distinct_states() -> None:
    lead = [
        note(0, 1, PITCHES[VoiceRole.LEAD], lyrics=text("won", melisma=Melisma.UNTYPED)),
        note(1, 1, PITCHES[VoiceRole.LEAD]),  # the extender: no text of its own
        note(2, 1, PITCHES[VoiceRole.LEAD], lyrics=text("der")),
    ]
    plan = plan_of(voices={**full_lyrics(), "lead": lead})
    states = [n.lyric.state for n in plan.voice(VoiceRole.LEAD).notes]
    assert states == [LyricState.SCORE_LYRIC, LyricState.SCORE_CONTINUATION, LyricState.SCORE_LYRIC]
    continuation = plan.voice(VoiceRole.LEAD).notes[1].lyric
    assert continuation.text is None
    assert continuation.provenance.melisma_origin_start == 0
    assert continuation.provenance.melisma_basis == "untyped"
    assert plan.is_ready


def test_provenance_keeps_the_scores_evidence_for_every_lyric() -> None:
    plan = plan_of()
    first = plan.voice(VoiceRole.TENOR).notes[0].lyric
    assert first.state is LyricState.SCORE_LYRIC
    assert first.text == "one"
    assert first.provenance.line_id == LINE_IDS[VoiceRole.TENOR]
    assert first.provenance.performed_start == 0
    assert first.provenance.source_text == "one"
    assert first.provenance.analysis_role == "syllable"


def test_a_sounding_note_without_a_lyric_blocks_readiness_and_never_receives_a_default() -> None:
    plan = plan_of(
        voices={**full_lyrics(), "bass": sung(VoiceRole.BASS, ["one", None, "three", "four"])}
    )
    assert not plan.is_ready
    (item,) = plan.review_items
    assert (item.role, item.note_index, item.start, item.reason) == (
        VoiceRole.BASS,
        1,
        Fraction(1),
        ReviewReason.LYRIC_ABSENT,
    )
    absent = plan.voice(VoiceRole.BASS).notes[1].lyric
    assert absent.state is LyricState.ABSENT
    assert absent.text is None  # not "a", not the neighbour's, not anything


def test_the_lead_is_never_copied_into_harmony_parts() -> None:
    song = performed(lead=sung(VoiceRole.LEAD, ["one", "two", "three", "four"]))
    plan = plan_of(song)
    assert not plan.is_ready
    assert plan.voice(VoiceRole.LEAD).notes[0].lyric.state is LyricState.SCORE_LYRIC
    for role in (VoiceRole.TENOR, VoiceRole.BARITONE, VoiceRole.BASS):
        assert {n.lyric.state for n in plan.voice(role).notes} == {LyricState.ABSENT}
        assert all(n.lyric.text is None for n in plan.voice(role).notes)
    assert {i.role for i in plan.review_items} == {
        VoiceRole.TENOR,
        VoiceRole.BARITONE,
        VoiceRole.BASS,
    }


def test_an_inferred_proposal_is_not_an_approved_lyric() -> None:
    proposal = LyricProposal(
        role=VoiceRole.BASS,
        start=Fraction(1),
        text="two",
        basis="aligned from the Lead by identical rhythm",
        basis_role=VoiceRole.LEAD,
    )
    plan = plan_of(
        proposals=[proposal],
        voices={**full_lyrics(), "bass": sung(VoiceRole.BASS, ["one", None, "three", "four"])},
    )
    lyric = plan.voice(VoiceRole.BASS).notes[1].lyric
    assert lyric.state is LyricState.INFERRED_PROPOSAL
    assert lyric.text is None  # the proposed text is evidence for a reviewer, not a lyric
    assert lyric.proposal == proposal
    assert not plan.is_ready
    (item,) = plan.review_items
    assert item.reason is ReviewReason.LYRIC_PROPOSAL_UNAPPROVED
    assert "two" in item.detail
    assert "Lead" in item.detail or "Lead" in proposal.basis


def test_a_user_approval_resolves_the_note_and_keeps_its_basis() -> None:
    approval = LyricApproval(
        role=VoiceRole.BASS, start=Fraction(1), text="two", proposal_basis="aligned from the Lead"
    )
    plan = plan_of(
        approvals=[approval],
        voices={**full_lyrics(), "bass": sung(VoiceRole.BASS, ["one", None, "three", "four"])},
    )
    lyric = plan.voice(VoiceRole.BASS).notes[1].lyric
    assert (lyric.state, lyric.text, lyric.approval) == (LyricState.USER_APPROVED, "two", approval)
    assert lyric.provenance.analysis_role == "missing"  # what the score itself said stays on record
    assert plan.is_ready


def test_an_approval_wins_over_a_proposal_for_the_same_note() -> None:
    proposal = LyricProposal(role=VoiceRole.BASS, start=Fraction(1), text="x", basis="guess")
    approval = LyricApproval(role=VoiceRole.BASS, start=Fraction(1), text="two")
    plan = plan_of(
        proposals=[proposal],
        approvals=[approval],
        voices={**full_lyrics(), "bass": sung(VoiceRole.BASS, ["one", None, "three", "four"])},
    )
    assert plan.voice(VoiceRole.BASS).notes[1].lyric.state is LyricState.USER_APPROVED
    assert plan.is_ready


def test_decisions_never_override_the_score_and_must_hit_a_real_lyricless_note() -> None:
    bass = sung(VoiceRole.BASS, ["one", None, "three", "four"])
    voices = {**full_lyrics(), "bass": bass}

    def approve(role: VoiceRole, start: int) -> None:
        plan_of(
            approvals=[LyricApproval(role=role, start=Fraction(start), text="zzz")], voices=voices
        )

    assert code_of(lambda: approve(VoiceRole.BASS, 0)) == "PLAN_APPROVAL_OVERRIDES_SCORE"
    assert code_of(lambda: approve(VoiceRole.BASS, 7)) == "PLAN_LYRIC_TARGET_INVALID"
    assert code_of(lambda: approve(VoiceRole.TENOR, 1)) == "PLAN_APPROVAL_OVERRIDES_SCORE"
    duplicate = [
        LyricApproval(role=VoiceRole.BASS, start=Fraction(1), text=t) for t in ("a1", "b2")
    ]
    assert code_of(lambda: plan_of(approvals=duplicate, voices=voices)) == "PLAN_APPROVAL_DUPLICATE"


def test_unsupported_and_conflicting_lyric_material_blocks_instead_of_being_guessed() -> None:
    bass = [
        humming(0, PITCHES[VoiceRole.BASS]),
        *sung(VoiceRole.BASS, ["two", "three", "four"], start=1),
    ]
    plan = plan_of(voices={**full_lyrics(), "bass": bass})
    (item,) = plan.review_items
    assert item.reason is ReviewReason.LYRIC_UNSUPPORTED_SOURCE
    assert not plan.is_ready


def test_lyric_state_objects_reject_contradictory_combinations() -> None:
    prov = LyricProvenance(line_id="L", performed_start=Fraction(0), analysis_role="syllable")
    with pytest.raises(SynthesisPlanError):
        NoteLyric(state=LyricState.SCORE_LYRIC, text=None, provenance=prov)
    with pytest.raises(SynthesisPlanError):
        NoteLyric(state=LyricState.SCORE_CONTINUATION, text="x", provenance=prov)
    with pytest.raises(SynthesisPlanError):
        NoteLyric(state=LyricState.INFERRED_PROPOSAL, text=None, provenance=prov)
    with pytest.raises(SynthesisPlanError):
        NoteLyric(state=LyricState.USER_APPROVED, text="x", provenance=prov)
    with pytest.raises(SynthesisPlanError):
        LyricApproval(role=VoiceRole.BASS, start=Fraction(0), text="  ")
    with pytest.raises(SynthesisPlanError):
        LyricProposal(role=VoiceRole.BASS, start=Fraction(0), text="x", basis=" ")


# --- the score itself must be usable ---


def test_unusable_scores_fail_with_typed_errors() -> None:
    microtone = Pitch(Step.C, 4, alter=Fraction(1, 2))
    bad = {**full_lyrics(), "lead": [note(0, 4, microtone, lyrics=text("la"))]}
    assert code_of(lambda: plan_of(voices=bad)) == "PLAN_PITCH_NOT_INTEGRAL"
    overlap = {
        **full_lyrics(),
        "lead": [note(0, 2, C4, lyrics=text("a")), note(1, 1, C4, lyrics=text("b"))],
    }
    assert code_of(lambda: plan_of(voices=overlap)) in {
        "PLAN_VOICE_OVERLAP",
        "PLAN_LYRIC_ANALYSIS_MISMATCH",
    }
    empty = {**full_lyrics(), "lead": [note(0, 4, None)]}
    assert code_of(lambda: plan_of(voices=empty)) == "PLAN_VOICE_EMPTY"
    no_tempo = performed_of(quartet_lines(**full_lyrics()), tempos=[])
    assert code_of(lambda: plan_of(no_tempo)) == "PLAN_TEMPO_MISSING"
