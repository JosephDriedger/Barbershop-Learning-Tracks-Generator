"""Lyric readiness: apply a capability's lyric policy to the performed lyric analysis.

Policies (``Capability.lyric_policy``):

* ``NONE``: lyrics are not consumed; nothing is checked here (lyric-domain errors are already INFO
  for such a capability).
* ``AT_LEAST_ONE_COMPLETE_LINE``: some assigned line must carry the lyrics completely. If the
  capability names a ``lyric_source_role`` that line is the authoritative source, and *it* must be
  complete; otherwise any assigned line may be the source. Lead is never assumed.
* ``ALL_ASSIGNED_LINES_COMPLETE``: every assigned line must be complete.

A line is **complete** when it has sounding attacks, carries lyric content, and has no attack left
without a resolved lyric (a melisma continuation counts as resolved) and none in conflict. Nothing
is guessed: a missing syllable is never filled in or extended from a neighbouring voice. How a
harmony voice without lyrics gets words is not decided here (that is the backend handoff).
"""

from barbershop_tracks.core.readiness.capability import LyricPolicy
from barbershop_tracks.core.readiness.context import Facts, make_finding
from barbershop_tracks.core.readiness.findings import ReadinessFinding
from barbershop_tracks.models import (
    LineLyricAnalysis,
    PerformanceNote,
    Severity,
    SongLyricAnalysis,
    VoiceRole,
)

COMPLETE, PARTIAL, ABSENT = "complete", "partial", "absent"


def coverage_state(analysis: LineLyricAnalysis | None) -> str:
    """``complete``, ``partial`` (some lyrics, gaps or conflicts) or ``absent`` (no lyrics)."""
    if analysis is None:
        return ABSENT
    coverage = analysis.coverage
    if not coverage.has_any_lyric:
        return ABSENT
    if coverage.sung_attacks and not coverage.missing_attacks and not coverage.conflict_attacks:
        return COMPLETE
    return PARTIAL


def _first_gap(analysis: LineLyricAnalysis) -> PerformanceNote | None:
    runs = analysis.coverage.missing_runs
    if runs:
        return analysis.attacks[runs[0].first_index].performed
    for attack in analysis.attacks:
        if attack.role.value == "conflict":
            return attack.performed
    return None


def check_lyrics(facts: Facts, analysis: SongLyricAnalysis) -> list[ReadinessFinding]:
    cap = facts.capability
    if cap.lyric_policy is LyricPolicy.NONE:
        return []
    by_line = {line.part_id: line for line in analysis.lines}
    out: list[ReadinessFinding] = []

    def add(code: str, message: str, line_id: str | None, role: VoiceRole | None) -> None:
        line = by_line.get(line_id) if line_id is not None else None
        gap = _first_gap(line) if line is not None else None
        out.append(
            make_finding(
                cap,
                Severity.ERROR,
                code,
                message,
                facts=facts,
                role=role,
                line_id=line_id,
                note=None if gap is None else gap.source[0],
            )
        )

    def describe(line_id: str) -> str:
        line = by_line.get(line_id)
        if line is None:
            return "has no lyric analysis"
        c = line.coverage
        return (
            f"has {c.missing_attacks} of {c.sung_attacks} sounding attacks without a resolved "
            f"lyric and {c.conflict_attacks} in conflict"
        )

    if cap.lyric_policy is LyricPolicy.ALL_ASSIGNED_LINES_COMPLETE:
        for line in facts.assigned_lines:
            state = coverage_state(by_line.get(line.line_id))
            role = facts.role_of(line.line_id)
            name = role.display_name if role is not None else line.line_id
            if state == ABSENT:
                add("LYRIC_LINE_MISSING", f"{name} has no lyrics; {cap.name} needs "
                    "every assigned line complete", line.line_id, role)  # fmt: skip
            elif state == PARTIAL:
                add("LYRIC_LINE_INCOMPLETE", f"{name} {describe(line.line_id)}; {cap.name} needs "
                    "every assigned line complete", line.line_id, role)  # fmt: skip
        return out

    # AT_LEAST_ONE_COMPLETE_LINE
    source = cap.lyric_source_role
    if source is not None:
        lines = facts.assignments.lines_for(source)
        if not lines:
            add(
                "LYRIC_SOURCE_MISSING",
                f"{cap.name} takes its lyrics from {source.display_name}, which has no assigned "
                "line",
                None,
                source,
            )
            return out
        line_id = lines[0]
        state = coverage_state(by_line.get(line_id))
        if state == ABSENT:
            add(
                "LYRIC_SOURCE_MISSING",
                f"{cap.name} takes its lyrics from {source.display_name} ({line_id}), which has "
                "none",
                line_id,
                source,
            )
        elif state == PARTIAL:
            add(
                "LYRIC_SOURCE_INCOMPLETE",
                f"{cap.name} takes its lyrics from {source.display_name} ({line_id}), which "
                f"{describe(line_id)}; missing syllables are never filled in from other voices",
                line_id,
                source,
            )
        return out

    states = {
        line.line_id: coverage_state(by_line.get(line.line_id)) for line in facts.assigned_lines
    }
    if COMPLETE in states.values() or not states:
        return out
    partial = [line_id for line_id, state in states.items() if state == PARTIAL]
    if partial:
        first = partial[0]
        add(
            "LYRIC_SOURCE_INCOMPLETE",
            f"no assigned line carries complete lyrics; {first} {describe(first)}"
            + (f" (and {len(partial) - 1} other line(s) are partial)" if len(partial) > 1 else ""),
            first,
            facts.role_of(first),
        )
    else:
        add(
            "LYRIC_SOURCE_MISSING",
            f"{cap.name} needs lyrics on at least one assigned line and none has any",
            None,
            None,
        )
    return out
