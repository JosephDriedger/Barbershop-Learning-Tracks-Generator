"""Whole words for the dictionary phonemizers: ``to-geth-er`` is sent as ``together`` + ``+`` + ``+``.

A MusicXML score writes a word syllable by syllable (``to`` / ``geth`` / ``er``, marked begin / middle / end).
Arpasing, English VCCV and X-SAMPA look up WORDS in the CMU dictionary and place one vowel on each note of
the word, so they need ``together`` on the first note and ``+`` (OpenUtau's extender) on the notes of the other
syllables. Sending the syllables as three words would look up ``geth`` (not a word) and pronounce ``to`` and
``er`` as words of their own. A voicebank that sings syllables directly (the default phonemizer, UTAU-style
banks) wants the syllables, so this applies only to the phonemizers named in ``DICTIONARY_PHONEMIZERS``.

A word is assembled only when it is certain to be the same word on every note: the syllables begin / middle /
end must follow each other, every note of the word must touch the next (``+`` is an extender only across no
gap), and a part that follows the Lead must sing consecutive syllables of the Lead's word. In every other case
(a part that holds one note under several syllables of the Lead's word, a rest inside a word, a word that
starts mid-way) nothing is assembled: each syllable stays as the score writes it and is looked up as it is. If
the dictionary does not have that fragment either, the render host stops and names it
(core/rendering/pronunciation.py); BLT does not guess how a partly sung word should sound.
"""

from dataclasses import dataclass, field
from fractions import Fraction

from barbershop_tracks.core.synthesis.plan import (
    LyricState,
    PlannedNote,
    SynthesisPlan,
    VoicePlan,
)
from barbershop_tracks.models import VoiceRole

# Real scores type their lyrics the way a word processor does. Three things are written differently for the
# engine, and only for the engine (the score's own lyric text, the review screens and the package's record keep
# what the score says):
#
# * a typographic apostrophe (U+2019: she's, ain't, in') is the plain apostrophe of the dictionary (CMUdict has
#   ``she's``): the same character in another typeface, not a guess;
# * punctuation around a word, the quotation marks of "goodbye", the "!" of "Bay!", the parentheses of
#   "(With ...)", has no sound and is not part of the word, so it is not looked up with it;
# * nothing else: a letter, an apostrophe, a digit and what is inside the word are never touched, and text that
#   is only punctuation is left as it is (and refused later, with the character named).
_APOSTROPHES = str.maketrans(dict.fromkeys("\u2018\u2019\u201b\u02bc\u02b9\u00b4\u2032\uff07", "'"))
_AROUND_THE_WORD = '"\u201c\u201d\u201e\u201f\u00ab\u00bb()!?,.;:\u2026\u2013\u2014'


def engine_text(text: str) -> str:
    """The lyric as the singing engine receives it: plain apostrophes, no punctuation around the word."""
    plain = text.translate(_APOSTROPHES)
    return plain.strip(_AROUND_THE_WORD) or plain


DICTIONARY_PHONEMIZERS = (
    "OpenUtau.Plugin.Builtin.ArpasingPhonemizer",
    "OpenUtau.Plugin.Builtin.EnglishVCCVPhonemizer",
    "OpenUtau.Plugin.Builtin.EnXSampaPhonemizer",
)

_TEXT_STATES = (LyricState.SCORE_LYRIC, LyricState.USER_APPROVED, LyricState.LEAD_SYLLABLE)
_CONTINUATIONS = (LyricState.SCORE_CONTINUATION, LyricState.LEAD_SUSTAIN)


@dataclass(frozen=True, slots=True)
class WordJoin:
    """What to write instead of the syllables of the words that span several notes."""

    whole: dict[int, str] = field(default_factory=dict)  # first syllable's note index -> the word
    follow: frozenset[int] = frozenset()  # later syllables' note indices: written as the extender


def _has_text(note: PlannedNote) -> bool:
    return note.lyric.state in _TEXT_STATES and note.lyric.text is not None


def _syllabic(note: PlannedNote) -> str:
    return note.lyric.provenance.syllabic or "single"


def is_word_fragment(note: PlannedNote) -> bool:
    """True for a syllable that is only a part of a longer word (begin / middle / end)."""
    return _has_text(note) and _syllabic(note) in ("begin", "middle", "end")


def _chain(
    notes: tuple[PlannedNote, ...], first: int, orders: dict[str, dict[Fraction, int]]
) -> list[int] | None:
    """The note indices of the complete word that begins at ``first``, or None if it is not complete."""
    start = notes[first]
    chain = [first]
    origins = [(start.lyric.provenance.follows_role, start.lyric.provenance.follows_start)]
    states = {start.lyric.state}
    current = first
    while True:
        nxt = current + 1
        if nxt >= len(notes) or notes[current].end != notes[nxt].start:
            return None  # the score ends, or a rest or gap separates two notes of the word
        following = notes[nxt]
        if following.lyric.state in _CONTINUATIONS:
            chain.append(nxt)
            current = nxt
            continue
        if not _has_text(following) or _syllabic(following) not in ("middle", "end"):
            return None  # the next note does not continue the word
        chain.append(nxt)
        origins.append(
            (following.lyric.provenance.follows_role, following.lyric.provenance.follows_start)
        )
        states.add(following.lyric.state)
        current = nxt
        if _syllabic(following) == "end":
            break
    if len(states) > 1:
        return None  # syllables from different sources
    if states == {LyricState.LEAD_SYLLABLE}:
        roles = {role or VoiceRole.LEAD.value for role, _ in origins}
        if len(roles) != 1:
            return None  # syllables followed from different parts
        order = orders.get(next(iter(roles)), {})
        ordinals = [order.get(o) if o is not None else None for _, o in origins]
        first_ordinal = ordinals[0]
        if first_ordinal is None or ordinals != list(
            range(first_ordinal, first_ordinal + len(ordinals))
        ):
            return None  # this part sings only some of the followed part's syllables of the word
    return chain


def assemble_words(plan: SynthesisPlan, voice: VoicePlan) -> WordJoin:
    """The complete words of ``voice``, whole on their first note; everything else is left as written."""
    # the order of each part's own syllables: what a part that follows it must sing consecutively
    orders = {
        v.role.value: {
            n.start: k
            for k, n in enumerate(
                n
                for n in v.notes
                if n.lyric.state in (LyricState.SCORE_LYRIC, LyricState.USER_APPROVED)
                and _has_text(n)
            )
        }
        for v in plan.voices
    }
    notes = voice.notes
    whole: dict[int, str] = {}
    follow: set[int] = set()
    i = 0
    while i < len(notes):
        if _has_text(notes[i]) and _syllabic(notes[i]) == "begin":
            chain = _chain(notes, i, orders)
            if chain is not None:
                whole[i] = engine_text(
                    "".join(notes[k].lyric.text or "" for k in chain if _has_text(notes[k]))
                )
                follow.update(k for k in chain[1:] if _has_text(notes[k]))
                i = chain[-1] + 1
                continue
        i += 1
    return WordJoin(whole=whole, follow=frozenset(follow))
