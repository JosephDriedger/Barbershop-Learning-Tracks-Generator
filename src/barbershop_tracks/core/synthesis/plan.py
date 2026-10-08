"""The engine-neutral synthesis plan: what is to be sung, by whom, exactly.

Immutable and validated at construction. It contains nothing specific to OpenUtau (no ticks, no
``+`` tokens, no USTX field), and it keeps the evidence for every lyric: where it came from and in
what state it is. A note whose lyric is not decided is a **review item** and makes the plan not
ready; it never silently receives a default syllable.

Lyric states (all five are distinct and none implies another):

* ``SCORE_LYRIC``: the score supplies this syllable for this note;
* ``SCORE_CONTINUATION``: the score marks this note as the continuation of an earlier syllable (a
  melisma); it carries no text of its own;
* ``ABSENT``: the score gives this sounding note no usable lyric (also: unsupported or conflicting
  lyric material, see ``ReviewReason``);
* ``INFERRED_PROPOSAL``: a lyric proposed from another part. A proposal is **not** a lyric: the note
  still has no text and still needs a decision;
* ``USER_APPROVED``: a lyric a person explicitly approved for this note.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from barbershop_tracks.core.synthesis.errors import SynthesisPlanError
from barbershop_tracks.models import VoiceRole

VOICE_ORDER: tuple[VoiceRole, ...] = (
    VoiceRole.TENOR,
    VoiceRole.LEAD,
    VoiceRole.BARITONE,
    VoiceRole.BASS,
)


class LyricState(Enum):
    SCORE_LYRIC = "score_lyric"
    SCORE_CONTINUATION = "score_continuation"
    ABSENT = "absent"
    INFERRED_PROPOSAL = "inferred_proposal"
    USER_APPROVED = "user_approved"


class ReviewReason(Enum):
    LYRIC_ABSENT = "lyric_absent"
    LYRIC_PROPOSAL_UNAPPROVED = "lyric_proposal_unapproved"
    LYRIC_CONFLICT = "lyric_conflict"
    LYRIC_UNSUPPORTED_SOURCE = "lyric_unsupported_source"  # humming, laughing, elision


@dataclass(frozen=True, slots=True, kw_only=True)
class LyricProposal:
    """A lyric proposed (never applied) for the note of ``role`` starting at ``start``."""

    role: VoiceRole
    start: Fraction
    text: str
    basis: str  # how it was inferred, in words a reviewer can check
    basis_role: VoiceRole | None = None  # the part it was inferred from, if any

    def __post_init__(self) -> None:
        _require_text(self.text, "proposal text")
        if not self.basis.strip():
            raise SynthesisPlanError(
                "PLAN_PROPOSAL_BASIS", "a proposal must say how it was inferred"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class LyricApproval:
    """A person's explicit decision that the note of ``role`` at ``start`` is sung to ``text``."""

    role: VoiceRole
    start: Fraction
    text: str
    approved_by: str = "user"
    proposal_basis: str | None = None  # the proposal this approves, if it came from one

    def __post_init__(self) -> None:
        _require_text(self.text, "approved text")
        if not self.approved_by.strip():
            raise SynthesisPlanError("PLAN_APPROVAL_BY", "an approval must name who approved it")


@dataclass(frozen=True, slots=True, kw_only=True)
class LyricProvenance:
    """Evidence for a note's lyric state, always from the performed score and its analysis."""

    line_id: str
    performed_start: Fraction
    analysis_role: str  # the M3 attack role ("syllable", "melisma_continuation", "missing", ...)
    source_text: str | None = None  # the score's own lyric text, verbatim, if it has any
    syllabic: str | None = None
    melisma_origin_start: Fraction | None = None  # start of the note that opened the melisma
    melisma_basis: str | None = None
    detail: str = ""  # why a lyric is unsupported or in conflict


