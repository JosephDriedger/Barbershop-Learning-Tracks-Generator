"""The song-wide time-signature map and its reconciliation across parts."""

from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.core.musicxml.issues import IssueCollector
from barbershop_tracks.core.musicxml.meter import build_meter_map
from barbershop_tracks.models import Severity
from xml_builders import attributes, measure, note, parse_text, quarters, score

pytestmark = pytest.mark.usefixtures("no_network")

F = Fraction


def _time(beats: int, beat_type: int) -> str:
    return (
        f"<attributes><time><beats>{beats}</beats>"
        f"<beat-type>{beat_type}</beat-type></time></attributes>"
    )


def _n(count: int) -> str:
    return quarters(*[("C", 4)] * count)


def _map(result: ParseResult) -> list[tuple[Fraction, int, int]]:
    assert result.song is not None
    return [(s.position, s.beats, s.beat_type) for s in result.song.time_signatures]


def _codes(result: ParseResult) -> list[str]:
    return [i.code for i in result.issues]


def _parse(tmp_path: Path, *parts: str) -> ParseResult:
    return parse_text(tmp_path, score(*parts))


# --- one part --------------------------------------------------------------------------


def test_meter_at_the_start_of_the_first_measure(tmp_path: Path) -> None:
    result = _parse(tmp_path, measure(1, _n(4), attrs=attributes()))
    assert _map(result) == [(F(0), 4, 4)]


def test_meter_change_at_a_later_measure(tmp_path: Path) -> None:
    m1 = measure(1, _n(4), attrs=attributes())
    m2 = measure(2, _n(3), attrs=_time(3, 4))
    m3 = measure(3, _n(3))
    assert _map(_parse(tmp_path, m1 + m2 + m3)) == [(F(0), 4, 4), (F(4), 3, 4)]


def test_restating_the_same_meter_adds_no_event(tmp_path: Path) -> None:
    m1 = measure(1, _n(4), attrs=attributes())
    m2 = measure(2, _n(4), attrs=_time(4, 4))
    m3 = measure(3, _n(4), attrs=_time(4, 4))
    assert _map(_parse(tmp_path, m1 + m2 + m3)) == [(F(0), 4, 4)]


def test_change_and_change_back(tmp_path: Path) -> None:
    m1 = measure(1, _n(4), attrs=attributes())
    m2 = measure(2, _n(3), attrs=_time(3, 4))
    m3 = measure(3, _n(4), attrs=_time(4, 4))
    assert _map(_parse(tmp_path, m1 + m2 + m3)) == [(F(0), 4, 4), (F(4), 3, 4), (F(7), 4, 4)]


def test_positions_with_a_pickup_are_exact(tmp_path: Path) -> None:
    pickup = measure(0, _n(1), attrs=attributes(), implicit=True)
    m1 = measure(1, _n(4))
    m2 = measure(2, _n(3), attrs=_time(3, 4))
    assert _map(_parse(tmp_path, pickup + m1 + m2)) == [(F(0), 4, 4), (F(5), 3, 4)]


def test_six_eight(tmp_path: Path) -> None:
    eighths = "".join(note("C", 4, 1) for _ in range(6))
    result = _parse(tmp_path, measure(1, eighths, attrs=attributes(time=(6, 8))))
    assert _map(result) == [(F(0), 6, 8)]


def test_meter_with_a_fractional_start_position_stays_exact(tmp_path: Path) -> None:
    triplets = "".join(note("C", 4, 1) for _ in range(3)) + note("D", 4, 3) + note("E", 4, 6)
    m1 = measure(1, triplets, attrs=attributes(divisions="3"))
    m2 = measure(2, "".join(note("C", 4, 3) for _ in range(3)), attrs=_time(3, 4))
    assert _map(_parse(tmp_path, m1 + m2)) == [(F(0), 4, 4), (F(4), 3, 4)]


def test_unsupported_meter_creates_no_map_event(tmp_path: Path) -> None:
    attrs = "<attributes><divisions>2</divisions><time><senza-misura/></time></attributes>"
    result = _parse(tmp_path, measure(1, _n(2), attrs=attrs))
    assert _map(result) == []
    assert "TIME_SIGNATURE_UNSUPPORTED" in _codes(result)


def test_mid_measure_meter_is_not_in_the_map(tmp_path: Path) -> None:
    body = _n(2) + _time(3, 4) + _n(2)
    result = _parse(tmp_path, measure(1, body, attrs=attributes()))
    assert _map(result) == [(F(0), 4, 4)]
    assert "TIME_SIGNATURE_CHANGE_MID_MEASURE" in _codes(result)


# --- several parts ---------------------------------------------------------------------


def test_identical_declarations_in_two_parts_are_one_event(tmp_path: Path) -> None:
    part = measure(1, _n(4), attrs=attributes())
    result = _parse(tmp_path, part, part)
    assert _map(result) == [(F(0), 4, 4)]
    assert not result.issues


