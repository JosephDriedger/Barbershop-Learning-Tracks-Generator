"""Performed-lyric analysis: what is sung at each performed attack, for one logical verse.

A pure function over a voice line's ``PerformanceNote``s. It never mutates the ``Song``, a
``Note``, a ``Lyric`` or a ``PerformanceNote``, never rewrites or moves text, and never produces
OpenUtau syntax, phonemes, MIDI ticks or any backend concept. It only classifies, reconstructs
words, and reports.

Policies here that MusicXML does not define are *ours* and are named as such in the messages
and in ``docs/m3c2-plan.md`` (lyrics on tie continuations, a rest ending an untyped extender).
"""

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.issues import IssueCollector
from barbershop_tracks.core.lyrics.findings import Finding
from barbershop_tracks.core.lyrics.hazards import scan_hazards
from barbershop_tracks.core.lyrics.melisma import Continuation, MelismaTracker
from barbershop_tracks.core.lyrics.verses import (
    choose_verse,
    has_mixed_numbering,
    logical_verses,
    lyrics_for,
    merge_verses,
)
from barbershop_tracks.core.lyrics.words import WordBuilder
from barbershop_tracks.core.timeline import merge_tied_notes
from barbershop_tracks.models import (
    AttackLyric,
    AttackRole,
    LineLyricAnalysis,
    LocatedIssue,
    Lyric,
    LyricCoverage,
    LyricKind,
    Melisma,
    MissingRun,
    Note,
    PerformanceLocation,
    PerformanceNote,
    PerformedSong,
    Severity,
    Song,
    SongLyricAnalysis,
)

Locator = Callable[[Note], PerformanceLocation | None]


