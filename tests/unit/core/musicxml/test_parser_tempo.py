"""Tempo extraction: exact values, positions, and reconciliation across parts."""

from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.musicxml.issues import IssueCollector
from barbershop_tracks.core.musicxml.tempo import (
    TempoEvent,
    offset_element,
    parse_tempo_value,
    reconcile_tempos,
)
from barbershop_tracks.models import Severity
from xml_builders import (
    attributes,
    backup,
    measure,
    note,
    parse_text,
    quarters,
    score,
    tempo_direction,
)

pytestmark = pytest.mark.usefixtures("no_network")

F = Fraction
FOUR = quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4))


def _parse(tmp_path: Path, *parts: str) -> ParseResult:
    return parse_text(tmp_path, score(*parts))


def _tempos(result: ParseResult) -> list[tuple[Fraction, Fraction]]:
    assert result.song is not None
    return [(t.position, t.bpm) for t in result.song.tempo_map]


def _codes(result: ParseResult) -> list[str]:
    return [issue.code for issue in result.issues]


def _m(body: str, number: int = 1, first: bool = True) -> str:
    return measure(number, body, attrs=attributes() if first else "")


# --- basic extraction -------------------------------------------------------------------


def test_no_tempo_gives_an_empty_map_and_no_default(tmp_path: Path) -> None:
    result = _parse(tmp_path, _m(FOUR))
    assert _tempos(result) == []
    assert not result.issues  # missing tempo is not a parse problem (M4 reports TEMPO_MISSING)


def test_tempo_at_the_start_of_a_measure(tmp_path: Path) -> None:
    result = _parse(tmp_path, _m(tempo_direction("96") + FOUR))
    assert _tempos(result) == [(F(0), F(96))]
    assert not result.issues


def test_tempo_in_the_middle_of_a_measure(tmp_path: Path) -> None:
    body = quarters(("C", 4), ("D", 4)) + tempo_direction("60") + quarters(("E", 4), ("F", 4))
    assert _tempos(_parse(tmp_path, _m(body))) == [(F(2), F(60))]


def test_two_tempo_changes_in_one_measure(tmp_path: Path) -> None:
    body = (
        tempo_direction("120")
        + quarters(("C", 4))
        + tempo_direction("90")
        + quarters(("D", 4), ("E", 4))
        + tempo_direction("60")
        + quarters(("F", 4))
    )
    assert _tempos(_parse(tmp_path, _m(body))) == [(F(0), F(120)), (F(1), F(90)), (F(3), F(60))]


def test_tempo_in_a_later_measure_has_a_global_position(tmp_path: Path) -> None:
    m2 = _m(tempo_direction("72") + FOUR, number=2, first=False)
    assert _tempos(_parse(tmp_path, _m(FOUR) + m2)) == [(F(4), F(72))]


def test_tempo_after_a_backup_uses_the_cursor_position(tmp_path: Path) -> None:
    body = FOUR + backup(8) + tempo_direction("80") + quarters(("G", 3), voice="2")
    assert _tempos(_parse(tmp_path, _m(body))) == [(F(0), F(80))]


def test_tempo_in_a_pickup_measure(tmp_path: Path) -> None:
    pickup = measure(
        0, tempo_direction("100") + quarters(("G", 4)), attrs=attributes(), implicit=True
    )
    assert _tempos(_parse(tmp_path, pickup + _m(FOUR, number=1, first=False))) == [(F(0), F(100))]


def test_sound_directly_in_the_measure(tmp_path: Path) -> None:
    body = '<sound tempo="88"/>' + FOUR
    assert _tempos(_parse(tmp_path, _m(body))) == [(F(0), F(88))]


# --- exact decimals ------------------------------------------------------------------


def test_decimal_tempo_is_exact(tmp_path: Path) -> None:
    result = _parse(tmp_path, _m(tempo_direction("92.5") + FOUR))
    ((_, bpm),) = _tempos(result)
    assert bpm == F(185, 2)
    assert isinstance(bpm, Fraction)


def test_repeating_decimal_is_not_rounded(tmp_path: Path) -> None:
    result = _parse(tmp_path, _m(tempo_direction("133.333") + FOUR))
    ((_, bpm),) = _tempos(result)
    assert bpm == F(133333, 1000)  # exactly what was written, no float and no rounding


@pytest.mark.parametrize("raw", ["60", "060", "+60", "60.0", "60.000"])
def test_equivalent_spellings_give_the_same_value(tmp_path: Path, raw: str) -> None:
    ((_, bpm),) = _tempos(_parse(tmp_path, _m(tempo_direction(raw) + FOUR)))
    assert bpm == 60


# --- invalid, zero, metronome -----------------------------------------------------------


