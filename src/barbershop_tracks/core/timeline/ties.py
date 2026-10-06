"""Pure tie merging: source notes in, derived performed notes out.

The source ``Note`` objects are never changed. Ties are matched on **exact sounding pitch**
(``Pitch.absolute_semitones``), so C#4 tied to Db4 is one performed note and microtones need
exact equality. A tie only continues into a note that starts exactly where the previous one
ends, so ties across barlines and ``divisions`` changes need no special handling, and a tie
across a rest or gap is unmatched.

Diagnostic precedence for every note that has a tie *stop* (``tied_from_previous``) at start s:

1. ``TIE_AMBIGUOUS``: two or more open ties of the same sounding pitch end exactly at s. Nothing
   is paired and nothing is guessed.
2. paired: exactly one open tie of that pitch ends at s.
3. ``TIE_PITCH_MISMATCH``: no open tie of that pitch, but at least one open tie ends exactly at s.
4. ``TIE_UNMATCHED_STOP``: no open tie ends at s at all (an unrelated stop; never reported as a
   pitch mismatch).

``TIE_UNMATCHED_START`` is reported for an open tie that is never continued. A start already
named by a ``TIE_AMBIGUOUS`` or ``TIE_PITCH_MISMATCH`` diagnostic is not reported again, so one
mistake produces one diagnostic. In every failure case the stop note still starts a new attack,
so the output stays defined; the ERRORs block generation.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from barbershop_tracks.models import (
    Note,
    PerformanceNote,
    Severity,
    ValidationIssue,
    ValidationResult,
)


@dataclass(frozen=True, slots=True)
class TieMergeResult:
    notes: tuple[PerformanceNote, ...]
    issues: ValidationResult


@dataclass(slots=True)
class _Group:
    index: int
    sources: list[Note]
    diagnosed: bool = False

    @property
    def end(self) -> Fraction:
        return self.sources[-1].end

    @property
    def height(self) -> Fraction:
        return _height(self.sources[-1])


@dataclass(slots=True)
class _Merger:
    part_id: str
    issues: list[ValidationIssue] = field(default_factory=list)
    open_groups: list[_Group] = field(default_factory=list)
    finished: list[tuple[int, PerformanceNote]] = field(default_factory=list)
    counter: int = 0
    ambiguous_reported: set[tuple[Fraction, Fraction]] = field(default_factory=set)

    def report(self, code: str, message: str, note: Note) -> None:
        self.issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                code=code,
                message=message,
                part_id=self.part_id,
                measure=note.measure,
                beat=note.beat,
            )
        )

    def finish(self, group: _Group) -> None:
        self.finished.append((group.index, PerformanceNote(source=tuple(group.sources))))

    def new_group(self, note: Note) -> _Group:
        group = _Group(index=self.counter, sources=[note])
        self.counter += 1
        if note.tied_to_next and not note.is_rest:
            self.open_groups.append(group)
        else:
            self.finish(group)
        return group

    def expire(self, start: Fraction) -> None:
        """Close open ties that ended before ``start``; they can no longer be continued."""
        for group in list(self.open_groups):
            if group.end < start:
                self.open_groups.remove(group)
                self._unmatched_start(group)
                self.finish(group)

    def close_all(self) -> None:
        for group in list(self.open_groups):
            self.open_groups.remove(group)
            self._unmatched_start(group)
            self.finish(group)

    def _unmatched_start(self, group: _Group) -> None:
        if not group.diagnosed:
            last = group.sources[-1]
            self.report(
                "TIE_UNMATCHED_START",
                f"a tie starts on {_name(last)} but no note continues it",
                last,
            )

    def stop(self, note: Note, wanted_at_start: set[Fraction]) -> None:
        """Handle a note that has a tie stop."""
        height = _height(note)
        ending_here = [g for g in self.open_groups if g.end == note.start]
        same = [g for g in ending_here if g.height == height]
        if len(same) > 1:
            key = (note.start, height)
            if key not in self.ambiguous_reported:
                self.ambiguous_reported.add(key)
                self.report(
                    "TIE_AMBIGUOUS",
                    f"{len(same)} open ties on {_name(note)} end here, so it is unclear which "
                    "one this tie stop continues",
                    note,
                )
            for group in same:
                group.diagnosed = True
            self.new_group(note)
        elif same:
            group = same[0]
            group.sources.append(note)
            if not note.tied_to_next:
                self.open_groups.remove(group)
                self.finish(group)
        else:
            if ending_here:
                names = ", ".join(sorted({_name(g.sources[-1]) for g in ending_here}))
                self.report(
                    "TIE_PITCH_MISMATCH",
                    f"a tie ends here on {_name(note)} but the tie that arrives is on {names}",
                    note,
                )
                for group in ending_here:
                    if group.height not in wanted_at_start:
                        group.diagnosed = True
            else:
                self.report(
                    "TIE_UNMATCHED_STOP",
                    f"a tie stops on {_name(note)} but no tie leads into it",
                    note,
                )
            self.new_group(note)


def merge_tied_notes(events: Sequence[Note], *, part_id: str) -> TieMergeResult:
    """Merge tied source notes of one voice line into performed notes.

    ``part_id`` (the line id) only locates diagnostics. The input notes are not modified and
    each appears, unchanged, in exactly one result note's ``source``.
    """
    ordered = sorted(events, key=lambda note: note.start)  # stable: chord order is kept
    wanted: dict[Fraction, set[Fraction]] = defaultdict(set)
    for note in ordered:
        if note.tied_from_previous and not note.is_rest:
            wanted[note.start].add(_height(note))
    merger = _Merger(part_id=part_id)
    for note in ordered:
        merger.expire(note.start)
        if not note.is_rest and note.tied_from_previous:
            merger.stop(note, wanted[note.start])
        else:
            merger.new_group(note)
    merger.close_all()
    merger.finished.sort(key=lambda item: (item[1].start, item[0]))
    return TieMergeResult(
        notes=tuple(performed for _, performed in merger.finished),
        issues=ValidationResult.of(merger.issues),
    )


def _height(note: Note) -> Fraction:
    pitch = note.sounding_pitch
    if pitch is None:  # pragma: no cover - callers exclude rests
        raise ValueError("a rest has no pitch")
    return pitch.absolute_semitones


def _name(note: Note) -> str:
    return str(note.sounding_pitch)
