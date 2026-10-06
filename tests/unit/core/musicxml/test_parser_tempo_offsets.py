"""Tempo ``<offset>``: MusicXML 4.0 behavior, and the observed MuseScore divergence.

READ THIS BEFORE CHANGING TEMPO POSITIONING.

Our parser follows the MusicXML 4.0 specification:

* a ``<sound>``'s own ``<offset>`` applies (and overrides the direction's);
* a direction-level ``<offset>`` moves the sound **only when** ``sound="yes"``; with ``sound="no"``
  (the default) the sound takes effect at the current location;
* offsets are in ``divisions`` and are converted exactly; they are never clamped.

MuseScore Studio 4.7.4 behaves differently (observed in
``tests/fixtures/musicxml/tempo_ties/oracle``): it applies a direction's ``<offset>`` whatever
``sound`` says, and ignores a ``<sound>``'s own ``<offset>``. That is a MuseScore quirk. The
divergence tests below pin both behaviors so nobody "fixes" the parser to match MuseScore by
accident. If you intend to change this, change the documented policy first.
"""

import json
from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.models import Severity
from xml_builders import attributes, measure, note, parse_text, quarters, score, tempo_direction

pytestmark = pytest.mark.usefixtures("no_network")

F = Fraction
TIES = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml" / "tempo_ties"
PPQ = 480
FOUR = quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4))
AFTER_ONE_QUARTER = quarters(("C", 4))  # the direction sits at cursor = 1 quarter


def _parse(tmp_path: Path, body: str, divisions: str = "2") -> ParseResult:
    attrs = attributes(divisions=divisions)
    return parse_text(tmp_path, score(measure(1, body, attrs=attrs)))


def _positions(result: ParseResult) -> list[Fraction]:
    assert result.song is not None
    return [t.position for t in result.song.tempo_map]


def _codes(result: ParseResult) -> list[str]:
    return [i.code for i in result.issues]


# --- MusicXML 4.0 specification behavior ----------------------------------------------


def test_spec_direction_offset_without_sound_yes_does_not_move_the_tempo(tmp_path: Path) -> None:
    for offset in ('<offset sound="no">2</offset>', "<offset>2</offset>"):
        body = AFTER_ONE_QUARTER + tempo_direction("60", dir_offset=offset) + quarters(("D", 4))
        assert _positions(_parse(tmp_path, body + quarters(("E", 4), ("F", 4)))) == [F(1)]


def test_spec_direction_offset_with_sound_yes_moves_the_tempo(tmp_path: Path) -> None:
    offset = '<offset sound="yes">2</offset>'  # 2 divisions at divisions=2 = 1 quarter note
    body = AFTER_ONE_QUARTER + tempo_direction("60", dir_offset=offset) + quarters(("D", 4))
    assert _positions(_parse(tmp_path, body + quarters(("E", 4), ("F", 4)))) == [F(2)]


def test_spec_sound_own_offset_applies(tmp_path: Path) -> None:
    body = AFTER_ONE_QUARTER + tempo_direction("60", sound_offset="2") + quarters(("D", 4))
    assert _positions(_parse(tmp_path, body + quarters(("E", 4), ("F", 4)))) == [F(2)]


def test_spec_sound_own_offset_overrides_the_directions(tmp_path: Path) -> None:
    body = (
        AFTER_ONE_QUARTER
        + tempo_direction("60", dir_offset='<offset sound="yes">4</offset>', sound_offset="1")
        + quarters(("D", 4), ("E", 4), ("F", 4))
    )
    assert _positions(_parse(tmp_path, body)) == [F(1) + F(1, 2)]  # sound offset 1 = half a quarter


def test_spec_sound_own_offset_applies_even_if_the_direction_says_no(tmp_path: Path) -> None:
    body = (
        AFTER_ONE_QUARTER
        + tempo_direction("60", dir_offset='<offset sound="no">4</offset>', sound_offset="2")
        + quarters(("D", 4), ("E", 4), ("F", 4))
    )
    assert _positions(_parse(tmp_path, body)) == [F(2)]


# --- exact conversion through divisions -----------------------------------------------


def test_zero_offset_is_the_cursor(tmp_path: Path) -> None:
    body = (
        AFTER_ONE_QUARTER
        + tempo_direction("60", sound_offset="0")
        + quarters(("D", 4), ("E", 4), ("F", 4))
    )
    assert _positions(_parse(tmp_path, body)) == [F(1)]


def test_positive_offset(tmp_path: Path) -> None:
    body = tempo_direction("60", sound_offset="4") + FOUR
    assert _positions(_parse(tmp_path, body)) == [F(2)]


def test_fractional_quarter_offset_through_divisions(tmp_path: Path) -> None:
    body = tempo_direction("60", sound_offset="1") + FOUR  # divisions=2: 1/2 quarter
    assert _positions(_parse(tmp_path, body)) == [F(1, 2)]


def test_offset_through_divisions_three_is_an_exact_third(tmp_path: Path) -> None:
    body = (
        tempo_direction("60", sound_offset="1")
        + "".join(note(s, 4, 3) for s in "CDEF")  # divisions=3: 3 per quarter
    )
    (position,) = _positions(_parse(tmp_path, body, divisions="3"))
    assert position == F(1, 3)  # not 0.333...: exact


def test_negative_offset_within_the_measure(tmp_path: Path) -> None:
    body = (
        quarters(("C", 4), ("D", 4))
        + tempo_direction("60", sound_offset="-2")
        + quarters(("E", 4), ("F", 4))
    )
    assert _positions(_parse(tmp_path, body)) == [F(1)]


def test_decimal_offset_is_exact(tmp_path: Path) -> None:
    body = tempo_direction("60", sound_offset="0.5") + FOUR
    assert _positions(_parse(tmp_path, body)) == [F(1, 4)]