@dataclass(frozen=True, slots=True, kw_only=True)
class NoteLyric:
    state: LyricState
    text: str | None
    provenance: LyricProvenance
    proposal: LyricProposal | None = None
    approval: LyricApproval | None = None

    def __post_init__(self) -> None:
        state = self.state
        if state in (LyricState.SCORE_LYRIC, LyricState.USER_APPROVED):
            _require_text(self.text, f"{state.value} text")
        elif self.text is not None:
            raise SynthesisPlanError(
                "PLAN_LYRIC_STATE", f"a {state.value} note carries no text, got {self.text!r}"
            )
        if state is LyricState.INFERRED_PROPOSAL and self.proposal is None:
            raise SynthesisPlanError("PLAN_LYRIC_STATE", "an inferred proposal needs its proposal")
        if state is not LyricState.INFERRED_PROPOSAL and self.proposal is not None:
            raise SynthesisPlanError("PLAN_LYRIC_STATE", f"a {state.value} note has no proposal")
        if state is LyricState.USER_APPROVED:
            if self.approval is None or self.approval.text != self.text:
                raise SynthesisPlanError(
                    "PLAN_LYRIC_STATE", "approved text must match its approval"
                )
        elif self.approval is not None:
            raise SynthesisPlanError("PLAN_LYRIC_STATE", f"a {state.value} note has no approval")

    @property
    def is_decided(self) -> bool:
        return (
            self.state is not LyricState.ABSENT and self.state is not LyricState.INFERRED_PROPOSAL
        )

    @property
    def review_reason(self) -> ReviewReason | None:
        if self.is_decided:
            return None
        if self.state is LyricState.INFERRED_PROPOSAL:
            return ReviewReason.LYRIC_PROPOSAL_UNAPPROVED
        role = self.provenance.analysis_role
        if role == "conflict":
            return ReviewReason.LYRIC_CONFLICT
        if role in ("humming", "laughing") or self.provenance.detail.startswith("unsupported"):
            return ReviewReason.LYRIC_UNSUPPORTED_SOURCE
        return ReviewReason.LYRIC_ABSENT


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedNote:
    """One sounding performed note: exact timing, the sounding pitch, and its lyric decision."""

    index: int  # position within the voice
    start: Fraction  # quarter notes
    duration: Fraction  # quarter notes
    midi_pitch: int  # the performed *sounding* pitch
    lyric: NoteLyric

    def __post_init__(self) -> None:
        if self.start < 0 or self.duration <= 0:
            raise SynthesisPlanError(
                "PLAN_NOTE_TIMING", f"bad note timing {self.start}+{self.duration}"
            )
        if not 0 <= self.midi_pitch <= 127:
            raise SynthesisPlanError(
                "PLAN_NOTE_PITCH", f"MIDI pitch {self.midi_pitch} out of range"
            )

    @property
    def end(self) -> Fraction:
        return self.start + self.duration


@dataclass(frozen=True, slots=True, kw_only=True)
class VoicePlan:
    role: VoiceRole
    line_id: str
    part_name: str
    notes: tuple[PlannedNote, ...]

    def __post_init__(self) -> None:
        if not self.notes:
            raise SynthesisPlanError("PLAN_VOICE_EMPTY", f"{self.role.display_name} has no notes")
        for expected, note in enumerate(self.notes):
            if note.index != expected:
                raise SynthesisPlanError("PLAN_NOTE_INDEX", f"{self.role.display_name} note index")
        for earlier, later in zip(self.notes, self.notes[1:], strict=False):
            if later.start < earlier.end:
                raise SynthesisPlanError(
                    "PLAN_VOICE_OVERLAP",
                    f"{self.role.display_name} sounds two notes at {later.start}",
                )

    @property
    def end(self) -> Fraction:
        return self.notes[-1].end


@dataclass(frozen=True, slots=True, kw_only=True)
class TempoPoint:
    position: Fraction
    bpm: Fraction  # exact; engine adapters decide how (and whether) it can be represented

    def __post_init__(self) -> None:
        if self.position < 0 or self.bpm <= 0:
            raise SynthesisPlanError("PLAN_TEMPO", f"bad tempo {self.bpm} at {self.position}")


@dataclass(frozen=True, slots=True, kw_only=True)
class MeterPoint:
    position: Fraction
    beats: int
    beat_type: int

    def __post_init__(self) -> None:
        if self.position < 0 or self.beats <= 0 or self.beat_type <= 0:
            raise SynthesisPlanError("PLAN_METER", f"bad meter {self.beats}/{self.beat_type}")

    @property
    def measure_length(self) -> Fraction:
        return Fraction(4 * self.beats, self.beat_type)


