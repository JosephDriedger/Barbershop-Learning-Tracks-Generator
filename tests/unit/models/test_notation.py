from fractions import Fraction

import pytest

from barbershop_tracks.models import ClefChange, Part, Song, SourceLine


def test_source_line_text_form() -> None:
    line = SourceLine(part_id="P1", staff=2, voice="5")
    assert str(line) == "P1/s2/v5"


@pytest.mark.parametrize(
    ("part_id", "staff", "voice"),
    [("", 1, "1"), ("P/1", 1, "1"), ("P1", 0, "1"), ("P1", 1, ""), ("P1", 1, "1/2")],
)
def test_source_line_rejects_invalid_parts(part_id: str, staff: int, voice: str) -> None:
    with pytest.raises(ValueError, match=r"staff|part_id|voice"):
        SourceLine(part_id=part_id, staff=staff, voice=voice)


def test_voice_ids_are_opaque_strings() -> None:
    assert str(SourceLine(part_id="P1", staff=1, voice="x7")) == "P1/s1/vx7"


def test_clef_change_holds_notation_only() -> None:
    clef = ClefChange(
        part_id="P1",
        staff=1,
        sign="G",
        line=2,
        octave_change=-1,
        measure=0,
        position=Fraction(3, 2),
    )
    assert clef.octave_change == -1
    assert clef.position == Fraction(3, 2)
    assert not hasattr(clef, "pitch_transform")


def test_clef_change_defaults() -> None:
    clef = ClefChange(part_id="P1", staff=1, sign="F", measure=1, position=Fraction(0))
    assert (clef.line, clef.octave_change) == (None, 0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"staff": 0},
        {"sign": ""},
        {"line": 0},
        {"measure": -1},
        {"position": Fraction(-1)},
        {"part_id": ""},
    ],
)
def test_clef_change_validation(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "part_id": "P1",
        "staff": 1,
        "sign": "G",
        "measure": 1,
        "position": Fraction(0),
    }
    values.update(overrides)
    with pytest.raises(ValueError, match=r"."):
        ClefChange(**values)  # type: ignore[arg-type]


def test_clef_position_rejects_floats() -> None:
    with pytest.raises(TypeError, match="Fraction or int"):
        ClefChange(part_id="P1", staff=1, sign="G", measure=1, position=0.5)  # type: ignore[arg-type]


def test_part_source_line_must_match_part_id() -> None:
    line = SourceLine(part_id="P1", staff=1, voice="1")
    assert Part(part_id="P1/s1/v1", name="Tenor", source_line=line).source_line == line
    with pytest.raises(ValueError, match="source_line"):
        Part(part_id="other", name="Tenor", source_line=line)


def test_part_keeps_source_name_and_has_no_role_from_a_line() -> None:
    part = Part(part_id="x", name="TENOR LEAD", source_name="TENOR\nLEAD")
    assert part.source_name == "TENOR\nLEAD"
    assert part.role is None


def test_song_carries_clef_changes() -> None:
    clef = ClefChange(part_id="P1", staff=1, sign="G", measure=1, position=Fraction(0))
    assert Song(title="x", clef_changes=[clef]).clef_changes == (clef,)  # type: ignore[arg-type]
    assert Song(title="x").clef_changes == ()
