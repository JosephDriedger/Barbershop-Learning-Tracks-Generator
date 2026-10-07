"""M3d2: ties, tempo, meter and lyrics over the performed traversal (whole pipeline, from XML)."""

import copy
import json
from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.lyrics import analyze_song_lyrics
from barbershop_tracks.core.musicxml import ParseResult, parse_musicxml
from barbershop_tracks.models import AttackRole, PerformedSong, Severity
from xml_builders import (
    attributes,
    extend,
    lyric_xml,
    measure,
    note,
    parse_text,
    score,
    syl,
    tempo_direction,
    text,
    tie_xml,
    tied_xml,
)

pytestmark = pytest.mark.usefixtures("no_network")

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "musicxml" / "repeats"
WHOLE = 8  # a whole note at divisions=2


def n(step: str = "C", *, ties: tuple[str, ...] = (), lyric: str = "", dur: int = WHOLE) -> str:
    tie = tie_xml(*ties)
    return note(step, 4, dur, tie=tie, notations=tied_xml(*ties), lyrics=lyric)


def sung(word: str, kind: str = "single", ext: str = "") -> str:
    return lyric_xml(syl(kind), text(word), ext)


def fwd() -> str:
    return '<barline location="left"><repeat direction="forward"/></barline>'


def back(times: str = "") -> str:
    t = f' times="{times}"' if times else ""
    return f'<barline location="right"><repeat direction="backward"{t}/></barline>'


def m(number: int, content: str, *, pre: str = "", post: str = "", first: bool = False) -> str:
    return measure(number, pre + content + post, attrs=attributes() if first else "")


def run(tmp_path: Path, *parts: str) -> ParseResult:
    return parse_text(tmp_path, score(*parts))


def performed(result: ParseResult) -> PerformedSong:
    assert result.performed is not None
    return result.performed


def codes(result: ParseResult) -> list[str]:
    return [i.code for i in result.issues]


def sources(song: PerformedSong) -> list[int]:
    """How many source notes each tie-merged attack of the first line has."""
    return [len(attack.source) for attack in song.merged[0]]


# --- ties --------------------------------------------------------------------------------------


def test_a_tie_entirely_inside_a_repeated_region_holds_on_every_pass(tmp_path: Path) -> None:
    body = m(1, n(ties=("start",)), pre=fwd(), first=True) + m(2, n(ties=("stop",)), post=back())
    result = run(tmp_path, body + m(3, n("D")))
    assert not result.issues, [str(i) for i in result.issues]
    assert sources(performed(result)) == [2, 2, 1]


def test_a_tie_start_before_a_repeat_jump_is_broken_then_held_on_the_final_pass(
    tmp_path: Path,
) -> None:
    body = (
        m(1, n("D"), pre=fwd(), first=True)
        + m(2, n(ties=("start",)), post=back())
        + m(3, n(ties=("stop",)))
    )
    result = run(tmp_path, body)
    song = performed(result)
    assert codes(result) == ["TIE_BROKEN_BY_REPEAT"]
    assert not result.issues.has_errors
    # D, C (first pass, jumped away), D, C+C (second pass, exits into measure 3)
    assert sources(song) == [1, 1, 1, 2]
    broken = song.located_issues[0]
    assert broken.issue.severity is Severity.WARNING
    assert broken.location is not None
    assert (broken.location.number, broken.location.visit) == (2, 1)
    assert broken.location.describe() == "measure 2, first visit"


def test_a_tied_to_note_at_a_repeat_start_is_a_new_attack_on_later_passes(tmp_path: Path) -> None:
    body = (
        m(1, n(ties=("start",)), first=True)
        + m(2, n(ties=("stop",)), pre=fwd())
        + m(3, n("D"), post=back())
        + m(4, n("E"))
    )
    result = run(tmp_path, body)
    song = performed(result)
    assert codes(result) == ["TIE_BROKEN_BY_REPEAT"]
    assert not result.issues.has_errors  # not an unmatched stop: the jump explains it
    # C+C (first time), D, then the second pass starts at measure 2 again: C is NOT dropped
    assert sources(song) == [2, 1, 1, 1, 1]
    enters = song.located_issues[0]
    assert enters.location is not None
    assert (enters.location.number, enters.location.visit) == (2, 2)
    assert "second visit" in str(enters)