@dataclass(frozen=True, slots=True, kw_only=True)
class VoiceEngineRef:
    """Opaque references to what the engine should sing with. Never a hard-coded voicebank.

    ``singer`` names a user-installed voicebank, ``phonemizer`` the phonemizer, ``renderer`` the
    rendering method; the three are chosen independently. The engine adapter validates them against
    what is actually installed; a plan only guarantees they are stated.
    """

    singer: str
    phonemizer: str
    renderer: str

    def __post_init__(self) -> None:
        for name, value in (
            ("singer", self.singer),
            ("phonemizer", self.phonemizer),
            ("renderer", self.renderer),
        ):
            if not value or value != value.strip() or any(ord(c) < 32 for c in value):
                raise SynthesisPlanError(
                    "PLAN_ENGINE_REF", f"{name} must be a non-empty plain string"
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceIdentity:
    """Which score this plan came from. Identity is the hash; the name is for display."""

    display_name: str
    sha256: str | None = None
    title: str | None = None

    def __post_init__(self) -> None:
        if not self.display_name.strip():
            raise SynthesisPlanError("PLAN_SOURCE", "a source needs a display name")
        digest = self.sha256
        if digest is not None and (
            len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise SynthesisPlanError("PLAN_SOURCE", "sha256 must be 64 lowercase hex digits")


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputRequirements:
    """What the synthesis must deliver: one stem per voice, spanning the performed length."""

    performed_length: Fraction  # quarter notes; later stems are padded to this, never trimmed
    stem_roles: tuple[VoiceRole, ...] = VOICE_ORDER

    def __post_init__(self) -> None:
        if self.performed_length <= 0:
            raise SynthesisPlanError("PLAN_OUTPUT", "the performed length must be positive")
        if tuple(self.stem_roles) != VOICE_ORDER:
            raise SynthesisPlanError("PLAN_OUTPUT", "one stem is required per TTBB voice, in order")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewItem:
    role: VoiceRole
    note_index: int
    start: Fraction
    reason: ReviewReason
    detail: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SynthesisPlan:
    source: SourceIdentity
    voices: tuple[VoicePlan, ...]
    tempo: tuple[TempoPoint, ...]
    meter: tuple[MeterPoint, ...]
    engine_refs: tuple[tuple[VoiceRole, VoiceEngineRef], ...]
    output: OutputRequirements

    def __post_init__(self) -> None:
        if tuple(v.role for v in self.voices) != VOICE_ORDER:
            raise SynthesisPlanError(
                "PLAN_ROLES", "voices must be exactly Tenor, Lead, Baritone, Bass"
            )
        lines = [v.line_id for v in self.voices]
        if len(set(lines)) != len(lines):
            raise SynthesisPlanError("PLAN_ROLES", "one line is used for several roles")
        if tuple(role for role, _ in self.engine_refs) != VOICE_ORDER:
            raise SynthesisPlanError(
                "PLAN_ENGINE_REF", "an engine reference is needed per voice, in order"
            )
        if not self.tempo or self.tempo[0].position != 0:
            raise SynthesisPlanError("PLAN_TEMPO", "a tempo is required at position zero")
        for earlier, later in zip(self.tempo, self.tempo[1:], strict=False):
            if later.position <= earlier.position:
                raise SynthesisPlanError("PLAN_TEMPO", "tempo positions must strictly increase")
        for earlier_m, later_m in zip(self.meter, self.meter[1:], strict=False):
            if later_m.position <= earlier_m.position:
                raise SynthesisPlanError("PLAN_METER", "meter positions must strictly increase")
        if any(v.end > self.output.performed_length for v in self.voices):
            raise SynthesisPlanError("PLAN_OUTPUT", "a voice sounds past the performed length")

    def voice(self, role: VoiceRole) -> VoicePlan:
        return self.voices[VOICE_ORDER.index(role)]

    def engine_ref(self, role: VoiceRole) -> VoiceEngineRef:
        return self.engine_refs[VOICE_ORDER.index(role)][1]

    @property
    def review_items(self) -> tuple[ReviewItem, ...]:
        """Every unresolved decision, derived from the notes so it can never disagree with them."""
        items: list[ReviewItem] = []
        for voice in self.voices:
            for note in voice.notes:
                reason = note.lyric.review_reason
                if reason is not None:
                    detail = note.lyric.provenance.detail or reason.value
                    if note.lyric.proposal is not None:
                        detail = (
                            f"proposed {note.lyric.proposal.text!r}: {note.lyric.proposal.basis}"
                        )
                    items.append(
                        ReviewItem(
                            role=voice.role,
                            note_index=note.index,
                            start=note.start,
                            reason=reason,
                            detail=detail,
                        )
                    )
        return tuple(items)

    @property
    def is_ready(self) -> bool:
        return not self.review_items


def engine_refs_from(
    mapping: Mapping[VoiceRole, VoiceEngineRef],
) -> tuple[tuple[VoiceRole, VoiceEngineRef], ...]:
    """Order a role mapping the way a plan wants it; a missing or extra role is an error."""
    if set(mapping) != set(VOICE_ORDER):
        raise SynthesisPlanError(
            "PLAN_ENGINE_REF", "an engine reference is needed for each of the four voices"
        )
    return tuple((role, mapping[role]) for role in VOICE_ORDER)


def _require_text(text: str | None, what: str) -> None:
    if text is None or not text.strip():
        raise SynthesisPlanError("PLAN_LYRIC_TEXT", f"{what} must not be empty")
