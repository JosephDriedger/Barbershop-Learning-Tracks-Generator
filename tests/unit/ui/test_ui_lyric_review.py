import json
from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.pipeline import PipelineError, approvals_document
from barbershop_tracks.core.synthesis import LyricApproval, LyricProposal, SynthesisPlan
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.lyric_review import LyricReviewState, RowState, check_text
from synth_builders import full_lyrics, plan_of, sung


def plan(**extra: object) -> SynthesisPlan:
    voices = {
        **full_lyrics(("one", "two", "three", "four")),
        "tenor": sung(VoiceRole.TENOR, [None, "two", None, None]),
        "bass": sung(VoiceRole.BASS, [None, None, "three", "four"]),
    }
    return plan_of(voices=voices, **extra)  # type: ignore[arg-type]


def states(review: LyricReviewState) -> list[RowState]:
    return [row.state for row in review.rows]


def state() -> LyricReviewState:
    return LyricReviewState(plan(), approver="Joe")


def test_only_notes_without_a_score_lyric_are_rows() -> None:
    review = state()
    keys = [(row.role.value, str(row.start)) for row in review.rows]
    assert keys == [("tenor", "0"), ("tenor", "2"), ("tenor", "3"), ("bass", "0"), ("bass", "1")]
    assert review.unresolved == 5
    assert all(row.state is RowState.UNDECIDED for row in review.rows)


def test_rows_describe_the_note_in_musical_terms() -> None:
    row = state().rows[1]  # the tenor note at quarter 2
    assert row.where == "bar 1, beat 3"
    assert row.pitch == "E4"
    assert row.length == "1 beat"
    assert row.reason == "No lyric in the score"
    assert row.lead_text == "three"  # shown as context only


def test_typing_makes_a_draft_and_approving_makes_it_count() -> None:
    review = state()
    review.set_text(0, "la")
    assert states(review)[0] is RowState.DRAFT
    assert review.approvals() == ()  # a draft is not an approval
    assert review.approve([0]) == 1
    assert states(review)[0] is RowState.APPROVED
    (approval,) = review.approvals()
    assert (approval.role, approval.start, approval.text, approval.approved_by) == (
        VoiceRole.TENOR,
        Fraction(0),
        "la",
        "Joe",
    )
    assert review.unresolved == 4


def test_editing_an_approved_row_makes_it_a_new_draft() -> None:
    review = state()
    review.set_text(0, "la")
    review.approve([0])
    review.set_text(0, "lo")
    assert review.rows[0].state is RowState.DRAFT
    assert review.approvals() == ()


def test_rows_without_usable_text_cannot_be_approved() -> None:
    review = state()
    review.set_text(0, "+")
    review.set_text(1, "")
    assert review.rows[0].state is RowState.INVALID
    assert review.approve([0, 1, 2]) == 0
    assert review.approvals() == ()


@pytest.mark.parametrize("text", ["+", "+~", "-", "[la]", "café", " lo"])
def test_text_the_engine_cannot_take_is_reported(text: str) -> None:
    assert check_text(text)


def test_ordinary_text_is_fine() -> None:
    assert check_text("la") == ""
    assert check_text("") == ""


def test_batch_fill_sets_drafts_for_exactly_the_picked_rows() -> None:
    review = state()
    assert review.fill_text([0, 3, 4], "ba") == 3
    assert [r.text for r in review.rows] == ["ba", "", "", "ba", "ba"]
    assert review.approvals() == ()
    assert review.approve([0, 3, 4]) == 3


def test_leads_words_are_copied_only_on_request_and_stay_drafts() -> None:
    review = state()
    assert all(r.text == "" for r in review.rows)  # nothing was copied by itself
    assert review.use_lead_words([0, 1]) == 2
    assert [r.text for r in review.rows[:2]] == ["one", "three"]
    assert review.rows[0].state is RowState.DRAFT
    assert review.approvals() == ()


def test_the_lead_never_receives_its_own_words_or_another_voices() -> None:
    voices = {**full_lyrics(), "lead": sung(VoiceRole.LEAD, [None, "two", "three", "four"])}
    review = LyricReviewState(plan_of(voices=voices))
    assert [r.role for r in review.rows] == [VoiceRole.LEAD]
    assert review.rows[0].lead_text is None
    assert review.use_lead_words([0]) == 0


def test_proposals_are_shown_and_only_applied_when_asked() -> None:
    proposal = LyricProposal(
        role=VoiceRole.TENOR,
        start=Fraction(0),
        text="one",
        basis="same rhythm as the Lead",
        basis_role=VoiceRole.LEAD,
    )
    review = LyricReviewState(plan(proposals=[proposal]))
    row = review.rows[0]
    assert row.proposal == "one"
    assert row.text == ""
    assert "waiting for approval" in row.reason
    assert review.use_proposals([0, 1]) == 1  # only the row that has a proposal
    assert row.state is RowState.DRAFT
    review.approve([0])
    assert review.approvals()[0].text == "one"


def test_clear_empties_rows() -> None:
    review = state()
    review.fill_text([0, 1], "la")
    review.approve([0])
    review.clear([0, 1])
    assert all(r.state is RowState.UNDECIDED for r in review.rows[:2])


def test_approvals_round_trip_through_the_m10_file_and_keep_the_score_binding(
    tmp_path: Path,
) -> None:
    first = state()
    first.fill_text([0, 4], "la")
    first.approve([0, 4])
    path = tmp_path / "a.json"
    document = approvals_document(first.approvals(), first.source_sha256)
    path.write_text(json.dumps(document), encoding="utf-8")

    second = state()
    assert second.load_file(path) == (2, 0)
    assert [r.state for r in second.rows] == [
        RowState.APPROVED,
        RowState.UNDECIDED,
        RowState.UNDECIDED,
        RowState.UNDECIDED,
        RowState.APPROVED,
    ]
    assert second.rows[0].approved_by == "Joe"


def test_approvals_for_another_score_are_rejected(tmp_path: Path) -> None:
    review = state()
    path = tmp_path / "a.json"
    path.write_text(json.dumps(approvals_document((), "cd" * 32)), encoding="utf-8")
    with pytest.raises(PipelineError) as error:
        review.load_file(path)
    assert error.value.code == "APPROVALS_WRONG_SCORE"


def test_file_entries_for_notes_outside_the_review_are_counted_not_applied(tmp_path: Path) -> None:
    review = state()
    review.fill_text([0], "la")
    review.approve([0])
    stray = LyricApproval(role=VoiceRole.LEAD, start=Fraction(0), text="zz", approved_by="Joe")
    document = approvals_document([*review.approvals(), stray], review.source_sha256)
    path = tmp_path / "a.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    other = state()
    assert other.load_file(path) == (1, 1)
    assert other.unresolved == 4
