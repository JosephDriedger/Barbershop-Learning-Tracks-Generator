"""Words the pronunciation dictionary lacks: name them, per voice and bar, before rendering.

The render host phonemizes the project first. A dictionary phonemizer (Arpasing, English VCCV,
X-SAMPA) that cannot look a word up would otherwise turn it into a voicebank alias or into the
text "word not found", both of which sing as silence. The host stops instead (exit 11) and
reports each word with the track and the tick of the note. This module turns that report into
what the singer needs: which voice, which bar and beat, which word. BLT never invents a
pronunciation and never drops the syllable: it stops and says so.

The same stop covers a pronunciation that a person gave (a phonetic override, see
core/synthesis/openutau/overrides.py) which the engine refuses: a symbol it does not know, or a
note that would make no sound. Each such problem is placed in the score the same way.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from barbershop_tracks.core.rendering.errors import PronunciationError
from barbershop_tracks.core.synthesis import SynthesisPlan
from barbershop_tracks.core.synthesis.openutau.overrides import score_lyrics_of
from barbershop_tracks.core.synthesis.openutau.words import assemble_words, is_word_fragment
from barbershop_tracks.core.synthesis.positions import position_label

TICKS_PER_QUARTER = 480  # the USTX resolution BLT writes (core/synthesis/openutau/ustx.py)


@dataclass(frozen=True, slots=True)
class UnknownWord:
    voice: str  # "Lead"
    role: str | None  # "lead"; None when the host named a track BLT does not know
    note_index: int | None  # within the voice
    start: Fraction | None  # quarter notes
    where: str  # "bar 9, beat 2"
    lyric: str  # the note's lyric as the score gives it
    word: str  # the part of it with no entry
    fragment: bool = False  # a syllable of a longer word that this part does not sing whole
    phonemizer: str | None = None  # the voice's pronunciation engine (the notation a hint takes)
    score_lyrics: tuple[str, ...] = ()  # the score's own text on the notes of the word, verbatim

    def as_detail(self) -> dict[str, Any]:
        return {
            "voice": self.voice,
            "role": self.role,
            "note_index": self.note_index,
            "start": None if self.start is None else str(self.start),
            "where": self.where,
            "lyric": self.lyric,
            "word": self.word,
            "fragment": self.fragment,
            "phonemizer": self.phonemizer,
            "score_lyrics": list(self.score_lyrics),
        }


def locate(plan: SynthesisPlan, reported: Sequence[Mapping[str, Any]]) -> list[UnknownWord]:
    """Match the host's ``unknown_words`` (track, tick, lyric, word) to the plan's notes."""
    by_name = {voice.role.display_name: voice for voice in plan.voices}
    found: list[UnknownWord] = []
    joins = {name: assemble_words(plan, voice) for name, voice in by_name.items()}
    for item in reported:
        track = str(item.get("track", ""))
        voice = by_name.get(track)
        position = item.get("position")
        start = Fraction(int(position), TICKS_PER_QUARTER) if isinstance(position, int) else None
        note_index: int | None = None
        fragment = False
        written: tuple[str, ...] = ()
        if voice is not None and start is not None:
            sung = next((n for n in voice.notes if n.start == start), None)
            if sung is not None:
                note_index = sung.index
                written = score_lyrics_of(plan, voice.role, joins[track], sung.index)
                # only the syllable as the score writes it is a fragment; a word that BLT assembled
                # from all of its syllables (words.py) is a whole word
                fragment = is_word_fragment(sung) and str(item.get("word", "")) == sung.lyric.text
        found.append(
            UnknownWord(
                voice=track,
                role=voice.role.value if voice is not None else None,
                note_index=note_index,
                start=start,
                where=position_label(start, plan.meter)
                if start is not None
                else "position unknown",
                lyric=str(item.get("lyric", "")),
                word=str(item.get("word", "")),
                fragment=fragment,
                phonemizer=plan.engine_ref(voice.role).phonemizer if voice is not None else None,
                score_lyrics=written,
            )
        )
    order = {name: i for i, name in enumerate(by_name)}
    found.sort(
        key=lambda u: (u.start if u.start is not None else Fraction(0), order.get(u.voice, 99))
    )
    return found


def group(found: Sequence[UnknownWord]) -> list[tuple[str, str, list[str]]]:
    """``(word, where, voices)`` for each place a word is sung, voices in score order."""
    groups: dict[tuple[str, str], list[str]] = {}
    for item in found:
        groups.setdefault((item.word, item.where), []).append(item.voice)
    return [(word, where, voices) for (word, where), voices in groups.items()]


def describe(found: Sequence[UnknownWord], limit: int = 8) -> str:
    pieces = {(item.word, item.where) for item in found if item.fragment}
    parts = [
        f'"{word}" ({where}; {", ".join(voices)})'
        + (" [a syllable of a longer word]" if (word, where) in pieces else "")
        for word, where, voices in group(found)[:limit]
    ]
    more = len(group(found)) - limit
    return "; ".join(parts) + (f"; and {more} more" if more > 0 else "")


@dataclass(frozen=True, slots=True)
class InvalidHint:
    """A pronunciation a person gave that the engine refuses, placed in the score."""

    voice: str
    role: str | None
    note_index: int | None
    start: Fraction | None
    where: str
    lyric: str  # the word the pronunciation is for
    symbol: str | None  # the symbol the engine does not know; None when the note made no sound
    reason: str  # symbol_unknown, no_sound or engine_error

    def as_detail(self) -> dict[str, Any]:
        return {
            "voice": self.voice,
            "role": self.role,
            "note_index": self.note_index,
            "start": None if self.start is None else str(self.start),
            "where": self.where,
            "lyric": self.lyric,
            "symbol": self.symbol,
            "reason": self.reason,
        }


def locate_hints(plan: SynthesisPlan, reported: Sequence[Mapping[str, Any]]) -> list[InvalidHint]:
    """Match the host's ``invalid_hints`` (track, tick, lyric, symbol) to the plan's notes."""
    by_name = {voice.role.display_name: voice for voice in plan.voices}
    found: list[InvalidHint] = []
    for item in reported:
        track = str(item.get("track", ""))
        voice = by_name.get(track)
        position = item.get("position")
        start = Fraction(int(position), TICKS_PER_QUARTER) if isinstance(position, int) else None
        sung = (
            next((n for n in voice.notes if n.start == start), None)
            if voice is not None and start is not None
            else None
        )
        symbol = item.get("symbol")
        found.append(
            InvalidHint(
                voice=track,
                role=voice.role.value if voice is not None else None,
                note_index=sung.index if sung is not None else None,
                start=start,
                where=position_label(start, plan.meter)
                if start is not None
                else "position unknown",
                lyric=str(item.get("lyric", "")),
                symbol=None if symbol is None else str(symbol),
                reason=str(item.get("reason", "symbol_unknown")),
            )
        )
    order = {name: i for i, name in enumerate(by_name)}
    found.sort(
        key=lambda h: (h.start if h.start is not None else Fraction(0), order.get(h.voice, 99))
    )
    return found


def describe_hints(found: Sequence[InvalidHint], limit: int = 8) -> str:
    parts: list[str] = []
    for item in found[:limit]:
        if item.reason == "symbol_unknown":
            what = f"the symbol {item.symbol!r} is not one this pronunciation engine knows"
        elif item.reason == "engine_error":
            what = "the pronunciation engine failed on the symbols given"
        else:
            what = "the symbols given make no sound"
        parts.append(f'"{item.lyric}" ({item.where}; {item.voice}): {what}')
    more = len(found) - limit
    return "; ".join(parts) + (f"; and {more} more" if more > 0 else "")


def with_findings(error: PronunciationError, plan: SynthesisPlan) -> PronunciationError:
    """The host's refusal with each word placed in the score (voice, bar, beat)."""
    host = error.details.get("host_result") or {}
    hints = host.get("invalid_hints")
    if error.code == "PRONUNCIATION_INVALID" and isinstance(hints, list) and hints:
        placed = locate_hints(plan, hints)
        detail = dict(error.details)
        detail["invalid_hints"] = [item.as_detail() for item in placed]
        message = (
            f"{len(placed)} pronunciation(s) given for this score cannot be used, so nothing was "
            f"rendered: {describe_hints(placed)}"
        )
        return PronunciationError("PRONUNCIATION_INVALID", message, detail)
    reported = host.get("unknown_words")
    if not isinstance(reported, list) or not reported:
        return error
    found = locate(plan, reported)
    details = dict(error.details)
    details["unknown_words"] = [item.as_detail() for item in found]
    words = len({item.word for item in found})
    message = (
        f"the pronunciation dictionary has no entry for {words} word(s), so nothing was "
        f"rendered (BLT does not guess pronunciations): {describe(found)}"
    )
    return PronunciationError("PRONUNCIATION_UNKNOWN", message, details)
