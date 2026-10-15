"""The pronunciation review: the words BLT could not look up, and what a person decides for each place.

No Qt here (``pronunciation_dialog.py`` shows it). Each row is **one voice at one note**: the place where a
word the dictionary lacks is sung. A row is *undecided* until the person types its pronunciation, in the
notation of that voice's pronunciation engine; it never receives a default, and nothing is copied
from one place to another unless the person asks (``fill_same_place``, which touches only the other
voices at the same note and word). The score's own text is shown as it is written and is never changed.

Only decided rows become :class:`PronunciationOverride` objects, each bound to the score's SHA-256.
"""

import getpass
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path
from typing import Any

from barbershop_tracks.core.pipeline import (
    ErrorCategory,
    PipelineError,
    notation_help,
    overrides_document,
    overrides_from_document,
)
from barbershop_tracks.core.synthesis.openutau import (
    ALPHABETS,
    OverrideError,
    PronunciationOverride,
    parse_symbols,
)
from barbershop_tracks.models import VoiceRole

_ROLES = {role.value: role for role in VoiceRole}


class RowState(Enum):
    UNDECIDED = "Needs a pronunciation"
    DECIDED = "Decided"
    INVALID = "Cannot be used"


@dataclass(slots=True)
class PronunciationRow:
    role: VoiceRole
    start: Fraction
    where: str  # "bar 4, beat 1"
    word: str  # the word the engine receives for the note (what BLT names)
    score_lyrics: tuple[str, ...]  # the score's own text on the notes of the word, verbatim
    phonemizer: str | None
    fragment: bool = False
    text: str = ""
    error: str = ""  # the form of the text, or what the engine said about it
    note: str = ""  # an informational remark (for example, that the engine accepted it)

    @property
    def key(self) -> tuple[VoiceRole, Fraction]:
        return (self.role, self.start)

    @property
    def supported(self) -> bool:
        return self.phonemizer in ALPHABETS

    @property
    def state(self) -> RowState:
        if self.error:
            return RowState.INVALID
        return RowState.DECIDED if self.text.strip() else RowState.UNDECIDED

    @property
    def notation(self) -> str:
        return notation_help(self.phonemizer)


def default_approver() -> str:
    try:
        return getpass.getuser() or "user"
    except Exception:
        return "user"


def _form_problem(text: str) -> str:
    if not text.strip():
        return ""
    try:
        parse_symbols(text)
    except OverrideError as error:
        return error.message
    return ""


