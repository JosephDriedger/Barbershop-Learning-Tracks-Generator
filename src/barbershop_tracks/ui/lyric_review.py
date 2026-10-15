"""The lyric review as an editable table of decisions. Pure Python (the dialog shows it).

The rows are exactly the notes that have no decided lyric (``SynthesisPlan.review_items``): a note
the score gives a lyric never appears, so it can never be overridden here. Each row is
*undecided*, a *draft* (text typed, not yet approved), *approved*, or *invalid* (text the singing
engine could not take). Only approved rows become ``LyricApproval``s. Nothing is filled in on its
own: copying the Lead's words, applying a proposal or typing one text for many notes are explicit
actions on the rows the user picked, and still need approving.

Notes that follow the Lead by the barbershop convention (``LEAD_SYLLABLE`` / ``LEAD_SUSTAIN``) are
also listed, as *follows the Lead* rows. They are decided, never block anything and are not
approved; typing a text for one and approving it overrides the rule for that note.
"""

import getpass
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path

from barbershop_tracks.core.pipeline import PipelineError, read_approvals
from barbershop_tracks.core.synthesis import LyricApproval, LyricState, SynthesisPlan
from barbershop_tracks.core.synthesis.openutau import UstxError, validate_lyric_text
from barbershop_tracks.core.synthesis.openutau.words import engine_text
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.formatting import duration_label, note_name, position_label

REASONS = {
    "lyric_absent": "No lyric in the score",
    "lyric_proposal_unapproved": "A suggested lyric is waiting for approval",
    "lyric_conflict": "The score has conflicting lyrics here",
    "lyric_unsupported_source": "The score has humming or an elision here",
}


class RowState(Enum):
    UNDECIDED = "Needs a lyric"
    DRAFT = "Not approved yet"
    APPROVED = "Approved"
    INVALID = "Cannot be sung"
    FOLLOWS = "Follows the Lead"


@dataclass(slots=True)
class LyricRow:
    role: VoiceRole
    note_index: int
    start: Fraction
    where: str
    length: str
    pitch: str
    reason: str
    detail: str
    proposal: str | None
    lead_text: str | None  # what the Lead sings at this moment: context only, never copied alone
    text: str = ""
    approved_by: str = ""
    approved: bool = False
    error: str = ""
    inherited: bool = False  # decided by the follow-the-Lead rule, listed for information

    @property
    def key(self) -> tuple[VoiceRole, Fraction]:
        return (self.role, self.start)

    @property
    def state(self) -> RowState:
        if self.error:
            return RowState.INVALID
        if self.approved:
            return RowState.APPROVED
        if self.text.strip():
            return RowState.DRAFT
        return RowState.FOLLOWS if self.inherited else RowState.UNDECIDED


def check_text(text: str) -> str:
    """Why ``text`` cannot be used as a lyric, or an empty string if it can."""
    if not text.strip():
        return ""
    try:
        validate_lyric_text(engine_text(text))  # a typographic apostrophe is the plain one
    except UstxError as error:
        return str(error.message)
    return ""


FOLLOWING_STATES = (LyricState.LEAD_SYLLABLE, LyricState.LEAD_SUSTAIN)


def has_rows(plan: SynthesisPlan) -> bool:
    """Whether the lyric review has anything to show for ``plan`` (to decide or just to see)."""
    return bool(plan.review_items) or any(
        n.lyric.state in FOLLOWING_STATES for v in plan.voices for n in v.notes
    )


def default_approver() -> str:
    try:
        return getpass.getuser() or "user"
    except Exception:
        return "user"


def _lead_text(plan: SynthesisPlan, start: Fraction) -> str | None:
    for note in plan.voice(VoiceRole.LEAD).notes:
        if note.start <= start < note.end:
            lyric = note.lyric
            if lyric.state is LyricState.SCORE_CONTINUATION:
                return None
            return lyric.text
        if note.start > start:
            break
    return None


