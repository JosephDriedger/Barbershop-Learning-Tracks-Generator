"""The syllabic word state machine: reconstructs words from BEGIN/MIDDLE/END/SINGLE.

Independent of the melisma machine: an ``<extend>`` never stands in for BEGIN/MIDDLE/END, and
a rest does not close or invalidate an open word (no "words cannot cross rests" rule exists in
the specification). Syllable text is joined literally; the source is never touched.

* ``SINGLE``: its own word. ``BEGIN``, ``MIDDLE``..., ``END``: one word.
* orphan ``MIDDLE``/``END`` -> ``LYRIC_WORD_UNOPENED``; an unfinished word (a new word starts, or
  the line ends) -> ``LYRIC_WORD_UNCLOSED``.
* ``UNSPECIFIED`` (no ``<syllabic>``) outside an open word is a complete one-syllable word;
  inside an open word it is ``LYRIC_WORD_AMBIGUOUS`` (it could continue the word or start a new
  one) and is never silently read as ``END``.
"""

from dataclasses import dataclass, field

from barbershop_tracks.core.lyrics.findings import Finding, error
from barbershop_tracks.models import Lyric, LyricWord, Syllabic, WordSyllable


@dataclass(slots=True)
class _Draft:
    index: int
    syllables: list[WordSyllable] = field(default_factory=list)
    interrupted_by_rest: bool = False
    closed: bool = True


class WordBuilder:
    def __init__(self) -> None:
        self._drafts: list[_Draft] = []
        self._open: _Draft | None = None
        self._index_of: dict[tuple[int, int], int] = {}
        self.unspecified_count = 0
        self.first_unspecified: int | None = None

    def _new(self) -> _Draft:
        draft = _Draft(index=len(self._drafts))
        self._drafts.append(draft)
        return draft

    def _add(self, draft: _Draft, syllable: WordSyllable) -> None:
        draft.syllables.append(syllable)
        self._index_of[(syllable.attack_index, syllable.segment)] = draft.index

    def _abandon_open(self, findings: list[Finding], why: str) -> None:
        if self._open is not None:
            last = self._open.syllables[-1]
            findings.append(
                error(
                    "LYRIC_WORD_UNCLOSED",
                    f"the word beginning with {self._open.syllables[0].text!r} is never ended "
                    f"({why})",
                    last.attack_index,
                )
            )
            self._open.closed = False
            self._open = None

    def rest(self) -> None:
        """A rest inside an open word is recorded but does not end it."""
        if self._open is not None:
            self._open.interrupted_by_rest = True

    def add(self, attack_index: int, lyric: Lyric) -> list[Finding]:
        """Add every syllable of a text lyric (an elided lyric has more than one)."""
        findings: list[Finding] = []
        syllables = [(0, lyric.text, lyric.syllabic)] + [
            (i + 1, seg.text, seg.syllabic) for i, seg in enumerate(lyric.elided)
        ]
        for segment, text, kind in syllables:
            self._syllable(
                WordSyllable(attack_index=attack_index, segment=segment, text=text, syllabic=kind),
                findings,
            )
        return findings

    def _syllable(self, syllable: WordSyllable, findings: list[Finding]) -> None:
        kind = syllable.syllabic
        at = syllable.attack_index
        if kind is Syllabic.SINGLE:
            self._abandon_open(findings, "a single-syllable word followed")
            self._add(self._new(), syllable)
        elif kind is Syllabic.BEGIN:
            self._abandon_open(findings, "a new word began")
            draft = self._new()
            draft.closed = False
            self._add(draft, syllable)
            self._open = draft
        elif kind is Syllabic.MIDDLE:
            if self._open is None:
                findings.append(
                    error(
                        "LYRIC_WORD_UNOPENED",
                        f"{syllable.text!r} is a middle syllable with no word open",
                        at,
                    )
                )
                draft = self._new()
                draft.closed = False
                self._add(draft, syllable)
                self._open = draft  # recover so a following END does not repeat the error
            else:
                self._add(self._open, syllable)
        elif kind is Syllabic.END:
            if self._open is None:
                findings.append(
                    error(
                        "LYRIC_WORD_UNOPENED",
                        f"{syllable.text!r} ends a word that was never begun",
                        at,
                    )
                )
                self._add(self._new(), syllable)
            else:
                self._add(self._open, syllable)
                self._open.closed = True
                self._open = None
        else:  # UNSPECIFIED
            self.unspecified_count += 1
            if self.first_unspecified is None:
                self.first_unspecified = at
            if self._open is not None:
                findings.append(
                    error(
                        "LYRIC_WORD_AMBIGUOUS",
                        f"{syllable.text!r} has no <syllabic> inside the open word beginning "
                        f"with {self._open.syllables[0].text!r}; it could continue or restart it",
                        at,
                    )
                )
            self._add(
                self._new(), syllable
            )  # never silently joined to, or read as END of, the word

    def finish(self) -> list[Finding]:
        findings: list[Finding] = []
        self._abandon_open(findings, "the line ended")
        return findings

    def words(self) -> tuple[LyricWord, ...]:
        return tuple(
            LyricWord(
                index=d.index,
                syllables=tuple(d.syllables),
                interrupted_by_rest=d.interrupted_by_rest,
                closed=d.closed,
            )
            for d in self._drafts
        )

    def word_indices(self, attack_index: int, syllable_count: int) -> tuple[int, ...]:
        return tuple(self._index_of[(attack_index, s)] for s in range(syllable_count))
