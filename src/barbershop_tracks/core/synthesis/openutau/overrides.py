"""Pronunciation overrides: a person's decision how one word, in one place of one score, is pronounced.

BLT never changes a lyric of the score and never guesses a pronunciation. When the pronunciation
dictionary has no entry for a word, a person may say how that word, *at that place*, is sung. The
decision is an explicit input of the run, like a lyric approval, and it is scoped narrowly:

* to **one score**: it carries the SHA-256 of the MusicXML file it was made for;
* to **one voice and one note**: the note of ``role`` that starts at ``start`` (quarter notes), the first
  note of the word as the engine receives it;
* to **one word**: the text the engine receives for that note (the score's syllables put together,
  see ``words.py``), so an override made for ``ev'ry`` is refused where the score says something else;
* to **one phonemizer**, with the notation that phonemizer takes (``alphabet``).

The same word elsewhere in the score is **not** affected; each occurrence needs its own decision.

The override reaches the engine only as OpenUtau's phonetic hint, ``word[sym bol s]``, written in the
project file that is sent to the engine. The plan, the review screens and the package's record keep
the score's own lyric text; the pronunciation is recorded next to it, never in place of it.

Which symbols a phonemizer knows is the phonemizer's own business: the render host asks it (a symbol it
does not know is refused before anything is rendered). Here only the form of the input is checked.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from barbershop_tracks.core.synthesis.errors import SynthesisPlanError
from barbershop_tracks.core.synthesis.openutau.words import (
    DICTIONARY_PHONEMIZERS,
    WordJoin,
    assemble_words,
    engine_text,
)
from barbershop_tracks.core.synthesis.plan import (
    LyricState,
    SynthesisPlan,
    VoiceEngineRef,
)
from barbershop_tracks.models import VoiceRole

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
ENGLISH_VCCV = "OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer"
ENGLISH_XSAMPA = "OpenUtau.Plugin.Builtin.EnXSampaPhonemizer"

# the notation each dictionary phonemizer takes in a phonetic hint
ALPHABETS: Mapping[str, str] = {
    ARPASING: "arpabet",
    ENGLISH_VCCV: "vccv",
    ENGLISH_XSAMPA: "xsampa",
}

ALPHABET_TITLES: Mapping[str, str] = {
    "arpabet": "ARPAbet (the notation of the CMU dictionary), lower case, for example: eh v r iy",
    "vccv": "the English VCCV symbols of this phonemizer, for example: E v r i",
    "xsampa": "X-SAMPA, for example: E v r i",
}

_SYMBOL = re.compile(r"^[^\s\[\]\x00-\x1f\x7f]+$")
_MAX_SYMBOLS = 64
_TEXT_STATES = (LyricState.SCORE_LYRIC, LyricState.USER_APPROVED, LyricState.LEAD_SYLLABLE)
_CONTINUATIONS = (LyricState.SCORE_CONTINUATION, LyricState.LEAD_SUSTAIN)


class OverrideError(SynthesisPlanError):
    """A pronunciation override that cannot be used. ``code`` says why; nothing was rendered."""


def alphabet_for(phonemizer: str) -> str | None:
    """The notation ``phonemizer`` takes in a phonetic hint; None if it takes none."""
    return ALPHABETS.get(phonemizer)


def parse_symbols(text: str) -> tuple[str, ...]:
    """The symbols of ``text`` (separated by spaces) after checking their form; raises OverrideError."""
    symbols = tuple(text.split())
    if not symbols:
        raise OverrideError("OVERRIDE_EMPTY", "a pronunciation needs at least one symbol")
    if len(symbols) > _MAX_SYMBOLS:
        raise OverrideError(
            "OVERRIDE_TOO_LONG", f"a pronunciation has at most {_MAX_SYMBOLS} symbols"
        )
    for symbol in symbols:
        if not _SYMBOL.match(symbol):
            raise OverrideError(
                "OVERRIDE_SYMBOL_FORM",
                f"{symbol!r} cannot be a phoneme symbol (no brackets, spaces or control characters)",
            )
    return symbols


@dataclass(frozen=True, slots=True, kw_only=True)
class PronunciationOverride:
    """A person's decision that the word at ``role``/``start`` is sung to ``symbols``."""

    role: VoiceRole
    start: Fraction  # quarter notes: the first note of the word
    word: str  # the word as the engine receives it for that note (what BLT named)
    phonemizer: str
    symbols: tuple[str, ...]
    approved_by: str
    source_sha256: str  # the score this decision is for

    def __post_init__(self) -> None:
        if not self.word.strip() or self.word != self.word.strip():
            raise OverrideError("OVERRIDE_WORD", "an override must name the word it is for")
        if self.phonemizer not in ALPHABETS:
            raise OverrideError(
                "OVERRIDE_PHONEMIZER_UNSUPPORTED",
                f"{self.phonemizer} takes no pronunciations; they can be given for "
                + ", ".join(sorted(p.rsplit(".", 1)[-1] for p in ALPHABETS)),
            )
        if not self.approved_by.strip():
            raise OverrideError("OVERRIDE_APPROVER", "an override must name who decided it")
        if len(self.source_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.source_sha256
        ):
            raise OverrideError("OVERRIDE_SOURCE", "an override is bound to the score's SHA-256")
        parse_symbols(" ".join(self.symbols))

    @property
    def alphabet(self) -> str:
        return ALPHABETS[self.phonemizer]

    @property
    def hint(self) -> str:
        """The text that goes between the brackets."""
        return " ".join(self.symbols)

    @property
    def key(self) -> tuple[VoiceRole, Fraction]:
        return (self.role, self.start)


