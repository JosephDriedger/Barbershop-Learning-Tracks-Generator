from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.models import (
    Note,
    Part,
    Pitch,
    Song,
    SourceMetadata,
    Step,
    TempoChange,
    TimeSignature,
    VoiceRole,
)


def _note(start: int, duration: int = 1) -> Note:
    return Note(
        start=Fraction(start),
        duration=Fraction(duration),
        measure=1,
        beat=Fraction(1),
        written_pitch=Pitch(Step.C, 4),
    )


# --- VoiceRole ------------------------------------------------------------------------


def test_voice_roles_are_exactly_the_four_parts() -> None:
    assert [role.name for role in VoiceRole] == ["TENOR", "LEAD", "BARITONE", "BASS"]


def test_voice_role_display_names() -> None:
    assert [role.display_name for role in VoiceRole] == ["Tenor", "Lead", "Baritone", "Bass"]


# --- Part -----------------------------------------------------------------------------


def test_part_role_is_not_inferred_from_its_name() -> None:
    part = Part(part_id="P1", name="Tenor")
    assert part.role is None
    assert Part(part_id="P2", name="Bass Voice").role is None


def test_part_role_can_be_assigned_explicitly() -> None:
    part = Part(part_id="P1", name="Voice 1")
    assigned = part.with_role(VoiceRole.LEAD)
    assert assigned.role is VoiceRole.LEAD
    assert part.role is None  # original is unchanged
    assert assigned.part_id == "P1"
    assert assigned.name == "Voice 1"


def test_part_explicit_role_may_contradict_its_name() -> None:
    part = Part(part_id="P1", name="Bass", role=VoiceRole.TENOR)
    assert part.role is VoiceRole.TENOR


def test_part_rejects_non_role() -> None:
    with pytest.raises(TypeError, match="VoiceRole"):
        Part(part_id="P1", name="x", role="tenor")  # type: ignore[arg-type]


def test_part_requires_part_id() -> None:
    with pytest.raises(ValueError, match="part_id"):
        Part(part_id="", name="x")


def test_part_events_are_kept_in_order_as_a_tuple() -> None:
    part = Part(part_id="P1", name="x", events=[_note(0), _note(1)])  # type: ignore[arg-type]
    assert isinstance(part.events, tuple)
    assert [e.start for e in part.events] == [0, 1]


def test_part_rejects_out_of_order_events() -> None:
    with pytest.raises(ValueError, match="ordered"):
        Part(part_id="P1", name="x", events=(_note(1), _note(0)))


def test_part_allows_simultaneous_events_for_the_validator_to_report() -> None:
    part = Part(part_id="P1", name="x", events=(_note(0), _note(0)))
    assert len(part.events) == 2


def test_part_end_and_sounding_notes() -> None:
    rest = Note.rest(start=Fraction(1), duration=Fraction(2), measure=1, beat=Fraction(2))
    part = Part(part_id="P1", name="x", events=(_note(0), rest))
    assert part.end == 3
    assert part.sounding_notes == (part.events[0],)
    assert Part(part_id="P2", name="empty").end == 0


# --- Song -----------------------------------------------------------------------------


def test_basic_song_construction() -> None:
    parts = tuple(
        Part(part_id=f"P{i}", name=name, events=(_note(0, 4),), role=role)
        for i, (name, role) in enumerate(
            [
                ("Tenor", VoiceRole.TENOR),
                ("Lead", VoiceRole.LEAD),
                ("Baritone", VoiceRole.BARITONE),
                ("Bass", VoiceRole.BASS),
            ]
        )
    )
    song = Song(
        title="Test Song",
        composer="A. Composer",
        arranger="B. Arranger",
        parts=parts,
        tempo_map=(TempoChange(position=Fraction(0), bpm=Fraction(96)),),
        time_signatures=(TimeSignature(position=Fraction(0), beats=4, beat_type=4),),
        source=SourceMetadata(
            path=Path("song.musicxml"), format_name="MusicXML", format_version="4.0"
        ),
    )
    assert song.title == "Test Song"
    assert song.composer == "A. Composer"
    assert song.arranger == "B. Arranger"
    assert len(song.parts) == 4
    assert song.duration == 4
    assert song.source.format_name == "MusicXML"
    assert song.parts_for_role(VoiceRole.LEAD) == (parts[1],)
    assert song.part_by_id("P3") is parts[3]
    assert song.part_by_id("missing") is None


def test_song_defaults_are_empty() -> None:
    song = Song(title="Empty")
    assert song.composer is None
    assert song.arranger is None
    assert song.parts == ()
    assert song.tempo_map == ()
    assert song.time_signatures == ()
    assert song.source == SourceMetadata()
    assert song.duration == 0


def test_song_does_not_validate_musical_content() -> None:
    # Two parts with the same role and a part with no role are the validator's concern.
    song = Song(
        title="Odd",
        parts=(
            Part(part_id="A", name="a", role=VoiceRole.BASS),
            Part(part_id="B", name="b", role=VoiceRole.BASS),
            Part(part_id="C", name="c"),
        ),
    )
    assert len(song.parts_for_role(VoiceRole.BASS)) == 2


def test_song_rejects_duplicate_part_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        Song(title="x", parts=(Part(part_id="A", name="a"), Part(part_id="A", name="b")))


def test_song_requires_ordered_tempo_and_time_signature_maps() -> None:
    with pytest.raises(ValueError, match="tempo_map"):
        Song(
            title="x",
            tempo_map=(
                TempoChange(position=Fraction(4), bpm=Fraction(90)),
                TempoChange(position=Fraction(0), bpm=Fraction(100)),
            ),
        )
    with pytest.raises(ValueError, match="time_signatures"):
        Song(
            title="x",
            time_signatures=(
                TimeSignature(position=Fraction(0), beats=4, beat_type=4),
                TimeSignature(position=Fraction(0), beats=3, beat_type=4),
            ),
        )


def test_song_is_immutable() -> None:
    song = Song(title="x")
    with pytest.raises(AttributeError):
        song.title = "y"  # type: ignore[misc]
