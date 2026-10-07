"""M3e2: ties, tempo, meter and lyrics through selected endings (whole pipeline, from XML)."""

from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.lyrics import analyze_song_lyrics
from barbershop_tracks.core.musicxml import ParseResult
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

WHOLE = 8  # a whole note at divisions=2


def n(step: str = "C", *, ties: tuple[str, ...] = (), lyric: str = "", dur: int = WHOLE) -> str:
    return note(step, 4, dur, tie=tie_xml(*ties), notations=tied_xml(*ties), lyrics=lyric)


def sung(word: str, kind: str = "single", ext: str = "") -> str:
    return lyric_xml(syl(kind), text(word), ext)


def bar(inner: str, location: str = "right") -> str:
    return f'<barline location="{location}">{inner}</barline>'


def fwd() -> str:
    return bar('<repeat direction="forward"/>', "left")


def start(number: str) -> str:
    return bar(f'<ending number="{number}" type="start"/>', "left")


def close(number: str, *, repeat: bool = False, kind: str | None = None) -> str:
    rep = '<repeat direction="backward"/>' if repeat else ""
    kind = kind or ("stop" if repeat else "discontinue")
    return bar(f'<ending number="{number}" type="{kind}"/>{rep}')


def m(number: int, content: str, *, pre: str = "", post: str = "", first: bool = False) -> str:
    return measure(number, pre + content + post, attrs=attributes() if first else "")


def voltas(
    body_last: str,
    first: str,
    second: str,
    *,
    body_first: str | None = None,
    tail: str | None = None,
    pre_body: str = "",
) -> str:
    """|: [body: m1, m2] [1. m3 :| [2. m4 | m5 (each argument is the note XML of that measure)."""
    return (
        m(1, body_first or n("C"), pre=fwd() + pre_body, first=True)
        + m(2, body_last)
        + m(3, first, pre=start("1"), post=close("1", repeat=True))
        + m(4, second, pre=start("2"), post=close("2"))
        + m(5, tail or n("G"))
    )


def run(tmp_path: Path, *parts: str) -> ParseResult:
    return parse_text(tmp_path, score(*parts))


def performed(result: ParseResult) -> PerformedSong:
    assert result.performed is not None
    return result.performed


def codes(result: ParseResult) -> list[str]:
    return [i.code for i in result.issues]


def sources(song: PerformedSong) -> list[int]:
    return [len(attack.source) for attack in song.merged[0]]


# --- ties --------------------------------------------------------------------------------------


def test_the_authoritative_set_drives_both_tie_codes(tmp_path: Path) -> None:
    result = run(tmp_path, voltas(n("D"), n("E"), n("F")))
    assert not result.issues
    assert performed(result).plan.discontinuity_positions == {Fraction(12), Fraction(20)}


def test_a_tie_entirely_inside_the_first_ending_holds(tmp_path: Path) -> None:
    body = (
        m(1, n("C"), pre=fwd(), first=True)
        + m(2, n("D"))
        + m(3, n("E", ties=("start",)), pre=start("1"))
        + m(4, n("E", ties=("stop",)), post=close("1", repeat=True))
        + m(5, n("F"), pre=start("2"), post=close("2"))
        + m(6, n("G"))
    )
    result = run(tmp_path, body)
    assert not result.issues, [str(i) for i in result.issues]
    assert sources(performed(result)) == [1, 1, 2, 1, 1, 1, 1]  # the pair holds on its pass


def test_a_tie_entirely_inside_the_final_ending_holds(tmp_path: Path) -> None:
    body = (
        m(1, n("C"), pre=fwd(), first=True)
        + m(2, n("D"))
        + m(3, n("E"), pre=start("1"), post=close("1", repeat=True))
        + m(4, n("F", ties=("start",)), pre=start("2"))
        + m(5, n("F", ties=("stop",)), post=close("2"))
        + m(6, n("G"))
    )
    result = run(tmp_path, body)
    assert not result.issues, [str(i) for i in result.issues]
    assert sources(performed(result)) == [1, 1, 1, 1, 1, 2, 1]


