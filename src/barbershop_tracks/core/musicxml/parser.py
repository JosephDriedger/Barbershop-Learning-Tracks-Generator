"""Parse a safely loaded MusicXML score into a ``Song`` plus validation issues.

M3b1 covers structure and notes: parts, staves, voice lines, the exact timeline, written
pitches and transposition, rests, chords, pickups and clefs. Lyrics, ties, tempo and meter
maps, and repeat expansion arrive in later steps.

Problems in the music never raise; they become ``ValidationIssue``s. Only a file that cannot
be loaded at all raises (``ScoreLoadError`` from the loader).
"""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.musicxml.issues import IssueCollector
from barbershop_tracks.core.musicxml.limits import DEFAULT_LIMITS, LoaderLimits
from barbershop_tracks.core.musicxml.meter import build_meter_map
from barbershop_tracks.core.musicxml.part_reader import PartTimeline, read_part
from barbershop_tracks.core.musicxml.repeat_marks import reconcile_marks
from barbershop_tracks.core.musicxml.source import MusicXmlSource, load_musicxml_source
from barbershop_tracks.core.musicxml.tempo import reconcile_tempos
from barbershop_tracks.core.musicxml.values import child_text
from barbershop_tracks.core.timeline import perform_song
from barbershop_tracks.models import (
    ClefChange,
    MeasureSpan,
    Note,
    Part,
    PerformedSong,
    RepeatMark,
    Song,
    SourceLine,
    SourceMetadata,
    ValidationResult,
)


@dataclass(frozen=True, slots=True)
class ParseResult:
    """The outcome of parsing. ``song`` is ``None`` only if nothing usable was found.

    A ``Song`` may be present even when ``issues`` contains errors; callers must not
    generate output while ``issues.has_errors``.
    """

    song: Song | None
    issues: ValidationResult
    performed: PerformedSong | None = None  # the song in performance order (repeats expanded)


def parse_musicxml(
    path: str | os.PathLike[str], limits: LoaderLimits = DEFAULT_LIMITS
) -> ParseResult:
    """Load and parse a ``.musicxml``, ``.xml`` or ``.mxl`` file."""
    return parse_score(load_musicxml_source(path, limits))


def parse_score(source: MusicXmlSource) -> ParseResult:
    """Parse an already loaded ``score-partwise`` document."""
    root = source.root
    issues = IssueCollector()
    names = _part_names(root)
    timelines = _read_parts(root, names, issues)
    if not timelines:
        issues.error("NO_PARTS", "the score contains no <part> elements")
        return ParseResult(song=None, issues=issues.result())
    _check_alignment(timelines, issues)
    parts = _build_parts(timelines, names)
    clefs: list[ClefChange] = [clef for timeline in timelines for clef in timeline.clefs]
    tempo_map = reconcile_tempos([t for tl in timelines for t in tl.tempos], issues)
    time_signatures = build_meter_map(
        part_ids=[tl.part_id for tl in timelines],
        meters=[tl.meters for tl in timelines],
        measure_numbers=timelines[0].measure_numbers,
        measure_lengths=timelines[0].measure_lengths,
        issues=issues,
    )
    measures = _measure_table(timelines[0])
    marks = _repeat_marks(timelines, measures, issues)
    song = Song(
        title=_title(root),
        composer=_creator(root, "composer"),
        arranger=_creator(root, "arranger"),
        parts=tuple(parts),
        tempo_map=tempo_map,
        time_signatures=time_signatures,
        source=SourceMetadata(
            path=source.path,
            format_name="MusicXML",
            format_version=root.get("version"),
            software=_software(root),
        ),
        clef_changes=tuple(clefs),
        measures=measures,
        repeat_marks=marks,
    )
    performed = perform_song(song)
    issues.extend(performed.issues)
    return ParseResult(song=song, issues=issues.result(), performed=performed)


def _measure_table(timeline: PartTimeline) -> tuple[MeasureSpan, ...]:
    """The source measure table, from the reference part (alignment is checked separately)."""
    spans: list[MeasureSpan] = []
    start = Fraction(0)
    for index, length in enumerate(timeline.measure_lengths):
        spans.append(
            MeasureSpan(
                index=index,
                number=timeline.measure_numbers[index],
                start=start,
                length=length,
                raw_number=timeline.raw_numbers[index],
                implicit=timeline.implicit[index],
            )
        )
        start += length
    return tuple(spans)


