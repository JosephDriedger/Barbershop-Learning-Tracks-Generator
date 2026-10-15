"""The barbershop convention: a part without lyrics of its own sings the words written for another part.

Scores usually write the words once and the other parts sing them too unless they are written separately.
This module applies that as explicit, recorded rules to the notes the score leaves *without any lyric*
(``ABSENT`` for the plain "no lyric" reason); nothing else is touched: a score lyric, a melisma continuation, a
conflict, humming, an elision, a proposal or a person's approval is never replaced.

Two rules, in this order, for a note of Tenor, Baritone or Bass starting at ``t``:

1. **The same note, written once.** Another part starts a note at the same moment with a lyric of its own: that
   is the lyric the score means for both. A held "Oo" written only under the Baritone is sung by the Tenor and the
   Bass that hold the same note while the Lead sings other, shorter words. The note that is *as long as this one*
   is the match; only when no part has one as long, a note that starts at the same moment is (parts may hold a
   chord for different times). If several parts have that note and they do not agree (different words), nothing is decided:
   the note stays a review item and the Lead's words are NOT used instead (the score disagrees with itself).
   (When the Lead is among the matches, rule 2 applies: the Lead's words are the convention.)
2. **The Lead.** Otherwise the Lead note sounding at ``t`` decides:

   * the Lead must be singing a decided syllable there (its own score lyric, an approval, or the continuation
     of one); if the Lead rests or is undecided, the note stays a review item;
   * if the note starts together with the Lead's syllable, it sings that syllable;
   * if it starts while the Lead is still holding a syllable (the part moves under a held word), it
     sustains the vowel when the previous note of the same part ends exactly where this one starts,
     and sings the Lead's syllable again otherwise (a held vowel cannot cross a gap).

The Lead itself is never changed. Each decision records whose words are followed (``follows_role``) and where.
"""

from bisect import bisect_right
from dataclasses import replace

from barbershop_tracks.core.synthesis.plan import (
    LyricState,
    NoteLyric,
    PlannedNote,
    ReviewReason,
    VoicePlan,
)
from barbershop_tracks.models import VoiceRole

_SYLLABLE_STATES = (LyricState.SCORE_LYRIC, LyricState.USER_APPROVED)
_EXPLICIT = (LyricState.SCORE_LYRIC, LyricState.USER_APPROVED, LyricState.SCORE_CONTINUATION)


def _lead_syllable(lead: VoicePlan, index: int) -> tuple[PlannedNote, str] | None:
    """The note that opened the syllable sounding in note ``index`` of the Lead, and its text."""
    while index >= 0:
        note = lead.notes[index]
        state = note.lyric.state
        if state in _SYLLABLE_STATES and note.lyric.text is not None:
            return note, note.lyric.text
        if state is not LyricState.SCORE_CONTINUATION:
            return None  # undecided, unsupported or already a followed lyric: nothing to copy
        index -= 1
    return None


def _origin_of(voice: VoicePlan, note: PlannedNote) -> tuple[PlannedNote, str] | None:
    """The syllable a note of ``voice`` sings (its own, or the one its melisma continues)."""
    if note.lyric.state in _SYLLABLE_STATES and note.lyric.text is not None:
        return note, note.lyric.text
    start = note.lyric.provenance.melisma_origin_start
    if note.lyric.state is LyricState.SCORE_CONTINUATION and start is not None:
        origin = next((n for n in voice.notes if n.start == start), None)
        if origin is not None and origin.lyric.state in _SYLLABLE_STATES and origin.lyric.text:
            return origin, origin.lyric.text
    return None


def _same_note_elsewhere(
    voices: tuple[VoicePlan, ...], me: VoicePlan, note: PlannedNote
) -> list[tuple[VoicePlan, PlannedNote]] | None:
    """The other parts' notes that match this one and carry a lyric of the score; None if none.

    The matches are the notes that start together with it and are as long; when there are none, those that
    only start together with it."""
    found: list[tuple[VoicePlan, PlannedNote]] = []
    for other in voices:
        if other.role is me.role:
            continue
        twin = next((n for n in other.notes if n.start == note.start), None)
        if twin is not None and twin.lyric.state in _EXPLICIT:
            found.append((other, twin))
    as_long = [(o, n) for o, n in found if n.duration == note.duration]
    return as_long or found or None