def test_a_tie_from_the_body_into_the_selected_first_ending_holds(tmp_path: Path) -> None:
    body = voltas(n("E", ties=("start",)), n("E", ties=("stop",)), n("F"), body_first=n("C"))
    result = run(tmp_path, body)
    song = performed(result)
    # pass 1 merges body end + ending 1; pass 2 skips to ending 2 whose note is not tied
    assert sources(song)[:3] == [1, 2, 1]


def test_a_tie_into_a_later_ending_after_a_skip_is_cut_and_the_attack_is_kept(
    tmp_path: Path,
) -> None:
    # the body's last note is tied into BOTH endings (as engraved), pass 2 skips ending 1
    body = voltas(n("E", ties=("start",)), n("E", ties=("stop",)), n("E", ties=("stop",)))
    result = run(tmp_path, body)
    song = performed(result)
    assert codes(result).count("TIE_BROKEN_BY_ENDING") == 2  # the tie leaves, and arrives
    assert not result.issues.has_errors
    # C D+E(ending 1) | C D, then E (ending 2) as its own attack, then G
    attacks = [(a.start, len(a.source)) for a in song.merged[0]]
    assert (Fraction(24), 1) in attacks  # the destination of the cut tie is still an attack
    located = [i for i in song.located_issues if i.issue.code == "TIE_BROKEN_BY_ENDING"]
    assert all(i.issue.severity is Severity.WARNING for i in located)


def test_a_tie_leaving_the_first_ending_toward_the_repeat_jump_is_cut(tmp_path: Path) -> None:
    # ending 1 ends with a tie-start into the (unrelated) next written measure, ending 2
    body = voltas(n("D"), n("E", ties=("start",)), n("E", ties=("stop",)))
    result = run(tmp_path, body)
    assert "TIE_BROKEN_BY_REPEAT" in codes(result)  # leaving ending 1: a repeat jump follows
    assert "TIE_BROKEN_BY_ENDING" in codes(result)  # arriving at ending 2: the destination
    assert not result.issues.has_errors


def test_a_tie_from_a_skipped_first_ending_toward_the_second_is_not_held(tmp_path: Path) -> None:
    # w02 layout: ending 1's note is tied to ending 2's; pass 2 never plays ending 1
    result = run(tmp_path, voltas(n("D"), n("E", ties=("start",)), n("E", ties=("stop",))))
    song = performed(result)
    ending_two = [a for a in song.merged[0] if a.source[0].measure == 4]
    assert len(ending_two) == 1
    assert len(ending_two[0].source) == 1  # a new attack, not swallowed into a missing tie


def test_a_multi_note_chain_intersecting_an_ending_skip(tmp_path: Path) -> None:
    body = voltas(
        n("E", ties=("start",)),
        n("E", ties=("stop", "start")),
        n("E", ties=("stop",)),
    )
    result = run(tmp_path, body)
    song = performed(result)
    # pass 1: body-end + ending 1 chain, cut at the repeat jump; pass 2: body-end alone, then the
    # destination attack in ending 2 (cut by the skip)
    counts = sources(song)
    assert counts[:2] == [1, 2]  # C, then D+E merged in pass 1
    assert max(counts) == 2  # nothing merged across a discontinuity
    assert sum(counts) == 7  # every source note of the performed order is in exactly one attack


def test_ties_across_the_final_exit_survive(tmp_path: Path) -> None:
    body = voltas(n("D"), n("E"), n("F", ties=("start",)), tail=n("F", ties=("stop",)))
    result = run(tmp_path, body)
    assert not result.issues
    assert sources(performed(result))[-1] == 2  # ending 2 tied into the next written measure