def test_a_multi_note_tie_chain_across_a_repeat_boundary_is_cut_only_at_the_jump(
    tmp_path: Path,
) -> None:
    body = (
        m(1, n(ties=("start",)), pre=fwd(), first=True)
        + m(2, n(ties=("stop", "start")), post=back())
        + m(3, n(ties=("stop",)))
    )
    result = run(tmp_path, body)
    song = performed(result)
    assert codes(result) == ["TIE_BROKEN_BY_REPEAT"]
    assert sources(song) == [2, 3]  # pass one: the chain stops at the jump; final pass: all three
    assert song.merged[0][1].duration == 12


def test_ties_that_are_unmatched_in_the_source_are_still_reported(tmp_path: Path) -> None:
    result = run(tmp_path, m(1, n(ties=("start",)), first=True) + m(2, n("D")))
    assert codes(result) == ["TIE_UNMATCHED_START"]


def test_the_ties_of_a_repeat_free_score_are_unchanged_and_not_duplicated(tmp_path: Path) -> None:
    result = run(tmp_path, m(1, n(ties=("start",)), first=True) + m(2, n(ties=("stop",))))
    assert not result.issues
    assert sources(performed(result)) == [2]


@pytest.mark.parametrize(
    ("name", "attacks", "broken"),
    [
        ("r07_tie_out_of_repeat", 5, 1),
        ("r07c_tie_into_repeat_start", 5, 1),
        ("r07d_tie_inside_repeat", 3, 0),
    ],
)
def test_tie_fixtures_never_lose_a_sung_attack(name: str, attacks: int, broken: int) -> None:
    result = parse_musicxml(FIXTURES / f"{name}.musicxml")
    assert not result.issues.has_errors, [str(i) for i in result.issues]
    assert len(performed(result).merged[0]) == attacks
    assert codes(result).count("TIE_BROKEN_BY_REPEAT") == broken


def test_a_tie_around_the_jump_is_not_merged_and_reports_the_source_problems() -> None:
    result = parse_musicxml(FIXTURES / "r07b_tie_across_jump.musicxml")
    assert len(performed(result).merged[0]) == 5  # nothing merged, nothing dropped
    assert "TIE_BROKEN_BY_REPEAT" in codes(result)
    assert "TIE_UNMATCHED_STOP" in codes(result)  # measure 1 starts with a stop nothing leads into


# --- tempo --------------------------------------------------------------------------------------


def t(bpm: int) -> str:
    return tempo_direction(str(bpm))


def tempos(song: PerformedSong) -> list[tuple[int, int]]:
    return [(int(e.position), int(e.bpm)) for e in song.tempo_events]


def tempo_score(tmp_path: Path, *measures: str) -> ParseResult:
    return run(tmp_path, "".join(measures))


def test_a_tempo_before_the_repeat_stays_in_force(tmp_path: Path) -> None:
    result = tempo_score(
        tmp_path,
        m(1, n(), pre=t(90), first=True),
        m(2, n("D"), pre=fwd()),
        m(3, n("E"), post=back()),
    )
    song = performed(result)
    assert tempos(song) == [(0, 90)]
    tempo = song.effective_tempo_at(Fraction(20))
    assert tempo is not None
    assert tempo.bpm == 90


def test_a_tempo_at_the_repeat_start_is_declared_again_on_the_second_visit(tmp_path: Path) -> None:
    result = tempo_score(
        tmp_path, m(1, n(), pre=fwd() + t(100), first=True), m(2, n("D"), post=back())
    )
    assert tempos(performed(result)) == [(0, 100), (8, 100)]


