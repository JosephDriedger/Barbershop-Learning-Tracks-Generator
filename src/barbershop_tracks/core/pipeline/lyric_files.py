"""The lyric review report BLT writes, and the approvals file a person writes back.

BLT never invents a lyric. When a note has no usable lyric (or only an unapproved proposal), the
run stops and produces a **review report** listing exactly those notes. A person (later, the GUI)
decides what each note is sung to and records that in an **approvals file**; passing it with
``--approve-lyrics`` makes those decisions explicit inputs of the next run.

Review report, schema ``blt.lyric-review/1``::

    {"schema": "blt.lyric-review/1",
     "source": {"display_name": "...", "sha256": "..."},
     "ready": false,
     "items": [{"voice": "tenor", "note_index": 3, "start": "3/2", "duration": "1/2",
                "midi_pitch": 64, "reason": "lyric_absent", "detail": "...",
                "proposal": null}],
     "approvals_template": {"schema": "blt.lyric-approvals/1", "source_sha256": "...",
                            "approvals": [{"voice": "tenor", "start": "3/2", "text": null,
                                           "approved_by": null}]}}

Approvals file, schema ``blt.lyric-approvals/1``: the template above with ``text`` and
``approved_by`` filled in. ``source_sha256`` must match the score, so decisions for another
version of the score are rejected. An approval may only target a note that lacks a score lyric.
Text is used exactly as written (it must be a plain, singable alias for the chosen voicebank).
"""

import json
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

from barbershop_tracks.core.pipeline.errors import ErrorCategory, PipelineError
from barbershop_tracks.core.synthesis import (
    VOICE_ORDER,
    LyricApproval,
    SynthesisPlan,
)
from barbershop_tracks.core.wording import agree, counted

REVIEW_SCHEMA = "blt.lyric-review/1"
APPROVALS_SCHEMA = "blt.lyric-approvals/1"
_ROLES = {role.value: role for role in VOICE_ORDER}


def review_report(plan: SynthesisPlan) -> dict[str, Any]:
    """The report for ``plan`` (items empty and ``ready`` true when nothing needs review)."""
    items = []
    template = []
    for item in plan.review_items:
        note = plan.voice(item.role).notes[item.note_index]
        proposal = note.lyric.proposal
        items.append(
            {
                "voice": item.role.value,
                "note_index": item.note_index,
                "start": str(item.start),
                "duration": str(note.duration),
                "midi_pitch": note.midi_pitch,
                "reason": item.reason.value,
                "detail": item.detail,
                "proposal": None
                if proposal is None
                else {"text": proposal.text, "basis": proposal.basis},
            }
        )
        template.append(
            {"voice": item.role.value, "start": str(item.start), "text": None, "approved_by": None}
        )
    return {
        "schema": REVIEW_SCHEMA,
        "source": {
            "display_name": plan.source.display_name,
            "sha256": plan.source.sha256,
        },
        "ready": not items,
        "items": items,
        "approvals_template": {
            "schema": APPROVALS_SCHEMA,
            "source_sha256": plan.source.sha256,
            "approvals": template,
        },
    }


def approvals_document(approvals: Sequence[LyricApproval], source_sha256: str) -> dict[str, Any]:
    """An approvals file (schema ``blt.lyric-approvals/1``) for ``approvals``."""
    return {
        "schema": APPROVALS_SCHEMA,
        "source_sha256": source_sha256,
        "approvals": [
            {
                "voice": a.role.value,
                "start": str(a.start),
                "text": a.text,
                "approved_by": a.approved_by,
            }
            for a in approvals
        ],
    }


def render_review_text(report: dict[str, Any], *, limit: int = 12) -> str:
    items = report["items"]
    by_voice: dict[str, int] = {}
    for item in items:
        by_voice[item["voice"]] = by_voice.get(item["voice"], 0) + 1
    lines = [
        f"{counted(len(items), 'note')} {agree(len(items), 'has', 'have')} no decided lyric "
        f"({', '.join(f'{v}: {n}' for v, n in by_voice.items())}):"
    ]
    for item in items[:limit]:
        lines.append(
            f"  {item['voice']} note {item['note_index']} at quarter {item['start']}: "
            f"{item['reason']} ({item['detail']})"
        )
    if len(items) > limit:
        lines.append(f"  ... and {len(items) - limit} more (see the review report)")
    return "\n".join(lines)


def _fail(code: str, message: str) -> PipelineError:
    return PipelineError(ErrorCategory.CONFIGURATION, code, message)


def _fraction(value: object, where: str) -> Fraction:
    if not isinstance(value, str | int) or isinstance(value, bool):
        raise _fail("APPROVALS_INVALID", f"{where}: start must be a fraction string like '3/2'")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise _fail("APPROVALS_INVALID", f"{where}: {value!r} is not a fraction") from error


def read_approvals(path: Path, *, source_sha256: str) -> tuple[LyricApproval, ...]:
    """The approvals in ``path``; template lines that still have no text stay undecided."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise _fail("APPROVALS_UNREADABLE", f"cannot read {path}: {error}") from error
    except ValueError as error:
        raise _fail("APPROVALS_INVALID", f"{path} is not valid JSON: {error}") from error
    if not isinstance(data, dict) or data.get("schema") != APPROVALS_SCHEMA:
        raise _fail("APPROVALS_INVALID", f"{path} must be a {APPROVALS_SCHEMA} object")
    if data.get("source_sha256") != source_sha256:
        raise _fail(
            "APPROVALS_WRONG_SCORE",
            "the approvals were made for a different version of the score "
            f"(expected {source_sha256[:12]}..., file says "
            f"{str(data.get('source_sha256'))[:12]}...)",
        )
    entries = data.get("approvals")
    if not isinstance(entries, list):
        raise _fail("APPROVALS_INVALID", "'approvals' must be a list")
    approvals: list[LyricApproval] = []
    for index, entry in enumerate(entries):
        where = f"approvals[{index}]"
        if not isinstance(entry, dict):
            raise _fail("APPROVALS_INVALID", f"{where} must be an object")
        voice = _ROLES.get(str(entry.get("voice")))
        if voice is None:
            raise _fail("APPROVALS_INVALID", f"{where}: voice must be one of {sorted(_ROLES)}")
        text = entry.get("text")
        if text is None:
            continue  # an undecided template line: it stays a review item, nothing is guessed
        if not isinstance(text, str) or not text.strip():
            raise _fail("APPROVALS_INVALID", f"{where}: text must be a non-empty string")
        by = entry.get("approved_by")
        if not isinstance(by, str) or not by.strip():
            raise _fail("APPROVALS_INVALID", f"{where}: approved_by must name who decided")
        approvals.append(
            LyricApproval(
                role=voice,
                start=_fraction(entry.get("start"), where),
                text=text,
                approved_by=by,
            )
        )
    return tuple(approvals)