def _meaning(voice: VoicePlan, twin: PlannedNote) -> tuple[str, str] | None:
    """What a twin note means: ("text", the syllable) or ("hold", the syllable it continues)."""
    origin = _origin_of(voice, twin)
    if origin is None:
        return None
    kind = "text" if twin.lyric.state in _SYLLABLE_STATES else "hold"
    return kind, origin[1]


def follow_the_lead(voices: tuple[VoicePlan, ...]) -> tuple[VoicePlan, ...]:
    """The voices with the rules applied (the Lead itself is never changed)."""
    lead = next((v for v in voices if v.role is VoiceRole.LEAD), None)
    if lead is None:
        return voices
    starts = [n.start for n in lead.notes]
    result: list[VoicePlan] = []
    for voice in voices:
        if voice.role is VoiceRole.LEAD:
            result.append(voice)
            continue
        notes = list(voice.notes)
        for i, note in enumerate(notes):
            if note.lyric.review_reason is not ReviewReason.LYRIC_ABSENT:
                continue
            previous = notes[i - 1] if i else None
            touching = (
                previous is not None
                and previous.end == note.start
                and previous.lyric.state is not LyricState.ABSENT
                and previous.lyric.state is not LyricState.INFERRED_PROPOSAL
            )
            # rule 1: the same note, written once under another part
            twins = _same_note_elsewhere(voices, voice, note)
            if twins is not None and not any(o.role is VoiceRole.LEAD for o, _ in twins):
                said = {_meaning(other, twin) for other, twin in twins}
                if None in said or len(said) != 1:
                    continue  # the score disagrees with itself, or says nothing usable: a person decides
                meaning = next(iter(said))
                assert meaning is not None
                kind, text = meaning
                source_voice, twin = twins[0]
                origin = _origin_of(source_voice, twin)
                assert origin is not None
                holds = kind == "hold" and touching
                notes[i] = replace(
                    note,
                    lyric=NoteLyric(
                        state=LyricState.LEAD_SUSTAIN if holds else LyricState.LEAD_SYLLABLE,
                        text=None if holds else text,
                        provenance=replace(
                            note.lyric.provenance,
                            syllabic=origin[0].lyric.provenance.syllabic,
                            detail=(
                                f"sings what the {source_voice.role.display_name} sings on the same "
                                f"note (the score writes it once): {text!r}"
                                + (" (held)" if holds else "")
                            ),
                            follows_start=origin[0].start,
                            follows_role=source_voice.role.value,
                        ),
                    ),
                )
                continue
            # rule 2: the Lead
            at = bisect_right(starts, note.start) - 1
            if at < 0 or lead.notes[at].end <= note.start:
                continue  # the Lead is not singing here
            found = _lead_syllable(lead, at)
            if found is None:
                continue
            lead_origin, lead_text = found
            together = lead.notes[at].start == note.start and lead.notes[at] is lead_origin
            sustain = not together and touching
            provenance = replace(
                note.lyric.provenance,
                syllabic=lead_origin.lyric.provenance.syllabic,  # keeps its place in the word
                detail=(
                    f"follows the Lead's syllable {lead_text!r} that starts at {lead_origin.start}"
                    + (" (held)" if sustain else "")
                ),
                follows_start=lead_origin.start,
                follows_role=VoiceRole.LEAD.value,
            )
            notes[i] = replace(
                note,
                lyric=NoteLyric(
                    state=LyricState.LEAD_SUSTAIN if sustain else LyricState.LEAD_SYLLABLE,
                    text=None if sustain else lead_text,
                    provenance=provenance,
                ),
            )
        result.append(replace(voice, notes=tuple(notes)))
    return tuple(result)


__all__ = ["follow_the_lead"]