def test_a_tempo_inside_the_repeat_occurs_again_and_carries_over_the_jump(tmp_path: Path) -> None:
    result = tempo_score(
        tmp_path,
        m(1, n(), pre=fwd(), first=True),
        m(2, n("D"), pre=t(60), post=back()),
        m(3, n("E")),
    )
    song = performed(result)
    assert tempos(song) == [(4, 60), (12, 60)]  # the explicit events, nothing synthesised
    assert song.effective_tempo_at(Fraction(3)) is None  # no tempo before the first event
    carried = song.effective_tempo_at(Fraction(8))  # the landing measure re-declares nothing
    assert carried is not None
    assert carried.bpm == 60  # carried across the jump (MuseScore re-asserts 120 here)


def test_a_tempo_changed_on_the_first_traversal_is_redeclared_after_the_jump(
    tmp_path: Path,
) -> None:
    result = tempo_score(
        tmp_path,
        m(1, n(), pre=fwd() + t(100), first=True),
        m(2, n("D"), pre=t(60), post=back()),
        m(3, n("E")),
    )
    song = performed(result)
    assert tempos(song) == [(0, 100), (4, 60), (8, 100), (12, 60)]
    landing = song.effective_tempo_at(Fraction(8))
    assert landing is not None
    assert landing.bpm == 100


def test_a_tempo_after_the_repeat_is_shifted_by_the_repeated_measures(tmp_path: Path) -> None:
    result = tempo_score(
        tmp_path,
        m(1, n(), pre=fwd(), first=True),
        m(2, n("D"), post=back()),
        m(3, n("E"), pre=t(70)),
    )
    assert tempos(performed(result)) == [(16, 70)]


def test_the_source_tempo_map_is_not_mutated(tmp_path: Path) -> None:
    result = tempo_score(
        tmp_path, m(1, n(), pre=fwd() + t(100), first=True), m(2, n("D"), post=back())
    )
    assert result.song is not None
    assert [(int(e.position), int(e.bpm)) for e in result.song.tempo_map] == [(0, 100)]


@pytest.mark.parametrize(
    "name", ["r08_tempo_inside", "r08b_tempo_before_repeat", "s02_tempo_start_marked"]
)
def test_explicit_tempo_events_equal_the_musescore_midi(name: str) -> None:
    song = performed(parse_musicxml(FIXTURES / f"{name}.musicxml"))
    oracle = json.loads((FIXTURES / f"{name}.oracle.json").read_text(encoding="utf-8"))
    expected = [(e["tick"], round(e["bpm"])) for e in oracle["tempos"]]
    assert [(int(e.position * 480), int(e.bpm)) for e in song.tempo_events] == expected


@pytest.mark.parametrize("name", ["s01_tempo_carry", "s03_tempo_after_repeat_only"])
def test_musescore_invents_a_default_tempo_we_do_not(name: str) -> None:
    song = performed(parse_musicxml(FIXTURES / f"{name}.musicxml"))
    oracle = json.loads((FIXTURES / f"{name}.oracle.json").read_text(encoding="utf-8"))
    assert {e["bpm"] for e in oracle["tempos"]} >= {120.0}  # its default, written at tick 0
    assert all(e.bpm != 120 for e in song.tempo_events)
    assert song.effective_tempo_at(Fraction(0)) is None


# --- meter ---------------------------------------------------------------------------------------


def ts(beats: int) -> str:
    return f"<attributes><time><beats>{beats}</beats><beat-type>4</beat-type></time></attributes>"


def meters(song: PerformedSong) -> list[tuple[int, int]]:
    """The explicit declarations met in the traversal: (performed position, beats)."""
    return [(int(e.signature.position), e.signature.beats) for e in song.meter_events]


def beats_at(song: PerformedSong, position: int) -> int | None:
    meter = song.effective_meter_at(Fraction(position))
    return None if meter is None else meter.beats


def test_meter_before_inside_and_after_a_repeat(tmp_path: Path) -> None:
    result = run(
        tmp_path,
        m(1, n(), first=True)
        + m(2, n("D", dur=6), pre=fwd() + ts(3))
        + m(3, n("E", dur=6), post=back())
        + m(4, n("F"), pre=ts(4)),
    )
    song = performed(result)
    assert not result.issues.has_errors, [str(i) for i in result.issues]
    # declarations: m1 4/4 @0, m2 3/4 @4, m2 again @10 (a real re-declaration), m4 4/4 @16
    assert meters(song) == [(0, 4), (4, 3), (10, 3), (16, 4)]
    assert [beats_at(song, p) for p in (0, 4, 10, 16)] == [4, 3, 3, 4]