def test_the_same_change_in_both_parts_is_one_event(tmp_path: Path) -> None:
    def part() -> str:
        return measure(1, _n(4), attrs=attributes()) + measure(2, _n(3), attrs=_time(3, 4))

    assert _map(_parse(tmp_path, part(), part())) == [(F(0), 4, 4), (F(4), 3, 4)]


def test_a_part_that_declares_nothing_inherits(tmp_path: Path) -> None:
    p1 = measure(1, _n(4), attrs=attributes()) + measure(2, _n(3), attrs=_time(3, 4))
    # P2 states 4/4 at the start, then relies on... a 3/4 declared only in P1 is a conflict.
    p2 = measure(1, _n(4), attrs=attributes()) + measure(2, _n(3))
    result = _parse(tmp_path, p1, p2)
    assert "TIME_SIGNATURE_CONFLICT" in _codes(result)  # P2 still has 4/4 in effect at measure 2


def test_declaring_in_only_the_first_part_is_fine_when_the_other_never_declares(
    tmp_path: Path,
) -> None:
    p1 = measure(1, _n(4), attrs=attributes())
    p2 = measure(1, _n(4), attrs="<attributes><divisions>2</divisions></attributes>")
    result = _parse(tmp_path, p1, p2)
    assert _map(result) == [(F(0), 4, 4)]  # the second part has no meter of its own to disagree
    assert "TIME_SIGNATURE_MISSING" in _codes(result)  # but it is reported as missing there


def test_conflicting_meters_in_two_parts_are_an_error(tmp_path: Path) -> None:
    p1 = measure(1, _n(4), attrs=attributes(time=(4, 4)))
    p2 = measure(1, _n(3), attrs=attributes(time=(3, 4)))
    result = _parse(tmp_path, p1, p2)
    issue = next(i for i in result.issues if i.code == "TIME_SIGNATURE_CONFLICT")
    assert issue.severity is Severity.ERROR
    assert issue.part_id == "P2"
    assert issue.measure == 1
    assert "4/4" in issue.message
    assert "3/4" in issue.message
    assert result.issues.has_errors


def test_a_continuing_conflict_is_reported_once_not_per_measure(tmp_path: Path) -> None:
    p1 = measure(1, _n(4), attrs=attributes(time=(4, 4))) + measure(2, _n(4)) + measure(3, _n(4))
    p2 = measure(1, _n(3), attrs=attributes(time=(3, 4))) + measure(2, _n(3)) + measure(3, _n(3))
    result = _parse(tmp_path, p1, p2)
    assert _codes(result).count("TIME_SIGNATURE_CONFLICT") == 1
    issue = next(i for i in result.issues if i.code == "TIME_SIGNATURE_CONFLICT")
    assert issue.measure == 1  # reported where it begins


def test_conflict_beginning_at_a_later_measure_is_reported_there_once(tmp_path: Path) -> None:
    # Part A is 4/4 throughout; part B switches to 3/4 at measure 3 and stays there.
    p1 = "".join(measure(i, _n(4), attrs=attributes() if i == 1 else "") for i in range(1, 7))
    p2 = (
        measure(1, _n(4), attrs=attributes())
        + measure(2, _n(4))
        + "".join(measure(i, _n(4), attrs=_time(3, 4) if i == 3 else "") for i in range(3, 7))
    )
    result = _parse(tmp_path, p1, p2)
    conflicts = [i for i in result.issues if i.code == "TIME_SIGNATURE_CONFLICT"]
    assert [i.measure for i in conflicts] == [3]
    assert conflicts[0].part_id == "P2"
    assert "part P1 has 4/4" in conflicts[0].message
    assert "part P2 has 3/4" in conflicts[0].message


def test_parts_that_change_at_different_measures_conflict(tmp_path: Path) -> None:
    p1 = measure(1, _n(4), attrs=attributes()) + measure(2, _n(3), attrs=_time(3, 4))
    p2 = (
        measure(1, _n(4), attrs=attributes())
        + measure(2, _n(4))
        + measure(3, _n(3), attrs=_time(3, 4))
    )
    result = _parse(tmp_path, p1, p2)
    assert "TIME_SIGNATURE_CONFLICT" in _codes(result)


# --- the pure helper -------------------------------------------------------------------


# --- persistent conflicts: reported when they begin or change, not on every measure ----


def _conflicts(
    meters: list[list[tuple[int, int] | None]], part_ids: list[str] | None = None
) -> list[tuple[int, str]]:
    """Run ``build_meter_map`` on equal-length 4/4 measures; return (measure, message) per error."""
    ids = part_ids or [f"P{i + 1}" for i in range(len(meters))]
    count = len(meters[0])
    issues = IssueCollector()
    build_meter_map(
        part_ids=ids,
        meters=meters,
        measure_numbers=list(range(1, count + 1)),
        measure_lengths=[F(4)] * count,
        issues=issues,
    )
    return [
        (i.measure or 0, i.message) for i in issues.result() if i.code == "TIME_SIGNATURE_CONFLICT"
    ]