def _repeat_marks(
    timelines: list[PartTimeline], measures: tuple[MeasureSpan, ...], issues: IssueCollector
) -> tuple[RepeatMark, ...]:
    """The repeat structure every part agrees on (none if they differ or are misaligned)."""
    if any(len(t.measure_lengths) != len(measures) for t in timelines):
        return ()  # PART_MEASURE_COUNT_MISMATCH already blocks; indices would not line up
    if not all(t.repeats_usable for t in timelines):
        return ()  # an unreadable sign was reported; a partly read structure is never expanded
    return reconcile_marks(
        [(t.part_id, t.repeats) for t in timelines], [m.number for m in measures], issues
    )


# --- parts ----------------------------------------------------------------------------


def _part_names(root: ET.Element) -> dict[str, str]:
    """Raw ``part-name`` per ``score-part`` id, in ``part-list`` order."""
    names: dict[str, str] = {}
    part_list = root.find("part-list")
    if part_list is not None:
        for score_part in part_list.findall("score-part"):
            part_id = score_part.get("id")
            if part_id is not None:
                names[part_id] = child_text(score_part, "part-name") or ""
    return names


def _read_parts(
    root: ET.Element, names: dict[str, str], issues: IssueCollector
) -> list[PartTimeline]:
    timelines: list[PartTimeline] = []
    for element in root.findall("part"):
        part_id = element.get("id")
        if not part_id or "/" in part_id:
            issues.error("PART_ID_INVALID", f"a <part> has an unusable id {part_id!r}")
            continue
        if part_id not in names:
            issues.error(
                "PART_NOT_IN_PART_LIST",
                f"part '{part_id}' is not declared in <part-list>",
                part_id=part_id,
            )
        timelines.append(read_part(element, part_id, issues))
    return timelines


def _check_alignment(timelines: list[PartTimeline], issues: IssueCollector) -> None:
    """Every part must have the same number of measures with the same lengths."""
    reference = timelines[0]
    for other in timelines[1:]:
        if len(other.measure_lengths) != len(reference.measure_lengths):
            issues.error(
                "PART_MEASURE_COUNT_MISMATCH",
                f"part '{other.part_id}' has {len(other.measure_lengths)} measures but "
                f"part '{reference.part_id}' has {len(reference.measure_lengths)}",
                part_id=other.part_id,
            )
        for index, (a, b) in enumerate(
            zip(reference.measure_lengths, other.measure_lengths, strict=False)
        ):
            if a != b:
                issues.error(
                    "MEASURE_LENGTH_MISMATCH_ACROSS_PARTS",
                    f"measure is {b} quarter notes long in part '{other.part_id}' but {a} "
                    f"in part '{reference.part_id}'",
                    part_id=other.part_id,
                    measure=other.measure_numbers[index],
                )
                break  # later measures would all be shifted; one report is enough


def _build_parts(timelines: list[PartTimeline], names: dict[str, str]) -> list[Part]:
    parts: list[Part] = []
    for timeline in timelines:
        raw_name = names.get(timeline.part_id)
        display = " ".join((raw_name or timeline.part_id).split())
        for staff, voice in sorted(timeline.lines, key=lambda key: key[0]):
            events: list[Note] = sorted(timeline.lines[(staff, voice)], key=lambda n: n.start)
            line = SourceLine(part_id=timeline.part_id, staff=staff, voice=voice)
            parts.append(
                Part(
                    part_id=str(line),
                    name=display,
                    events=tuple(events),
                    source_line=line,
                    source_name=raw_name,
                )
            )
    return parts


# --- metadata -------------------------------------------------------------------------


def _title(root: ET.Element) -> str:
    work = root.find("work")
    if work is not None:
        title = child_text(work, "work-title")
        if title is not None:
            return title
    return child_text(root, "movement-title") or ""


def _creator(root: ET.Element, kind: str) -> str | None:
    identification = root.find("identification")
    if identification is None:
        return None
    for creator in identification.findall("creator"):
        if creator.get("type") == kind and creator.text and creator.text.strip():
            return creator.text.strip()
    return None


def _software(root: ET.Element) -> str | None:
    encoding = root.find("identification/encoding")
    return None if encoding is None else child_text(encoding, "software")


__all__ = ["ParseResult", "parse_musicxml", "parse_score"]