class PronunciationState:
    """What the person has decided for a score, row by row."""

    def __init__(self, source_sha256: str, approver: str | None = None) -> None:
        self.source_sha256 = source_sha256
        self.approver = approver or default_approver()
        self.rows: list[PronunciationRow] = []

    # --- building the rows ----------------------------------------------------------------------

    def add_blocked(self, unknown_words: Sequence[Mapping[str, Any]]) -> None:
        """One row per place ``details['unknown_words']`` names (existing rows are kept)."""
        for item in unknown_words:
            role = _ROLES.get(str(item.get("role")))
            start = item.get("start")
            if role is None or start is None:
                continue  # a place BLT could not locate in the score cannot be decided
            row = PronunciationRow(
                role=role,
                start=Fraction(str(start)),
                where=str(item.get("where", "")),
                word=str(item.get("lyric", "")),
                score_lyrics=tuple(str(x) for x in item.get("score_lyrics", ())),
                phonemizer=None if item.get("phonemizer") is None else str(item["phonemizer"]),
                fragment=bool(item.get("fragment", False)),
            )
            if self._find(row.key) is None:
                self.rows.append(row)
        self._sort()

    def adopt(
        self,
        overrides: Sequence[PronunciationOverride],
        where: Mapping[tuple[VoiceRole, Fraction], str],
    ) -> None:
        """Rows for decisions that already exist (so that they can be revised), with their text."""
        for item in overrides:
            row = self._find(item.key)
            if row is None:
                row = PronunciationRow(
                    role=item.role,
                    start=item.start,
                    where=where.get(item.key, f"quarter {item.start}"),
                    word=item.word,
                    score_lyrics=(),
                    phonemizer=item.phonemizer,
                )
                self.rows.append(row)
            row.text = item.hint
            row.error = ""
        self._sort()

    def _sort(self) -> None:
        order = {role: i for i, role in enumerate(_ROLES.values())}
        self.rows.sort(key=lambda r: (r.start, order.get(r.role, 99)))

    def _find(self, key: tuple[VoiceRole, Fraction]) -> PronunciationRow | None:
        return next((r for r in self.rows if r.key == key), None)

    # --- editing --------------------------------------------------------------------------------

    def set_text(self, index: int, text: str) -> None:
        row = self.rows[index]
        row.text = " ".join(text.split())
        row.error = _form_problem(row.text)
        row.note = ""

    def clear(self, indices: Sequence[int]) -> None:
        for index in indices:
            row = self.rows[index]
            row.text, row.error, row.note = "", "", ""

    def fill_same_place(self, index: int) -> int:
        """Give the other voices that sing the same word at the same place this row's pronunciation.

        Only rows at the same note position, with the same word and the same pronunciation engine
        are touched, and only when the person asks; the same word elsewhere is never affected.
        """
        source = self.rows[index]
        if not source.text.strip() or source.error:
            return 0
        changed = 0
        for row in self.rows:
            if (
                row is not source
                and row.start == source.start
                and row.word == source.word
                and row.phonemizer == source.phonemizer
                and row.text != source.text
            ):
                row.text, row.error, row.note = source.text, "", ""
                changed += 1
        return changed

    def mark_refused(self, refusals: Sequence[Mapping[str, Any]]) -> int:
        """Record what the engine refused (``details['invalid_hints']``) on the rows it concerns."""
        marked = 0
        for item in refusals:
            role = _ROLES.get(str(item.get("role")))
            start = item.get("start")
            if role is None or start is None:
                continue
            row = self._find((role, Fraction(str(start))))
            if row is None:
                continue
            symbol = item.get("symbol")
            reason = str(item.get("reason", ""))
            if reason == "symbol_unknown" and symbol is not None:
                row.error = f"the pronunciation engine does not know the symbol {symbol!r}"
            elif reason == "engine_error":
                row.error = "the pronunciation engine failed on these symbols"
            else:
                row.error = "these symbols make no sound"
            marked += 1
        return marked

    def mark_accepted(self, reports: Sequence[Mapping[str, Any]]) -> None:
        """Note, on each decided row the engine accepted, the sounds it made of it."""
        for item in reports:
            role = next((r for r in VoiceRole if r.display_name == item.get("track")), None)
            position = item.get("position")
            if role is None or not isinstance(position, int):
                continue
            row = self._find((role, Fraction(position, 480)))
            if row is not None and not row.error:
                row.note = "accepted; the engine sings: " + ", ".join(
                    str(p) for p in item.get("phonemes", [])
                )

    # --- results --------------------------------------------------------------------------------

    @property
    def undecided(self) -> int:
        return sum(1 for r in self.rows if r.state is RowState.UNDECIDED)

    @property
    def decided(self) -> int:
        return sum(1 for r in self.rows if r.state is RowState.DECIDED)

    @property
    def invalid(self) -> int:
        return sum(1 for r in self.rows if r.state is RowState.INVALID)

    def overrides(self) -> tuple[PronunciationOverride, ...]:
        """The decided rows as overrides; a row with a problem or without symbols is left out."""
        found: list[PronunciationOverride] = []
        for row in self.rows:
            if row.state is not RowState.DECIDED or not row.supported or row.phonemizer is None:
                continue
            found.append(
                PronunciationOverride(
                    role=row.role,
                    start=row.start,
                    word=row.word,
                    phonemizer=row.phonemizer,
                    symbols=parse_symbols(row.text),
                    approved_by=self.approver,
                    source_sha256=self.source_sha256,
                )
            )
        return tuple(found)

    def document(self) -> dict[str, Any]:
        where = {row.key: row.where for row in self.rows}
        return overrides_document(
            self.overrides(),
            self.source_sha256,
            where={(role.value, start): text for (role, start), text in where.items()},
        )

    def load_file(self, path: Path) -> tuple[int, int]:
        """Apply the decisions in ``path`` to the rows; returns (applied, ignored).

        A file made for another version of the score is refused as a whole (``PipelineError``).
        Entries that match no row (another voice, place or word) are counted and ignored here;
        generation refuses them if they are kept, so nothing is applied to a place it was not
        decided for.
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise PipelineError(
                ErrorCategory.CONFIGURATION, "OVERRIDES_UNREADABLE", f"cannot read {path}: {error}"
            ) from error
        applied = ignored = 0
        for item in overrides_from_document(
            data, source_sha256=self.source_sha256, label=str(path)
        ):
            row = self._find(item.key)
            if row is None or row.word != item.word or row.phonemizer != item.phonemizer:
                ignored += 1
                continue
            row.text, row.error, row.note = item.hint, "", ""
            applied += 1
        return applied, ignored


__all__ = ["PronunciationRow", "PronunciationState", "RowState", "default_approver"]