A, B, C = (4, 4), (3, 4), (2, 4)


def test_conflict_that_begins_and_persists_gives_one_issue() -> None:
    found = _conflicts([[A, A, A, A, A, A], [A, A, B, B, B, B]])
    assert [m for m, _ in found] == [3]


def test_changing_conflicting_combination_gives_a_new_issue() -> None:
    # B is 3/4 from measure 3, then 2/4 from measure 5, while A stays 4/4.
    found = _conflicts([[A] * 6, [A, A, B, B, C, C]])
    assert [m for m, _ in found] == [3, 5]
    assert "part P2 has 3/4" in found[0][1]
    assert "part P2 has 2/4" in found[1][1]
    assert "part P1 has 4/4" in found[1][1]


def test_resolved_conflict_gives_no_continuing_issues() -> None:
    # B differs only at measures 3 and 4, then agrees again.
    found = _conflicts([[A] * 6, [A, A, B, B, A, A]])
    assert [m for m, _ in found] == [3]


def test_conflict_that_resolves_and_reappears_is_reported_again() -> None:
    found = _conflicts([[A] * 7, [A, B, B, A, A, B, B]])
    assert [m for m, _ in found] == [2, 6]


def test_three_parts_where_the_conflicting_state_changes() -> None:
    # P1 4/4 throughout. P2 3/4 from measure 2. P3 joins P2's 3/4 at measure 4 (the combination
    # changes: it was 4/4,3/4,4/4 and becomes 4/4,3/4,3/4) and then goes 2/4 at measure 6.
    found = _conflicts(
        [
            [A, A, A, A, A, A, A],
            [A, B, B, B, B, B, B],
            [A, A, A, B, B, C, C],
        ]
    )
    assert [m for m, _ in found] == [2, 4, 6]
    assert "part P3 has 2/4" in found[2][1]
    assert "part P2 has 3/4" in found[2][1]


def test_three_parts_with_an_unchanged_conflict_is_reported_once() -> None:
    found = _conflicts([[A] * 5, [A, B, B, B, B], [A, B, B, B, B]])
    assert [m for m, _ in found] == [2]


def test_agreement_throughout_gives_no_conflict() -> None:
    assert _conflicts([[A] * 4, [A] * 4, [A] * 4]) == []


def test_unknown_meter_in_one_part_is_not_a_conflict() -> None:
    assert _conflicts([[A] * 4, [None] * 4]) == []
    assert _conflicts([[A, A, A, A], [A, None, None, A]]) == []


def test_unknown_meter_does_not_hide_or_restart_a_continuing_conflict() -> None:
    # The conflict continues while P3's meter is unknown; the combination (P1, P2) is the same.
    found = _conflicts([[A] * 5, [A, B, B, B, B], [A, A, A, A, A]], ["P1", "P2", "P3"])
    assert [m for m, _ in found] == [2]
    unknown_gap = _conflicts([[A] * 4, [A, B, B, B], [A, None, None, None]])
    assert [m for m, _ in unknown_gap] == [2]


def test_map_follows_the_first_part_through_a_conflict() -> None:
    issues = IssueCollector()
    result = build_meter_map(
        part_ids=["P1", "P2"],
        meters=[[A, A, A], [A, B, B]],
        measure_numbers=[1, 2, 3],
        measure_lengths=[F(4)] * 3,
        issues=issues,
    )
    assert [(s.position, s.beats, s.beat_type) for s in result] == [(F(0), 4, 4)]


def test_build_meter_map_directly() -> None:
    issues = IssueCollector()
    result = build_meter_map(
        part_ids=["P1", "P2"],
        meters=[[(4, 4), (4, 4), (3, 4)], [(4, 4), (4, 4), (3, 4)]],
        measure_numbers=[1, 2, 3],
        measure_lengths=[F(4), F(4), F(3)],
        issues=issues,
    )
    assert [(s.position, s.beats, s.beat_type) for s in result] == [(F(0), 4, 4), (F(8), 3, 4)]
    assert not issues.result()


def test_build_meter_map_ignores_unknown_entries() -> None:
    issues = IssueCollector()
    result = build_meter_map(
        part_ids=["P1", "P2"],
        meters=[[(4, 4), (4, 4)], [None, None]],
        measure_numbers=[1, 2],
        measure_lengths=[F(4), F(4)],
        issues=issues,
    )
    assert [(s.beats, s.beat_type) for s in result] == [(4, 4)]


def test_build_meter_map_with_no_parts() -> None:
    assert (
        build_meter_map(
            part_ids=[], meters=[], measure_numbers=[], measure_lengths=[], issues=IssueCollector()
        )
        == ()
    )