def test_a_tie_warning_in_an_ending_is_structurally_locatable(tmp_path: Path) -> None:
    body = voltas(n("E", ties=("start",)), n("E", ties=("stop",)), n("E", ties=("stop",)))
    song = performed(run(tmp_path, body))
    arrives = [
        i
        for i in song.located_issues
        if i.issue.code == "TIE_BROKEN_BY_ENDING" and i.location and i.location.endings == (2,)
    ]
    assert len(arrives) == 1
    location = arrives[0].location
    assert location is not None
    assert location.number == 4
    assert location.measure_index == 3
    assert location.visit == 1
    assert location.repeat_pass == 2
    assert location.endings == (2,)
    assert "ending 2" in location.describe()


# --- tempo --------------------------------------------------------------------------------------


def t(bpm: int) -> str:
    return tempo_direction(str(bpm))


def tempos(song: PerformedSong) -> list[tuple[int, int]]:
    return [(int(e.position), int(e.bpm)) for e in song.tempo_events]


def with_tempo(step: str, bpm: int) -> str:
    return t(bpm) + n(step)  # the direction comes first: it applies to this measure's start


def test_a_tempo_in_the_first_ending_only_occurs_on_pass_one(tmp_path: Path) -> None:
    song = performed(run(tmp_path, voltas(n("D"), with_tempo("E", 60), n("F"))))
    assert tempos(song) == [(8, 60)]  # ending 1 is performed once, at measure 3


def test_a_tempo_in_the_second_ending_only_occurs_on_pass_two(tmp_path: Path) -> None:
    song = performed(run(tmp_path, voltas(n("D"), n("E"), with_tempo("F", 70))))
    assert tempos(song) == [(20, 70)]


def test_the_tempo_before_the_endings_is_carried_into_the_selected_ending(tmp_path: Path) -> None:
    song = performed(run(tmp_path, voltas(n("D"), n("E"), n("F"), body_first=with_tempo("C", 90))))
    assert tempos(song) == [(0, 90), (12, 90)]  # the body declares it again on pass two only
    landing = song.effective_tempo_at(Fraction(20))  # ending 2
    assert landing is not None
    assert landing.bpm == 90
    assert all(not (16 < e.position < 24) for e in song.tempo_events)  # nothing invented there


def test_a_tempo_from_the_skipped_ending_is_never_replayed(tmp_path: Path) -> None:
    song = performed(run(tmp_path, voltas(n("D"), with_tempo("E", 60), n("F"))))
    assert song.effective_tempo_at(Fraction(20)) is not None  # carried as state ...
    assert tempos(song) == [(8, 60)]  # ... but never re-declared in ending 2


# --- meter -------------------------------------------------------------------------------------


def ts(beats: int) -> str:
    return f"<attributes><time><beats>{beats}</beats><beat-type>4</beat-type></time></attributes>"


def meters(song: PerformedSong) -> list[tuple[int, int]]:
    return [(int(e.signature.position), e.signature.beats) for e in song.meter_events]


def beats_at(song: PerformedSong, position: int) -> int | None:
    meter = song.effective_meter_at(Fraction(position))
    return None if meter is None else meter.beats


def meter_score(*, first: str, second: str) -> str:
    """m1 4/4 (declared), m2 body with the repeat start, endings m3 (:|) and m4, then m5."""
    return (
        m(1, n("C"), first=True)
        + m(2, n("D"), pre=fwd())
        + m(3, first, pre=start("1"), post=close("1", repeat=True))
        + m(4, second, pre=start("2"), post=close("2"))
        + m(5, n("G", dur=6))  # written under whichever 3/4 an ending declared
    )


def test_a_meter_declared_in_the_first_ending_is_met_on_pass_one_only(tmp_path: Path) -> None:
    body = meter_score(first=ts(3) + n("E", dur=6), second=n("F", dur=6))
    result = run(tmp_path, body)
    song = performed(result)
    assert meters(song) == [(0, 4), (8, 3)]  # declared once: ending 1 is played once
    assert not result.issues.has_errors, [str(i) for i in result.issues]