def test_offset_to_exactly_the_end_of_the_measure_is_allowed(tmp_path: Path) -> None:
    body = tempo_direction("60", sound_offset="8") + FOUR  # 8 divisions = 4 quarters = measure
    result = _parse(tmp_path, body)
    assert _positions(result) == [F(4)]
    assert not result.issues


# --- never clamped: invalid positions are located errors -------------------------------


@pytest.mark.parametrize("offset", ["9", "100", "-1"])
def test_offset_outside_the_measure_is_an_error_and_is_not_clamped(
    tmp_path: Path, offset: str
) -> None:
    result = _parse(tmp_path, tempo_direction("60", sound_offset=offset) + FOUR)
    issue = next(i for i in result.issues if i.code == "TEMPO_OFFSET_OUT_OF_MEASURE")
    assert issue.severity is Severity.ERROR
    assert (issue.part_id, issue.measure) == ("P1", 1)
    assert _positions(result) == []  # no tempo was placed at a clamped position
    assert result.issues.has_errors


def test_out_of_measure_offset_in_a_later_measure_reports_that_measure(tmp_path: Path) -> None:
    m1 = measure(1, FOUR, attrs=attributes())
    m2 = measure(2, tempo_direction("60", sound_offset="-4") + FOUR)
    result = parse_text(tmp_path, score(m1 + m2))
    issue = next(i for i in result.issues if i.code == "TEMPO_OFFSET_OUT_OF_MEASURE")
    assert issue.measure == 2


@pytest.mark.parametrize("raw", ["abc", "1/2", "1e1", " "])
def test_unusable_offset_text_is_an_error(tmp_path: Path, raw: str) -> None:
    result = _parse(tmp_path, tempo_direction("60", sound_offset=raw) + FOUR)
    assert "TEMPO_INVALID" in _codes(result)
    assert _positions(result) == []


def test_offset_uses_the_divisions_in_force_at_the_direction(tmp_path: Path) -> None:
    m1 = measure(1, FOUR, attrs=attributes())
    m2_attrs = attributes(divisions="4", time=None, clefs=None)
    body = tempo_direction("60", sound_offset="4") + "".join(note("G", 4, 4) for _ in range(4))
    m2 = measure(2, body, attrs=m2_attrs)
    assert _positions(parse_text(tmp_path, score(m1 + m2))) == [F(4) + F(1)]


# --- observed MuseScore divergence (documented; do not "fix" to match MuseScore) -------


def _oracle_tempo_ticks(name: str) -> list[int]:
    data = json.loads((TIES / "oracle" / f"{name}.json").read_text())
    return [t["tick"] for t in data["tempos"] if t["tick"] > 0]  # tick 0 is MuseScore's default


def _our_ticks(name: str) -> list[int]:
    result = parse_musicxml(TIES / "inputs" / f"{name}.musicxml")
    assert result.song is not None
    ticks = [t.position * PPQ for t in result.song.tempo_map]
    assert all(t.denominator == 1 for t in ticks)
    return [int(t) for t in ticks]


def test_agreement_tempo_between_notes_without_an_offset() -> None:
    assert _our_ticks("t_a_at_cursor") == _oracle_tempo_ticks("t_a_at_cursor") == [960]


def test_agreement_direction_offset_with_sound_yes() -> None:
    assert _our_ticks("t_c_dir_offset_yes") == _oracle_tempo_ticks("t_c_dir_offset_yes") == [960]


@pytest.mark.parametrize("name", ["t_b_dir_offset_no", "t_e_dir_offset_default"])
def test_divergence_direction_offset_without_sound_yes(name: str) -> None:
    # MusicXML 4.0: sound is "no" (the default), so the tempo stays at the cursor (tick 480).
    # MuseScore applies the direction's offset anyway and puts it at tick 960.
    assert _our_ticks(name) == [480]
    assert _oracle_tempo_ticks(name) == [960]


def test_divergence_sound_own_offset() -> None:
    # MusicXML 4.0: the <sound>'s own offset applies (cursor 480 + 480 = tick 960).
    # MuseScore ignores it and leaves the tempo at the cursor (tick 480).
    assert _our_ticks("t_d_sound_offset") == [960]
    assert _oracle_tempo_ticks("t_d_sound_offset") == [480]


def test_divergence_zero_tempo_is_unresolved_where_musescore_uses_its_default() -> None:
    result = parse_musicxml(TIES / "inputs" / "t_h_zero.musicxml")
    assert result.song is not None
    assert result.song.tempo_map == ()
    assert "TEMPO_ZERO_UNRESOLVED" in _codes(result)
    data = json.loads((TIES / "oracle" / "t_h_zero.json").read_text())
    assert data["tempos"] == [{"tick": 0, "microseconds_per_quarter": 500000}]  # MuseScore's 120


def test_agreement_decimal_and_multiple_tempos() -> None:
    decimal = parse_musicxml(TIES / "inputs" / "t_g_decimal.musicxml")
    assert decimal.song is not None
    assert [t.bpm for t in decimal.song.tempo_map] == [F(185, 2)]
    data = json.loads((TIES / "oracle" / "t_g_decimal.json").read_text())
    expected = F(60_000_000) / F(185, 2)
    assert abs(F(data["tempos"][0]["microseconds_per_quarter"]) - expected) < 1  # exact rationals

    two = parse_musicxml(TIES / "inputs" / "t_f_two_changes.musicxml")
    assert two.song is not None
    assert [int(t.position * PPQ) for t in two.song.tempo_map] == [0, 960]
    assert [t.bpm for t in two.song.tempo_map] == [F(60), F(90)]