def test_a_jump_to_a_measure_that_only_inherits_its_meter_adds_no_declaration(
    tmp_path: Path,
) -> None:
    # m1: 4/4 declared; m2: nothing (inherits 4/4); m3: 3/4 declared; m4: backward repeat -> m2
    result = run(
        tmp_path,
        m(1, n(), first=True)
        + m(2, n("D"), pre=fwd())
        + m(3, n("E", dur=6), pre=ts(3))
        + m(4, n("F", dur=6), post=back()),
    )
    song = performed(result)
    assert not result.issues.has_errors, [str(i) for i in result.issues]
    # m2 is played at 4 and again at 14; m3 really declares 3/4, so it declares again at 18
    assert meters(song) == [(0, 4), (8, 3), (18, 3)]
    assert all(e.measure_index != 1 for e in song.meter_events)  # nothing is attributed to m2
    # the meter in force is restored by the written context, not by an invented event
    assert beats_at(song, 8) == 3  # m3
    assert beats_at(song, 13) == 3  # m4
    assert beats_at(song, 14) == 4  # m2 again, back under its written 4/4
    assert beats_at(song, 18) == 3  # m3 again
    restored = song.effective_meter_at(Fraction(14))
    assert restored is not None
    assert restored.position == 14  # the start of the performed measure, not a declaration site
    assert result.song is not None
    assert [(int(s.position), s.beats) for s in result.song.time_signatures] == [(0, 4), (8, 3)]


def test_a_measure_that_declares_its_meter_replays_that_declaration_on_a_revisit(
    tmp_path: Path,
) -> None:
    # m1 4/4; m2 declares 3/4; m3 inherits it; m4 declares 4/4; backward repeat -> m2
    result = run(
        tmp_path,
        m(1, n(), first=True)
        + m(2, n("D", dur=6), pre=fwd() + ts(3))
        + m(3, n("E", dur=6))
        + m(4, n("F"), pre=ts(4), post=back()),
    )
    song = performed(result)
    assert meters(song) == [(0, 4), (4, 3), (10, 4), (14, 3), (20, 4)]
    redeclared = [e for e in song.meter_events if e.measure_index == 1]
    assert [e.visit for e in redeclared] == [1, 2]  # a real declaration, met twice
    assert all(e.measure_index != 2 for e in song.meter_events)  # m3 inherits: no event, ever
    assert [beats_at(song, p) for p in (7, 17)] == [3, 3]


def test_the_meter_before_the_first_declaration_is_unknown(tmp_path: Path) -> None:
    result = run(tmp_path, m(1, n(), first=True))
    assert beats_at(performed(result), 0) == 4


@pytest.mark.parametrize("name", ["r09_meter_inside", "s04_meter_carry"])
def test_meter_matches_the_musescore_midi_as_declarations_and_as_effective_state(
    name: str,
) -> None:
    # MuseScore's MIDI shows the playback result only. Its signature events line up with our
    # explicit declarations here because both fixtures declare their meters in the repeated
    # region; effective_meter_at is checked separately, as the model's own state.
    song = performed(parse_musicxml(FIXTURES / f"{name}.musicxml"))
    oracle = json.loads((FIXTURES / f"{name}.oracle.json").read_text(encoding="utf-8"))
    expected = [(e["tick"], e["signature"]) for e in oracle["time_signatures"]]
    declared = [
        (int(e.signature.position * 480), f"{e.signature.beats}/{e.signature.beat_type}")
        for e in song.meter_events
    ]
    assert declared == expected
    for tick, signature in expected:
        meter = song.effective_meter_at(Fraction(tick, 480))
        assert meter is not None
        assert f"{meter.beats}/{meter.beat_type}" == signature