def test_a_meter_declared_in_the_second_ending_is_met_on_pass_two_only(tmp_path: Path) -> None:
    body = meter_score(first=n("E"), second=ts(3) + n("F", dur=6))
    song = performed(run(tmp_path, body))
    # m1 0-4, m2 4-8, ending 1 8-12, jump, m2 12-16, ending 2 declares 3/4 at 16
    assert meters(song) == [(0, 4), (16, 3)]


def test_skipping_an_ending_changes_the_effective_meter_without_an_event(tmp_path: Path) -> None:
    # ending 1 declares 3/4; ending 2 declares nothing and so inherits 3/4 from the written
    # context; the body is written under 4/4
    body = meter_score(first=ts(3) + n("E", dur=6), second=n("F", dur=6))
    song = performed(run(tmp_path, body))
    assert meters(song) == [(0, 4), (8, 3)]  # nothing is added when playback skips to ending 2
    # performed: C D E | D (pass 2 body, back under 4/4) F (ending 2, written under 3/4) G
    assert beats_at(song, 8) == 3  # ending 1
    assert beats_at(song, 11) == 4  # the body again: its written 4/4, restored, no event
    assert beats_at(song, 15) == 3  # ending 2, reached by an ending skip
    assert all(e.measure_index != 3 for e in song.meter_events)  # no event from ending 2


def test_no_events_come_from_unplayed_ending_measures(tmp_path: Path) -> None:
    song = performed(run(tmp_path, meter_score(first=n("E"), second=ts(3) + n("F", dur=6))))
    played = {p.source_index for p in song.plan.played}
    assert played == {0, 1, 2, 3, 4}  # both endings are performed once each ...
    assert [e.visit for e in song.meter_events if e.measure_index == 3] == [1]  # ... once


# --- lyrics ------------------------------------------------------------------------------------


def lyrics(song: PerformedSong, verse: str | None = None):  # type: ignore[no-untyped-def]
    return analyze_song_lyrics(song, verse=verse).lines[0]


def roles(analysis) -> list[AttackRole]:  # type: ignore[no-untyped-def]
    return [a.role for a in analysis.attacks]


def issue_codes(analysis) -> list[str]:  # type: ignore[no-untyped-def]
    return [i.code for i in analysis.issues]


def test_repeated_lyrics_in_the_common_body_and_unique_ones_in_each_ending(
    tmp_path: Path,
) -> None:
    body = voltas(
        n("D", lyric=sung("ni")),
        n("E", lyric=sung("one")),
        n("F", lyric=sung("two")),
        body_first=n("C", lyric=sung("la")),
        tail=n("G", lyric=sung("end")),
    )
    analysis = lyrics(performed(run(tmp_path, body)))
    # the skipped ending's lyric is never sung on the pass that skips it
    assert [w.text for w in analysis.words] == ["la", "ni", "one", "la", "ni", "two", "end"]
    assert analysis.coverage.syllable_attacks == 7  # only performed attacks count
    assert not analysis.issues


def test_a_word_cut_by_an_ending_skip_is_never_joined(tmp_path: Path) -> None:
    # the body ends BEGIN; each ending carries the END. Pass 1 reads "bana"; pass 2 skips
    body = voltas(
        n("D", lyric=sung("ba", "begin")),
        n("E", lyric=sung("na", "end")),
        n("F", lyric=sung("na", "end")),
        body_first=n("C", lyric=sung("la")),
        tail=n("G", lyric=sung("end")),
    )
    analysis = lyrics(performed(run(tmp_path, body)))
    words = [(w.text, w.closed) for w in analysis.words]
    assert ("bana", True) in words  # pass 1: adjacent, joined
    assert ("ba", False) in words  # pass 2: cut by the skip
    assert "LYRIC_WORD_UNCLOSED" in issue_codes(analysis)
    assert "LYRIC_WORD_UNOPENED" in issue_codes(analysis)  # the landing END
    unopened = next(i for i in analysis.located if i.issue.code == "LYRIC_WORD_UNOPENED")
    assert unopened.location is not None
    assert (unopened.location.number, unopened.location.repeat_pass) == (4, 2)
    assert unopened.location.endings == (2,)


