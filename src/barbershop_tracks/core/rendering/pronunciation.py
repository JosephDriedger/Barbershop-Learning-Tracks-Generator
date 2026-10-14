"""Words the pronunciation dictionary lacks: name them, per voice and bar, before rendering.

The render host phonemizes the project first. A dictionary phonemizer (Arpasing, English VCCV,
X-SAMPA) that cannot look a word up would otherwise turn it into a voicebank alias or into the
text "word not found", both of which sing as silence. The host stops instead (exit 11) and
reports each word with the track and the tick of the note. This module turns that report into
what the singer needs: which voice, which bar and beat, which word. BLT never invents a
pronunciation and never drops the syllable: it stops and says so.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from barbershop_tracks.core.rendering.errors import PronunciationError
from barbershop_tracks.core.synthesis import SynthesisPlan
from barbershop_tracks.core.synthesis.openutau.words import is_word_fragment
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
        }


def locate(plan: SynthesisPlan, reported: Sequence[Mapping[str, Any]]) -> list[UnknownWord]:
    """Match the host's ``unknown_words`` (track, tick, lyric, word) to the plan's notes."""
    by_name = {voice.role.display_name: voice for voice in plan.voices}
    found: list[UnknownWord] = []
    for item in reported:
        track = str(item.get("track", ""))
        voice = by_name.get(track)
        position = item.get("position")
        start = Fraction(int(position), TICKS_PER_QUARTER) if isinstance(position, int) else None
        note_index: int | None = None
        fragment = False
        if voice is not None and start is not None:
            sung = next((n for n in voice.notes if n.start == start), None)
            if sung is not None:
                note_index = sung.index
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


def with_findings(error: PronunciationError, plan: SynthesisPlan) -> PronunciationError:
    """The host's refusal with each word placed in the score (voice, bar, beat)."""
    host = error.details.get("host_result") or {}
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