def test_the_source_meter_map_is_not_mutated(tmp_path: Path) -> None:
    result = run(tmp_path, m(1, n(), pre=fwd(), first=True) + m(2, n("D"), pre=ts(3), post=back()))
    assert result.song is not None
    assert len(result.song.time_signatures) == 2  # the written declarations only


# --- lyrics --------------------------------------------------------------------------------------


def lyrics(song: PerformedSong, verse: str | None = None):  # type: ignore[no-untyped-def]
    return analyze_song_lyrics(song, verse=verse).lines[0]


def roles(analysis) -> list[AttackRole]:  # type: ignore[no-untyped-def]
    return [a.role for a in analysis.attacks]


def test_repeated_lyrics_are_sung_again_on_the_second_visit(tmp_path: Path) -> None:
    body = (
        m(1, n(lyric=sung("la")), pre=fwd(), first=True)
        + m(2, n("D", lyric=sung("ni")), post=back())
        + m(3, n("E", lyric=sung("do")))
    )
    result = run(tmp_path, body)
    analysis = lyrics(performed(result))
    assert [w.text for w in analysis.words] == ["la", "ni", "la", "ni", "do"]
    assert analysis.coverage.syllable_attacks == 5  # coverage is over the performed order
    assert not analysis.issues


def test_an_untyped_melisma_is_not_carried_across_a_repeat_jump(tmp_path: Path) -> None:
    body = (
        m(1, n("D"), pre=fwd(), first=True)  # no lyric
        + m(2, n(lyric=sung("la", ext=extend())), post=back())
        + m(3, n("E", lyric=sung("do")))
    )
    analysis = lyrics(performed(run(tmp_path, body)))
    assert roles(analysis) == [
        AttackRole.MISSING,
        AttackRole.SYLLABLE,
        AttackRole.MISSING,  # NOT a continuation of the extender before the jump
        AttackRole.SYLLABLE,
        AttackRole.SYLLABLE,
    ]
    assert "LYRIC_MELISMA_INTERRUPTED" in [i.code for i in analysis.issues]


def test_a_typed_extension_open_at_a_jump_is_unclosed_then_fresh_on_the_next_visit(
    tmp_path: Path,
) -> None:
    stop = lyric_xml(extend("stop"))
    body = (
        m(1, n("D"), pre=fwd(), first=True)
        + m(2, n(lyric=sung("la", ext=extend("start"))), post=back())
        + m(3, n("E", lyric=stop))
    )
    analysis = lyrics(performed(run(tmp_path, body)))
    assert [i.code for i in analysis.issues].count("LYRIC_MELISMA_UNCLOSED") == 1
    assert "LYRIC_EXTEND_WITHOUT_START" not in [i.code for i in analysis.issues]
    assert analysis.attacks[2].role is AttackRole.MISSING  # not a continuation across the jump
    assert analysis.attacks[-1].role is AttackRole.MELISMA_CONTINUATION  # the final pass closes it
    unclosed = next(i for i in analysis.located if i.issue.code == "LYRIC_MELISMA_UNCLOSED")
    assert unclosed.location is not None
    assert (unclosed.location.number, unclosed.location.visit) == (2, 1)


def test_a_word_is_not_joined_across_a_repeat_jump(tmp_path: Path) -> None:
    body = (
        m(1, n("D", lyric=sung("x")), pre=fwd(), first=True)
        + m(2, n(lyric=sung("ba", "begin")), post=back())
        + m(3, n("E", lyric=sung("na", "end")))
    )
    analysis = lyrics(performed(run(tmp_path, body)))
    texts = [(w.text, w.closed) for w in analysis.words]
    assert ("ba", False) in texts  # cut by the jump
    assert ("bana", True) in texts  # the final pass reads it whole
    assert "bax" not in [w.text for w in analysis.words]
    unclosed = [i for i in analysis.located if i.issue.code == "LYRIC_WORD_UNCLOSED"]
    assert len(unclosed) == 1
    assert unclosed[0].issue.severity is Severity.ERROR