def test_begin_in_the_first_ending_and_end_in_the_second_are_not_one_word(tmp_path: Path) -> None:
    body = voltas(
        n("D", lyric=sung("ni")),
        n("E", lyric=sung("ba", "begin")),
        n("F", lyric=sung("na", "end")),
        body_first=n("C", lyric=sung("la")),
    )
    analysis = lyrics(performed(run(tmp_path, body)))
    assert "bana" not in [w.text for w in analysis.words]
    assert "LYRIC_WORD_UNCLOSED" in issue_codes(analysis)
    assert "LYRIC_WORD_UNOPENED" in issue_codes(analysis)


def test_a_typed_melisma_is_not_carried_across_an_ending_skip(tmp_path: Path) -> None:
    stop = lyric_xml(extend("stop"))
    body = voltas(
        n("D", lyric=sung("la", ext=extend("start"))),
        n("E", lyric=stop),
        n("F", lyric=stop),
        body_first=n("C", lyric=sung("ni")),
        tail=n("G", lyric=sung("end")),
    )
    analysis = lyrics(performed(run(tmp_path, body)))
    assert issue_codes(analysis).count("LYRIC_MELISMA_UNCLOSED") == 1  # cut by the skip
    assert "LYRIC_EXTEND_WITHOUT_START" in issue_codes(analysis)  # ending 2's stop has no start
    pass_one = next(a for a in analysis.attacks if a.performed.source[0].measure == 3)
    assert pass_one.role is AttackRole.MELISMA_CONTINUATION  # pass 1 is adjacent: continues


def test_an_untyped_melisma_is_not_carried_across_an_ending_skip(tmp_path: Path) -> None:
    body = voltas(
        n("D", lyric=sung("la", ext=extend())),
        n("E"),  # lyric-less: continues the extender on pass 1
        n("F"),  # lyric-less: must NOT continue it after the skip on pass 2
        body_first=n("C", lyric=sung("ni")),
        tail=n("G", lyric=sung("end")),
    )
    analysis = lyrics(performed(run(tmp_path, body)))
    by_measure: dict[int, list[AttackRole]] = {}
    for attack in analysis.attacks:
        by_measure.setdefault(attack.performed.source[0].measure, []).append(attack.role)
    assert by_measure[3] == [AttackRole.MELISMA_CONTINUATION]
    assert by_measure[4] == [AttackRole.MISSING]
    assert "LYRIC_MELISMA_INTERRUPTED" in issue_codes(analysis)


def test_coverage_counts_only_performed_attacks(tmp_path: Path) -> None:
    body = voltas(n("D"), n("E"), n("F"))
    analysis = lyrics(performed(run(tmp_path, body)))
    # 2 body measures twice + each ending once + the tail = 7 attacks, none of them sung
    assert analysis.coverage.sung_attacks == 7
    assert issue_codes(analysis) == ["LYRIC_LINE_EMPTY"]


def test_a_song_analysed_literally_sees_no_discontinuity(tmp_path: Path) -> None:
    body = voltas(
        n("D", lyric=sung("ni")),
        n("E", lyric=sung("one")),
        n("F", lyric=sung("two")),
        body_first=n("C", lyric=sung("la")),
        tail=n("G", lyric=sung("end")),
    )
    result = run(tmp_path, body)
    assert result.song is not None
    literal = analyze_song_lyrics(result.song).lines[0]
    assert [w.text for w in literal.words] == ["la", "ni", "one", "two", "end"]  # written order
