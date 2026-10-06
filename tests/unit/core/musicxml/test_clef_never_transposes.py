"""PERMANENT regression tests: a clef octave change never changes sounding pitch.

A G clef with ``<clef-octave-change>-1</clef-octave-change>`` (the tenor treble clef) is
notation only. The sounding pitch changes only through an independently applicable
``<transpose>``, applied exactly once. These tests must stay for the life of the parser.
MuseScore 4.7.4 behaves this way (see tests/fixtures/musicxml/oracle/e1_* and e2b_*).
"""

from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml import ParseResult
from barbershop_tracks.models import IDENTITY_TRANSFORM, Note, PitchTransform
from xml_builders import attributes, measure, parse_text, quarters, score, transpose_xml

pytestmark = pytest.mark.usefixtures("no_network")


def clef(sign: str, line: int, octave_change: int) -> str:
    return (
        f"<clef><sign>{sign}</sign><line>{line}</line>"
        f"<clef-octave-change>{octave_change}</clef-octave-change></clef>"
    )


def _notes(result: ParseResult) -> tuple[Note, ...]:
    assert result.song is not None
    return result.song.parts[0].events


@pytest.mark.parametrize("octave_change", [-2, -1, 1, 2])
@pytest.mark.parametrize("sign_line", [("G", 2), ("F", 4)])
def test_clef_octave_change_alone_does_not_change_pitch(
    tmp_path: Path, sign_line: tuple[str, int], octave_change: int
) -> None:
    sign, line = sign_line
    attrs = attributes(clefs=clef(sign, line, octave_change))
    result = parse_text(tmp_path, score(measure(1, quarters(("C", 4), ("D", 4)), attrs=attrs)))
    events = _notes(result)
    assert [e.midi_note for e in events] == [60, 62]  # exactly the written pitches
    assert all(e.transform == IDENTITY_TRANSFORM for e in events)
    assert all(e.sounding_pitch == e.written_pitch for e in events)
    # ... and the clef is still preserved as notation metadata
    assert result.song is not None
    assert [c.octave_change for c in result.song.clef_changes] == [octave_change]


def test_tenor_clef_fixture_matches_the_musescore_oracle(tmp_path: Path) -> None:
    attrs = attributes(clefs=clef("G", 2, -1))
    notes = quarters(("C", 4), ("C", 5))
    events = _notes(parse_text(tmp_path, score(measure(1, notes, attrs=attrs))))
    assert [e.midi_note for e in events] == [60, 72]  # MuseScore: C4 -> 60, C5 -> 72


def test_clef_and_transpose_together_apply_transpose_exactly_once(tmp_path: Path) -> None:
    transpose = transpose_xml(chromatic="0", octave=-1)
    attrs = attributes(clefs=clef("G", 2, -1), transpose=transpose)
    result = parse_text(tmp_path, score(measure(1, quarters(("C", 4)), attrs=attrs)))
    event = _notes(result)[0]
    assert event.transform == PitchTransform(octave_change=-1)  # from <transpose> only
    assert event.midi_note == 48  # C3, as MuseScore plays it; not C2 (36)
    # The combination is not an error, a warning, or "ignored" anything.
    assert [i.code for i in result.issues] == ["MEASURE_INCOMPLETE"]


def test_transpose_without_clef_change_gives_the_same_pitch(tmp_path: Path) -> None:
    transpose = transpose_xml(chromatic="0", octave=-1)
    with_clef = attributes(clefs=clef("G", 2, -1), transpose=transpose)
    plain = attributes(transpose=transpose)
    a = _notes(
        parse_text(tmp_path, score(measure(1, quarters(("C", 4)), attrs=with_clef)), "a.musicxml")
    )
    b = _notes(
        parse_text(tmp_path, score(measure(1, quarters(("C", 4)), attrs=plain)), "b.musicxml")
    )
    assert a[0].midi_note == b[0].midi_note == 48


def test_clef_change_in_a_later_measure_never_affects_pitch(tmp_path: Path) -> None:
    four = quarters(("C", 4), ("C", 4), ("C", 4), ("C", 4))
    m1 = measure(1, four, attrs=attributes())
    m2 = measure(2, four, attrs=f"<attributes>{clef('G', 2, -1)}</attributes>")
    result = parse_text(tmp_path, score(m1 + m2))
    assert {e.midi_note for e in _notes(result)} == {60}
    assert result.song is not None
    assert [c.measure for c in result.song.clef_changes] == [1, 2]