@pytest.mark.parametrize("raw", ["abc", "-5", "1e2", "1/2", "", "NaN", "60 bpm"])
def test_invalid_tempo_is_an_error_and_sets_nothing(tmp_path: Path, raw: str) -> None:
    result = _parse(tmp_path, _m(tempo_direction(raw) + FOUR))
    issue = next(i for i in result.issues if i.code == "TEMPO_INVALID")
    assert issue.severity is Severity.ERROR
    assert _tempos(result) == []


def test_tempo_zero_is_unresolved_not_a_tempo_and_never_120(tmp_path: Path) -> None:
    result = _parse(tmp_path, _m(tempo_direction("0") + FOUR))
    issue = next(i for i in result.issues if i.code == "TEMPO_ZERO_UNRESOLVED")
    assert issue.severity is Severity.WARNING
    assert (issue.part_id, issue.measure) == ("P1", 1)
    assert _tempos(result) == []
    assert not result.issues.has_errors


@pytest.mark.parametrize("raw", ["0.0", "00"])
def test_other_spellings_of_zero_are_also_unresolved(tmp_path: Path, raw: str) -> None:
    result = _parse(tmp_path, _m(tempo_direction(raw) + FOUR))
    assert "TEMPO_ZERO_UNRESOLVED" in _codes(result)
    assert _tempos(result) == []


def test_zero_does_not_cancel_an_earlier_valid_tempo(tmp_path: Path) -> None:
    body = tempo_direction("90") + quarters(("C", 4)) + tempo_direction("0") + quarters(("D", 4))
    result = _parse(tmp_path, _m(body))
    assert _tempos(result) == [(F(0), F(90))]
    assert "TEMPO_ZERO_UNRESOLVED" in _codes(result)


def test_metronome_without_sound_is_a_warning_and_sets_no_tempo(tmp_path: Path) -> None:
    result = _parse(tmp_path, _m(tempo_direction(None, metronome="96") + FOUR))
    issue = next(i for i in result.issues if i.code == "METRONOME_WITHOUT_SOUND")
    assert issue.severity is Severity.WARNING
    assert _tempos(result) == []


def test_metronome_with_sound_is_fine(tmp_path: Path) -> None:
    result = _parse(tmp_path, _m(tempo_direction("96", metronome="96") + FOUR))
    assert not result.issues
    assert _tempos(result) == [(F(0), F(96))]


def test_words_alone_never_set_a_tempo(tmp_path: Path) -> None:
    result = _parse(tmp_path, _m(tempo_direction(None, words="Allegro") + FOUR))
    assert _tempos(result) == []
    assert not result.issues


def test_metronome_value_is_not_used_when_sound_differs(tmp_path: Path) -> None:
    result = _parse(tmp_path, _m(tempo_direction("100", metronome="60") + FOUR))
    assert _tempos(result) == [(F(0), F(100))]  # only <sound tempo> is a playback tempo


# --- explicit events are kept -----------------------------------------------------------


def test_a_later_tempo_equal_to_the_previous_one_is_kept(tmp_path: Path) -> None:
    body = (
        tempo_direction("90")
        + quarters(("C", 4), ("D", 4))
        + tempo_direction("90")
        + quarters(("E", 4), ("F", 4))
    )
    assert _tempos(_parse(tmp_path, _m(body))) == [(F(0), F(90)), (F(2), F(90))]


def test_same_value_twice_at_one_position_in_one_part_is_one_event(tmp_path: Path) -> None:
    body = tempo_direction("90") + tempo_direction("90") + FOUR
    assert _tempos(_parse(tmp_path, _m(body))) == [(F(0), F(90))]


def test_different_values_at_one_position_in_one_part_conflict(tmp_path: Path) -> None:
    body = tempo_direction("90") + tempo_direction("100") + FOUR
    result = _parse(tmp_path, _m(body))
    issue = next(i for i in result.issues if i.code == "TEMPO_CONFLICT")
    assert issue.severity is Severity.ERROR
    assert _tempos(result) == []  # unresolved: nothing is chosen for the player


# --- across parts -----------------------------------------------------------------------


def test_identical_tempo_in_two_parts_is_one_event(tmp_path: Path) -> None:
    p = _m(tempo_direction("96") + FOUR)
    result = _parse(tmp_path, p, p)
    assert _tempos(result) == [(F(0), F(96))]
    assert not result.issues


def test_tempo_declared_in_only_one_part_is_used(tmp_path: Path) -> None:
    result = _parse(tmp_path, _m(tempo_direction("96") + FOUR), _m(FOUR))
    assert _tempos(result) == [(F(0), F(96))]


def test_tempos_at_different_positions_in_different_parts_are_merged_in_order(
    tmp_path: Path,
) -> None:
    p1 = _m(tempo_direction("96") + FOUR)
    p2 = _m(FOUR) + _m(tempo_direction("60") + FOUR, number=2, first=False)
    p1 = p1 + _m(FOUR, number=2, first=False)
    assert _tempos(_parse(tmp_path, p1, p2)) == [(F(0), F(96)), (F(4), F(60))]