class _Collector(IssueCollector):
    """An issue collector that remembers the note an issue is about (for its location)."""

    def __init__(self) -> None:
        super().__init__()
        self.notes: list[Note | None] = []

    def _add(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super()._add(*args, **kwargs)
        self.notes.append(None)

    def about(self, note: Note, severity: Severity, code: str, message: str, part_id: str) -> None:
        """Add an issue located at ``note``."""
        super()._add(severity, code, message, part_id, note.measure, note.beat)
        self.notes.append(note)

    def located(self, locator: Locator | None) -> tuple[LocatedIssue, ...]:
        issues = self.result().issues
        return tuple(
            LocatedIssue(issue, locator(note) if locator is not None and note is not None else None)
            for issue, note in zip(issues, self.notes, strict=True)
        )


@dataclass(slots=True)
class _Record:
    index: int
    performed: PerformanceNote
    role: AttackRole
    lyric: Lyric | None = None
    continuation: Continuation | None = None


def analyze_line(
    performed: Sequence[PerformanceNote],
    *,
    part_id: str,
    verse: str | None = None,
    discontinuities: Collection[Fraction] = (),
    locator: Locator | None = None,
) -> LineLyricAnalysis:
    """Analyze one voice line. ``verse`` (a logical verse) overrides the automatic choice.

    ``discontinuities`` are performed positions where playback lands after something other than
    written adjacency (``PerformancePlan.discontinuity_positions``: a repeat jump or a skipped
    ending): all lyric state (words, typed and untyped melismas) ends there. ``locator`` maps
    a note to its performance location for ``LineLyricAnalysis.located``.
    """
    available = logical_verses(performed)
    choice = choose_verse(available, verse)
    issues = _Collector()
    if verse is not None and not choice.found:
        issues.error(
            "LYRIC_VERSE_NOT_FOUND",
            f"verse {verse!r} was requested but this line has only {_names(available)}",
            part_id=part_id,
        )
    elif verse is None and len(available) > 1:
        issues.warning(
            "LYRIC_MULTIPLE_VERSES",
            _multiple_verses_message(choice.selected, available, choice.fell_back),
            part_id=part_id,
        )
    return _analyze(
        performed, part_id, choice.selected, available, issues, discontinuities, locator
    )


def analyze_song_lyrics(
    song: Song | PerformedSong, *, verse: str | None = None
) -> SongLyricAnalysis:
    """Analyze every line for one song-wide logical verse.

    * ``Song``: the **literal**, non-expanded analysis, in written order, with ties merged over
      the written order and no discontinuities. Use it only for scores without repeats.
    * ``PerformedSong``: the actual performed traversal: ties were resolved over the performed
      order (their diagnostics are not repeated here) and every discontinuity (a repeat jump or a
      skipped ending) ends all lyric state.
      Generation should use this form whenever a performance representation exists.

    A requested or automatically chosen verse that a line does not have simply gives that line
    no lyrics (a lyric-less voice is normal).
    """
    if isinstance(song, PerformedSong):
        lines = [(line.part_id, notes) for line, notes in zip(song.lines, song.merged, strict=True)]
        discontinuities = song.plan.discontinuity_positions
        locator: Locator | None = song.location_of
    else:
        lines = [
            (part.part_id, merge_tied_notes(part.events, part_id=part.part_id).notes)
            for part in song.parts
        ]
        discontinuities = frozenset()
        locator = None
    per_line = [logical_verses(notes) for _, notes in lines]
    available = merge_verses(per_line)
    choice = choose_verse(available, verse)
    song_issues = IssueCollector()
    if verse is not None and not choice.found:
        song_issues.error(
            "LYRIC_VERSE_NOT_FOUND",
            f"verse {verse!r} was requested but the song has only {_names(available)}",
        )
    elif verse is None and len(available) > 1:
        song_issues.warning(
            "LYRIC_MULTIPLE_VERSES",
            _multiple_verses_message(choice.selected, available, choice.fell_back),
        )
    analyses = tuple(
        _analyze(
            notes, part_id, choice.selected, line_verses, _Collector(), discontinuities, locator
        )
        for (part_id, notes), line_verses in zip(lines, per_line, strict=True)
    )
    return SongLyricAnalysis(choice=choice, lines=analyses, issues=song_issues.result())


# --- the analysis ----------------------------------------------------------------------


def _analyze(
    performed: Sequence[PerformanceNote],
    part_id: str,
    selected: str | None,
    available: tuple[str, ...],
    issues: _Collector,
    discontinuities: Collection[Fraction] = (),
    locator: Locator | None = None,
) -> LineLyricAnalysis:
    tracker, words = MelismaTracker(), WordBuilder()
    records: list[_Record] = []
    previous_end: Fraction | None = None
    pending = sorted(discontinuities)
    next_break = 0

    def report(finding: Finding) -> None:
        note = performed[finding.attack_index].source[0]
        issues.about(note, finding.severity, finding.code, finding.message, part_id)

    def report_all(findings: Sequence[Finding]) -> None:
        for finding in findings:
            report(finding)

    for index, attack in enumerate(performed):
        if next_break < len(pending) and attack.start >= pending[next_break]:
            while next_break < len(pending) and attack.start >= pending[next_break]:
                next_break += 1  # one reset per attack, however many positions were passed
            report_all(tracker.discontinuity())
            report_all(words.discontinuity())
            previous_end = None
        if attack.is_rest:
            tracker.rest()
            words.rest()
            records.append(_Record(index, attack, AttackRole.REST))
            continue
        if previous_end is not None and attack.start < previous_end:
            report(
                Finding(
                    "LYRIC_SIMULTANEOUS_ATTACKS",
                    Severity.ERROR,
                    "this attack starts before the previous one ends; a lyric line must "
                    "have one attack at a time",
                    index,
                )
            )
        previous_end = attack.end
        record = _classify(index, attack, selected, tracker, words, report_all, report)
        records.append(record)
        _tie_continuations(index, attack, record, selected, tracker, issues, part_id, report_all)

    report_all(tracker.finish())
    report_all(words.finish())
    return _finish(
        records, performed, part_id, selected, available, tracker, words, issues, locator
    )


def _classify(
    index: int,
    attack: PerformanceNote,
    selected: str | None,
    tracker: MelismaTracker,
    words: WordBuilder,
    report_all: Callable[[Sequence[Finding]], None],
    report: Callable[[Finding], None],
) -> _Record:
    candidates = lyrics_for(attack.source[0], selected)
    if len(candidates) > 1:  # the parser already reported LYRIC_DUPLICATE_VERSE
        report_all(tracker.conflict())
        return _Record(index, attack, AttackRole.CONFLICT)
    if not candidates:
        role, continuation = tracker.unlyriced(index)
        return _Record(index, attack, role, continuation=continuation)
    lyric = candidates[0]
    if lyric.kind is LyricKind.TEXT:
        if lyric.melisma in (Melisma.CONTINUE, Melisma.STOP):
            report(
                Finding(
                    "LYRIC_EXTEND_SEQUENCE_INVALID",
                    Severity.ERROR,
                    f"the syllable {lyric.text!r} starts new text but its extender says "
                    f"'{lyric.melisma.value}', which would continue or end an earlier one",
                    index,
                )
            )
            report_all(tracker.conflict())
            return _Record(index, attack, AttackRole.CONFLICT)
        report_all(tracker.syllable(lyric, index))
        report_all(words.add(index, lyric))
        return _Record(index, attack, AttackRole.SYLLABLE, lyric=lyric)
    if lyric.kind is LyricKind.EXTENSION:
        role, continuation, findings = tracker.extension_only(lyric, index)
        report_all(findings)
        return _Record(index, attack, role, lyric=lyric, continuation=continuation)
    name = lyric.kind.value
    report_all(tracker.vocal_event(index, name))
    role = AttackRole.HUMMING if lyric.kind is LyricKind.HUMMING else AttackRole.LAUGHING
    return _Record(index, attack, role, lyric=lyric)


def _same_content(a: Lyric, b: Lyric) -> bool:
    """Meaningful literal equality: kind, text, syllabic, extend form and elided segments."""
    return (
        a.kind is b.kind
        and a.text == b.text
        and a.syllabic is b.syllabic
        and a.melisma is b.melisma
        and a.elided == b.elided
    )


def _tie_continuations(
    index: int,
    attack: PerformanceNote,
    record: _Record,
    selected: str | None,
    tracker: MelismaTracker,
    issues: _Collector,
    part_id: str,
    report_all: Callable[[Sequence[Finding]], None],
) -> None:
    """Our policy for lyrics on later source notes of a tie group (MusicXML is silent)."""
    primary = record.lyric if record.role is not AttackRole.CONFLICT else None
    for note in attack.source[1:]:
        for lyric in lyrics_for(note, selected):
            if lyric.kind is LyricKind.EXTENSION:
                report_all(
                    [
                        Finding(f.code, f.severity, f.message, index)
                        for f in tracker.continuation_event(lyric, index)
                    ]
                )
            elif primary is not None and _same_content(lyric, primary):
                _note_issue(
                    issues, part_id, note, Severity.WARNING, "LYRIC_TIE_REPEATED",
                    "a tied continuation repeats the attack's lyric; it is sung once "
                    "(our interpretation: MusicXML does not say)",
                )  # fmt: skip
            else:
                _note_issue(
                    issues, part_id, note, Severity.ERROR, "LYRIC_TIE_CONFLICT",
                    f"a tied continuation carries lyric content ({_label(lyric)}) different from "
                    "the attack's, which merging the tie would swallow (our interpretation: "
                    "MusicXML does not say)",
                )  # fmt: skip


def _note_issue(
    issues: _Collector,
    part_id: str,
    note: Note,
    severity: Severity,
    code: str,
    message: str,
) -> None:
    issues.about(note, severity, code, message, part_id)


def _label(lyric: Lyric) -> str:
    return repr(lyric.full_text) if lyric.has_text else f"<{lyric.kind.value}>"


# --- assembling the result ------------------------------------------------------------


def _finish(
    records: list[_Record],
    performed: Sequence[PerformanceNote],
    part_id: str,
    selected: str | None,
    available: tuple[str, ...],
    tracker: MelismaTracker,
    words: WordBuilder,
    issues: _Collector,
    locator: Locator | None,
) -> LineLyricAnalysis:
    attacks = tuple(_attack(record, words) for record in records)
    coverage = _coverage(records, tracker)
    _line_issues(records, performed, part_id, selected, tracker, words, coverage, issues)
    return LineLyricAnalysis(
        part_id=part_id,
        verse=selected,
        verses=available,
        attacks=attacks,
        words=words.words(),
        coverage=coverage,
        issues=issues.result(),
        located=issues.located(locator),
    )


def _attack(record: _Record, words: WordBuilder) -> AttackLyric:
    syllables = (
        1 + len(record.lyric.elided) if record.role is AttackRole.SYLLABLE and record.lyric else 0
    )
    cont = record.continuation
    return AttackLyric(
        index=record.index,
        performed=record.performed,
        role=record.role,
        lyric=record.lyric,
        word_indices=words.word_indices(record.index, syllables),
        melisma_origin=cont.origin if cont else None,
        melisma_position=cont.position if cont else None,
        melisma_basis=cont.basis if cont else None,
    )


def _coverage(records: list[_Record], tracker: MelismaTracker) -> LyricCoverage:
    sung = [r for r in records if r.role is not AttackRole.REST]
    runs: list[MissingRun] = []
    start: _Record | None = None
    last: _Record | None = None
    count = 0

    def close() -> None:
        nonlocal start, last, count
        if start is not None and last is not None:
            first_note, last_note = start.performed.source[0], last.performed.source[0]
            runs.append(
                MissingRun(
                    first_index=start.index,
                    last_index=last.index,
                    count=count,
                    first_measure=first_note.measure,
                    first_beat=first_note.beat,
                    last_measure=last_note.measure,
                    last_beat=last_note.beat,
                )
            )
        start, last, count = None, None, 0

    for record in sung:
        if record.role is AttackRole.MISSING:
            start = start or record
            last = record
            count += 1
        else:
            close()
    close()

    def n(role: AttackRole) -> int:
        return sum(1 for r in records if r.role is role)

    return LyricCoverage(
        sung_attacks=len(sung),
        syllable_attacks=n(AttackRole.SYLLABLE),
        continuation_attacks=n(AttackRole.MELISMA_CONTINUATION),
        missing_attacks=n(AttackRole.MISSING),
        humming_attacks=n(AttackRole.HUMMING),
        laughing_attacks=n(AttackRole.LAUGHING),
        conflict_attacks=n(AttackRole.CONFLICT),
        missing_runs=tuple(runs),
        longest_melisma=tracker.longest,
    )


def _line_issues(
    records: list[_Record],
    performed: Sequence[PerformanceNote],
    part_id: str,
    selected: str | None,
    tracker: MelismaTracker,
    words: WordBuilder,
    coverage: LyricCoverage,
    issues: _Collector,
) -> None:
    def at(index: int) -> Note:
        return performed[index].source[0]

    if has_mixed_numbering(performed, selected):
        issues.warning(
            "LYRIC_VERSE_MIXED_NUMBERING",
            'verse 1 appears both as number="1" and unnumbered; they are analyzed as one verse',
            part_id=part_id,
        )
    if tracker.interruptions:
        issues.about(
            at(tracker.interruptions[0]),
            Severity.WARNING,
            "LYRIC_MELISMA_INTERRUPTED",
            f"{len(tracker.interruptions)} untyped extender(s) were ended by a rest or a repeat "
            "jump and then followed by a lyric-less attack, which is unresolved (our "
            "conservative interpretation: MusicXML does not say whether an extender crosses a "
            "rest)",
            part_id,
        )
    if words.unspecified_count:
        issues.about(
            at(words.first_unspecified or 0),
            Severity.WARNING,
            "LYRIC_SYLLABIC_MISSING",
            f"{words.unspecified_count} syllable(s) have no <syllabic>, so word boundaries are "
            "not stated",
            part_id,
        )
    _coverage_issue(coverage, part_id, issues, performed)
    syllables = [(r.index, r.lyric) for r in records if r.role is AttackRole.SYLLABLE and r.lyric]
    for hazard in scan_hazards(syllables):
        issues.about(
            at(hazard.first_attack_index),
            Severity.WARNING,
            hazard.code,
            f"{hazard.count} syllable(s) {hazard.description}",
            part_id,
        )


def _coverage_issue(
    coverage: LyricCoverage,
    part_id: str,
    issues: _Collector,
    performed: Sequence[PerformanceNote],
) -> None:
    if not coverage.sung_attacks:
        return
    if not coverage.has_any_lyric:
        issues.warning(
            "LYRIC_LINE_EMPTY",
            f"the line has {coverage.sung_attacks} performed attacks and no usable lyrics for "
            "the selected verse",
            part_id=part_id,
        )
        return
    if coverage.missing_attacks:
        runs = coverage.missing_runs
        first = runs[0]
        longest = max(run.count for run in runs)
        issues.about(
            performed[first.first_index].source[0],
            Severity.WARNING,
            "LYRIC_MISSING_SUMMARY",
            f"{coverage.missing_attacks} performed attacks lack resolved lyrics across "
            f"{len(runs)} run{'s' if len(runs) != 1 else ''} (longest {longest})",
            part_id,
        )


def _names(verses: Sequence[str]) -> str:
    return "verse " + ", ".join(repr(v) for v in verses) if verses else "no lyrics"


def _multiple_verses_message(
    selected: str | None, available: Sequence[str], fell_back: bool
) -> str:
    listed = ", ".join(repr(v) for v in available)
    base = f"the line has several verses ({listed}); verse {selected!r} was analyzed"
    if fell_back:
        return base + " because there is no verse '1' (the first verse in document order)"
    return base
