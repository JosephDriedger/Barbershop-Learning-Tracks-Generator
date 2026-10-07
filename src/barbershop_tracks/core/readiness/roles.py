"""Voice-assignment checks: the explicit line -> role mapping against the capability."""

from barbershop_tracks.core.readiness.context import Facts, make_finding
from barbershop_tracks.core.readiness.findings import ReadinessFinding
from barbershop_tracks.models import Severity, VoiceRole

_ORDER = list(VoiceRole)


def check_roles(facts: Facts) -> list[ReadinessFinding]:
    cap, given = facts.capability, facts.assignments
    out: list[ReadinessFinding] = []

    def add(severity: Severity, code: str, message: str, **kw) -> None:  # type: ignore[no-untyped-def]
        out.append(make_finding(cap, severity, code, message, **kw))

    known = facts.line_ids
    for role, line in given.entries:
        if line not in known:
            add(
                Severity.ERROR,
                "ROLE_LINE_UNKNOWN",
                f"{role.display_name} is assigned to {line!r}, which is not a line of this score",
                role=role,
                line_id=line,
            )
    for role in given.duplicate_roles:
        lines = ", ".join(given.lines_for(role))
        add(
            Severity.ERROR,
            "ROLE_DUPLICATE",
            f"{role.display_name} is assigned to more than one line ({lines}); a role needs "
            "exactly one line and lines are never merged",
            role=role,
        )
    for line in given.lines_assigned_twice:
        roles = ", ".join(r.display_name for r in given.roles_for(line))
        add(
            Severity.ERROR,
            "LINE_ASSIGNED_TWICE",
            f"line {line!r} is assigned to several roles ({roles})",
            line_id=line,
        )
    assigned_lines = {line for _, line in given.entries}
    for line in given.ignored:
        if line not in known:
            add(
                Severity.ERROR,
                "IGNORED_LINE_UNKNOWN",
                f"{line!r} is ignored but is not a line of this score",
                line_id=line,
            )
        elif line in assigned_lines:
            add(
                Severity.ERROR,
                "LINE_ASSIGNED_AND_IGNORED",
                f"line {line!r} is both assigned a role and ignored",
                line_id=line,
            )
    present = {role for role, _ in given.entries}
    for role in _ORDER:
        if role in cap.required_roles and role not in present:
            add(
                Severity.ERROR,
                "ROLE_MISSING",
                f"{cap.name} needs a {role.display_name} line and none is assigned",
                role=role,
            )
    if cap.assigned_lines_must_sound:
        seen: set[str] = set()
        for role, line in given.entries:
            facts_line = facts.line(line)
            if facts_line is not None and not facts_line.has_notes and line not in seen:
                seen.add(line)
                add(
                    Severity.ERROR,
                    "ROLE_LINE_EMPTY",
                    f"{role.display_name} is assigned to {line!r}, which has no sounding notes",
                    role=role,
                    line_id=line,
                )
    ignored = set(given.ignored)
    for musical in facts.lines:
        if not musical.has_notes:
            continue
        accounted = musical.line_id in assigned_lines
        if musical.line_id in ignored and not accounted:
            add(
                Severity.INFO,
                "LINE_IGNORED",
                f"line {musical.line_id!r} has {len(musical.attacks)} sounding notes and is "
                "explicitly excluded",
                line_id=musical.line_id,
            )
        elif not accounted and cap.all_musical_lines_accounted_for:
            add(
                Severity.ERROR,
                "LINE_UNASSIGNED",
                f"line {musical.line_id!r} has {len(musical.attacks)} sounding notes but no "
                "role and is not ignored; a musical line is never silently discarded",
                line_id=musical.line_id,
            )
    return out