class LyricReviewState:
    def __init__(self, baseline: SynthesisPlan, approver: str | None = None) -> None:
        self.source_sha256: str = baseline.source.sha256 or ""
        self.approver = approver or default_approver()
        self.rows: list[LyricRow] = []
        for item in baseline.review_items:
            note = baseline.voice(item.role).notes[item.note_index]
            proposal = note.lyric.proposal
            self.rows.append(
                LyricRow(
                    role=item.role,
                    note_index=item.note_index,
                    start=item.start,
                    where=position_label(item.start, baseline.meter, baseline.measures),
                    length=duration_label(note.duration),
                    pitch=note_name(note.midi_pitch),
                    reason=REASONS.get(item.reason.value, item.reason.value),
                    detail=item.detail,
                    proposal=None if proposal is None else proposal.text,
                    lead_text=None
                    if item.role is VoiceRole.LEAD
                    else _lead_text(baseline, item.start),
                )
            )
        for voice in baseline.voices:
            for note in voice.notes:
                lyric = note.lyric
                if lyric.state not in FOLLOWING_STATES:
                    continue
                sung = lyric.text if lyric.text is not None else "(holds the vowel)"
                self.rows.append(
                    LyricRow(
                        role=voice.role,
                        note_index=note.index,
                        start=note.start,
                        where=position_label(note.start, baseline.meter, baseline.measures),
                        length=duration_label(note.duration),
                        pitch=note_name(note.midi_pitch),
                        reason="Follows the Lead",
                        detail=lyric.provenance.detail,
                        proposal=None,
                        lead_text=sung,
                        inherited=True,
                    )
                )
        self._by_key = {row.key: row for row in self.rows}

    # --- counts ----------------------------------------------------------------------------

    @property
    def unresolved(self) -> int:
        return sum(1 for row in self.rows if not row.approved and not row.inherited)

    @property
    def approved_count(self) -> int:
        return sum(1 for row in self.rows if row.approved)

    @property
    def following_count(self) -> int:
        return sum(1 for row in self.rows if row.inherited and not row.approved)

    # --- editing ---------------------------------------------------------------------------

    def set_text(self, index: int, text: str) -> None:
        row = self.rows[index]
        row.text = text
        row.error = check_text(text)
        row.approved = False  # a changed text is a new draft

    def approve(self, indices: list[int]) -> int:
        """Approve the rows that have usable text; returns how many were approved."""
        done = 0
        for index in indices:
            row = self.rows[index]
            if row.text.strip() and not row.error:
                row.approved = True
                row.approved_by = self.approver
                done += 1
        return done

    def unapprove(self, indices: list[int]) -> None:
        for index in indices:
            self.rows[index].approved = False

    def fill_text(self, indices: list[int], text: str) -> int:
        """Give every picked row the same draft text (explicit batch action)."""
        for index in indices:
            self.set_text(index, text)
        return len(indices)

    def use_proposals(self, indices: list[int]) -> int:
        """Take the suggested lyric as the draft of each picked row that has one."""
        done = 0
        for index in indices:
            row = self.rows[index]
            if row.proposal:
                self.set_text(index, row.proposal)
                done += 1
        return done

    def use_lead_words(self, indices: list[int]) -> int:
        """Copy what the Lead sings into the picked rows as drafts (explicit; still to approve)."""
        done = 0
        for index in indices:
            row = self.rows[index]
            if row.role is not VoiceRole.LEAD and row.lead_text and not row.inherited:
                self.set_text(index, row.lead_text)
                done += 1
        return done

    def clear(self, indices: list[int]) -> None:
        for index in indices:
            self.set_text(index, "")

    # --- cancel support ---------------------------------------------------------------------

    def snapshot(self) -> list[tuple[str, bool, str, str]]:
        return [(r.text, r.approved, r.approved_by, r.error) for r in self.rows]

    def restore(self, saved: list[tuple[str, bool, str, str]]) -> None:
        for row, (text, approved, by, error) in zip(self.rows, saved, strict=True):
            row.text, row.approved, row.approved_by, row.error = text, approved, by, error

    # --- results and files -----------------------------------------------------------------

    def approvals(self) -> tuple[LyricApproval, ...]:
        return tuple(
            LyricApproval(
                role=row.role,
                start=row.start,
                text=row.text.strip(),
                approved_by=row.approved_by or self.approver,
            )
            for row in self.rows
            if row.approved
        )

    def load_file(self, path: Path) -> tuple[int, int]:
        """Apply an approvals file made for this score; returns (applied, not applicable)."""
        loaded = read_approvals(path, source_sha256=self.source_sha256)  # may raise PipelineError
        applied = skipped = 0
        for approval in loaded:
            row = self._by_key.get((approval.role, approval.start))
            if row is None:
                skipped += 1
                continue
            row.text = approval.text
            row.error = check_text(approval.text)
            row.approved = not row.error
            row.approved_by = approval.approved_by
            applied += 1
        return applied, skipped


__all__ = ["LyricReviewState", "LyricRow", "PipelineError", "RowState", "check_text"]