def test_conflicting_tempos_at_the_same_global_position_are_an_error(tmp_path: Path) -> None:
    result = _parse(tmp_path, _m(tempo_direction("96") + FOUR), _m(tempo_direction("100") + FOUR))
    issue = next(i for i in result.issues if i.code == "TEMPO_CONFLICT")
    assert issue.severity is Severity.ERROR
    assert "P1" in issue.message
    assert "P2" in issue.message
    assert "96" in issue.message
    assert "100" in issue.message
    assert _tempos(result) == []
    assert result.issues.has_errors


def test_conflict_at_one_position_does_not_hide_other_tempos(tmp_path: Path) -> None:
    later = tempo_direction("70") + quarters(("C", 4))
    p1 = _m(tempo_direction("96") + FOUR) + _m(
        later + quarters(("D", 4), ("E", 4), ("F", 4)), 2, False
    )
    p2 = _m(tempo_direction("100") + FOUR) + _m(FOUR, 2, False)
    result = _parse(tmp_path, p1, p2)
    assert _tempos(result) == [(F(4), F(70))]
    assert _codes(result).count("TEMPO_CONFLICT") == 1


def test_tempo_map_is_strictly_increasing(tmp_path: Path) -> None:
    body = (
        tempo_direction("120")
        + quarters(("C", 4))
        + tempo_direction("60")
        + quarters(("D", 4), ("E", 4), ("F", 4))
    )
    positions = [p for p, _ in _tempos(_parse(tmp_path, _m(body)))]
    assert positions == sorted(set(positions))


# --- divisions interplay ----------------------------------------------------------------


def test_tempo_position_follows_the_active_divisions(tmp_path: Path) -> None:
    m1 = measure(1, quarters(("C", 4), ("D", 4), ("E", 4), ("F", 4)), attrs=attributes())
    body = tempo_direction("80") + "".join(note("G", 4, 4) for _ in range(4))
    m2 = measure(2, body, attrs=attributes(divisions="4", time=None, clefs=None))
    assert _tempos(_parse(tmp_path, m1 + m2)) == [(F(4), F(80))]


def test_tempo_before_any_divisions_is_not_misplaced(tmp_path: Path) -> None:
    body = tempo_direction("80", dir_offset='<offset sound="yes">2</offset>') + FOUR
    result = _parse(tmp_path, measure(1, body, attrs=attributes(divisions=None)))
    assert "DIVISIONS_MISSING" in _codes(result)  # an offset needs divisions; nothing is guessed
    assert _tempos(result) == []


# --- the pure helpers -------------------------------------------------------------------


def test_parse_tempo_value() -> None:
    assert parse_tempo_value("96") == 96
    assert parse_tempo_value("92.5") == F(185, 2)
    assert parse_tempo_value("0") == 0
    assert parse_tempo_value("-1") is None
    assert parse_tempo_value("1e2") is None


def test_reconcile_identical_events_across_parts() -> None:
    issues = IssueCollector()
    events = [
        TempoEvent(position=F(0), bpm=F(96), part_id="P1", measure=1),
        TempoEvent(position=F(0), bpm=F(96), part_id="P2", measure=1),
        TempoEvent(position=F(4), bpm=F(96), part_id="P1", measure=2),
    ]
    changes = reconcile_tempos(events, issues)
    assert [(c.position, c.bpm) for c in changes] == [(F(0), F(96)), (F(4), F(96))]
    assert not issues.result()


def test_reconcile_conflict_leaves_the_position_unresolved() -> None:
    issues = IssueCollector()
    events = [
        TempoEvent(position=F(0), bpm=F(96), part_id="P1", measure=1),
        TempoEvent(position=F(0), bpm=F(97), part_id="P2", measure=1),
    ]
    assert reconcile_tempos(events, issues) == ()
    assert [i.code for i in issues.result()] == ["TEMPO_CONFLICT"]


def test_offset_element_rule_is_the_specification() -> None:
    import xml.etree.ElementTree as ET

    def direction(inner: str) -> ET.Element:
        return ET.fromstring(f"<direction>{inner}</direction>")

    own = direction('<offset sound="no">1</offset><sound tempo="60"><offset>2</offset></sound>')
    sound = own.find("sound")
    assert sound is not None
    chosen = offset_element(sound, own)
    assert chosen is not None
    assert chosen.text == "2"  # the sound's own offset overrides the direction's

    yes = direction('<offset sound="yes">3</offset><sound tempo="60"/>')
    yes_sound = yes.find("sound")
    assert yes_sound is not None
    yes_offset = offset_element(yes_sound, yes)
    assert yes_offset is not None
    assert yes_offset.text == "3"

    for inner in ('<offset sound="no">3</offset>', "<offset>3</offset>", ""):
        plain = direction(f'{inner}<sound tempo="60"/>')
        plain_sound = plain.find("sound")
        assert plain_sound is not None
        assert offset_element(plain_sound, plain) is None