@dataclass(frozen=True, slots=True)
class ResolvedOverride:
    """An override matched to its note: where the engine receives the word, and what the score says."""

    override: PronunciationOverride
    note_index: int
    score_lyrics: tuple[str, ...]  # the score's own text on the notes of the word, verbatim
    # set only when BLT built the pronunciation itself from dictionary entries (no person decided it)
    composed_from: tuple[str, ...] = ()
    composed_how: str = ""
    composed_guessed: bool = False  # from the spelling alone, not from dictionary entries


@dataclass(frozen=True, slots=True)
class ResolvedOverrides:
    by_note: Mapping[tuple[VoiceRole, int], ResolvedOverride]

    def __bool__(self) -> bool:
        return bool(self.by_note)

    def for_note(self, role: VoiceRole, index: int) -> ResolvedOverride | None:
        return self.by_note.get((role, index))

    def all(self) -> tuple[ResolvedOverride, ...]:
        return tuple(self.by_note.values())


NO_OVERRIDES = ResolvedOverrides({})


def _sent_word(plan: SynthesisPlan, role: VoiceRole, joined: WordJoin, index: int) -> str | None:
    note = plan.voice(role).notes[index]
    if note.lyric.state not in _TEXT_STATES or note.lyric.text is None:
        return None
    return engine_text(joined.whole.get(index, note.lyric.text))


def score_lyrics_of(
    plan: SynthesisPlan, role: VoiceRole, joined: WordJoin, index: int
) -> tuple[str, ...]:
    """The text the score (or the Lead it follows) has on the notes that make up the word."""
    notes = plan.voice(role).notes
    first = notes[index].lyric
    texts = [first.provenance.source_text or first.text or ""]
    if index in joined.whole:
        k = index + 1
        while k < len(notes) and (k in joined.follow or notes[k].lyric.state in _CONTINUATIONS):
            if k in joined.follow:
                lyric = notes[k].lyric
                texts.append(lyric.provenance.source_text or lyric.text or "")
            k += 1
    return tuple(texts)


def resolve_overrides(
    plan: SynthesisPlan, overrides: Sequence[PronunciationOverride], *, source_sha256: str | None
) -> ResolvedOverrides:
    """Match each override to its note, or say exactly why it cannot be used.

    Refused (nothing is skipped silently): an override made for another score, for another
    phonemizer than the voice's, for a note that does not exist or does not start a word the engine
    receives, for a word other than the score gives there, or a second override for one note.
    """
    if not overrides:
        return NO_OVERRIDES
    resolved: dict[tuple[VoiceRole, int], ResolvedOverride] = {}
    seen: set[tuple[VoiceRole, Fraction]] = set()
    joins: dict[VoiceRole, WordJoin] = {}
    for item in overrides:
        label = f"{item.role.display_name}, {item.word!r} at quarter {item.start}"
        if source_sha256 is not None and item.source_sha256 != source_sha256:
            raise OverrideError(
                "OVERRIDE_WRONG_SCORE",
                f"{label}: this pronunciation was decided for a different version of the score "
                f"(it says {item.source_sha256[:12]}..., the score is {source_sha256[:12]}...); "
                "decide it again for this score",
            )
        if item.key in seen:
            raise OverrideError("OVERRIDE_DUPLICATE", f"{label}: two pronunciations for one note")
        seen.add(item.key)
        ref: VoiceEngineRef = plan.engine_ref(item.role)
        if ref.phonemizer != item.phonemizer:
            raise OverrideError(
                "OVERRIDE_PHONEMIZER_MISMATCH",
                f"{label}: it was written for {item.phonemizer.rsplit('.', 1)[-1]} but "
                f"{item.role.display_name} uses {ref.phonemizer.rsplit('.', 1)[-1]}; the notation "
                "of one phonemizer is not valid for another",
            )
        if ref.phonemizer not in DICTIONARY_PHONEMIZERS:
            raise OverrideError(
                "OVERRIDE_PHONEMIZER_UNSUPPORTED", f"{label}: no pronunciations here"
            )
        voice = plan.voice(item.role)
        note = next((n for n in voice.notes if n.start == item.start), None)
        if note is None:
            raise OverrideError(
                "OVERRIDE_NO_NOTE",
                f"{label}: {item.role.display_name} has no note starting there "
                "(the score or the voice assignment is not the one this was decided for)",
            )
        joined = joins.setdefault(item.role, assemble_words(plan, voice))
        if note.index in joined.follow:
            raise OverrideError(
                "OVERRIDE_NOT_WORD_START",
                f"{label}: that note continues a word that starts earlier; "
                "the pronunciation belongs on the first note of the word",
            )
        sent = _sent_word(plan, item.role, joined, note.index)
        if sent is None:
            raise OverrideError(
                "OVERRIDE_NO_WORD",
                f"{label}: that note sings no word (it continues a held syllable)",
            )
        if sent != item.word:
            raise OverrideError(
                "OVERRIDE_WORD_MISMATCH",
                f"{label}: the score now has {sent!r} there; this pronunciation was decided for "
                f"{item.word!r}",
            )
        resolved[(item.role, note.index)] = ResolvedOverride(
            item, note.index, score_lyrics_of(plan, item.role, joined, note.index)
        )
    return ResolvedOverrides(resolved)


__all__ = [
    "ALPHABETS",
    "ALPHABET_TITLES",
    "ARPASING",
    "ENGLISH_VCCV",
    "ENGLISH_XSAMPA",
    "NO_OVERRIDES",
    "OverrideError",
    "PronunciationOverride",
    "ResolvedOverride",
    "ResolvedOverrides",
    "alphabet_for",
    "parse_symbols",
    "resolve_overrides",
    "score_lyrics_of",
]