def test_a_landing_end_syllable_is_unopened_not_joined_to_the_pass_before(tmp_path: Path) -> None:
    body = (
        m(1, n("D", lyric=sung("na", "end")), pre=fwd(), first=True)
        + m(2, n(lyric=sung("ba", "begin")), post=back())
        + m(3, n("E", lyric=sung("do")))
    )
    analysis = lyrics(performed(run(tmp_path, body)))
    # pass 1: the END at measure 1 has no BEGIN; pass 2: BEGIN, jump, END is unopened again...
    assert "LYRIC_WORD_UNOPENED" in [i.code for i in analysis.issues]


def test_lyric_less_lines_and_coverage_use_the_performed_attack_count(tmp_path: Path) -> None:
    body = m(1, n(), pre=fwd(), first=True) + m(2, n("D"), post=back(times="3"))
    analysis = lyrics(performed(run(tmp_path, body)))
    assert analysis.coverage.sung_attacks == 6
    assert [i.code for i in analysis.issues] == ["LYRIC_LINE_EMPTY"]


def test_a_song_is_analyzed_literally_and_a_performed_song_over_the_traversal(
    tmp_path: Path,
) -> None:
    body = m(1, n(lyric=sung("la")), pre=fwd(), first=True) + m(2, n("D"), post=back())
    result = run(tmp_path, body)
    assert result.song is not None
    literal = analyze_song_lyrics(result.song)
    traversal = analyze_song_lyrics(performed(result))
    assert len(literal.lines[0].attacks) == 2  # written order, no expansion
    assert len(traversal.lines[0].attacks) == 4  # the performed order, both visits


def test_without_repeats_the_two_forms_agree(tmp_path: Path) -> None:
    result = run(tmp_path, m(1, n(lyric=sung("la")), first=True) + m(2, n("D")))
    assert result.song is not None
    a = analyze_song_lyrics(result.song).lines[0]
    b = analyze_song_lyrics(performed(result)).lines[0]
    assert roles(a) == roles(b)
    assert [w.text for w in a.words] == [w.text for w in b.words]


# --- provenance and immutability -----------------------------------------------------------------


def test_the_whole_pipeline_leaves_the_source_song_unchanged(tmp_path: Path) -> None:
    body = (
        m(1, n(ties=("start",), lyric=sung("la")), pre=fwd() + t(90), first=True)
        + m(2, n(ties=("stop",)), post=back())
        + m(3, n("E"))
    )
    result = run(tmp_path, body)
    assert result.song is not None
    before = copy.deepcopy(result.song)
    analyze_song_lyrics(performed(result))
    analyze_song_lyrics(result.song)
    assert result.song == before
    assert performed(result).song is result.song


def test_performed_attacks_keep_distinct_provenance_per_visit(tmp_path: Path) -> None:
    body = m(1, n(), pre=fwd(), first=True) + m(2, n("D"), post=back(times="3"))
    song = performed(run(tmp_path, body))
    line = song.lines[0]
    attacks = song.merged[0]
    visits = [line.occurrence_of(a.source[0]).visit for a in attacks if a.source[0].measure == 1]
    assert visits == [1, 2, 3]
    locations = [song.location_of(a.source[0]) for a in attacks]
    assert [(loc.number, loc.visit) for loc in locations if loc] == [
        (1, 1),
        (2, 1),
        (1, 2),
        (2, 2),
        (1, 3),
        (2, 3),
    ]


def test_performance_issues_report_the_visit_of_a_tie_problem(tmp_path: Path) -> None:
    # a tie to a different pitch on the second pass only is not possible in the source; instead
    # use an unmatched tie start inside the repeated region: it is reported on its first visit
    body = m(1, n(ties=("start",)), pre=fwd(), first=True) + m(2, n("D"), post=back())
    result = run(tmp_path, body)
    song = performed(result)
    located = [i for i in song.located_issues if i.issue.code == "TIE_UNMATCHED_START"]
    assert located
    assert all(i.location is not None for i in located)
    assert [i.location.visit for i in located if i.location] == sorted(
        i.location.visit for i in located if i.location
    )
    assert located[0].location is not None
    assert located[0].location.visit == 1
