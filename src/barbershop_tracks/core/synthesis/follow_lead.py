"""The barbershop convention: a part without lyrics of its own sings what the Lead sings.

Scores usually write the words once, under the Lead, and the other parts sing them too unless they
are written separately. This module applies that as an explicit, recorded rule to the notes the
score leaves *without any lyric* (``ABSENT`` for the plain "no lyric" reason); nothing else is
touched: a score lyric, a melisma continuation, a conflict, humming, an elision, a proposal or a
person's approval is never replaced.

For a note of Tenor, Baritone or Bass starting at ``t`` the Lead note sounding at ``t`` decides:

* the Lead must be singing a decided syllable there (its own score lyric, an approval, or the
  continuation of one); if the Lead rests or is undecided, the note stays a review item;
* if the note starts together with the Lead's syllable, it sings that syllable;
* if it starts while the Lead is still holding a syllable (the part moves under a held word), it
  sustains the vowel when the previous note of the same part ends exactly where this one starts,
  and sings the Lead's syllable again otherwise (a held vowel cannot cross a gap).
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


def follow_the_lead(voices: tuple[VoicePlan, ...]) -> tuple[VoicePlan, ...]:
    """The voices with the rule applied (the Lead itself is never changed)."""
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
            at = bisect_right(starts, note.start) - 1
            if at < 0 or lead.notes[at].end <= note.start:
                continue  # the Lead is not singing here
            found = _lead_syllable(lead, at)
            if found is None:
                continue
            origin, text = found
            previous = notes[i - 1] if i else None
            touching = (
                previous is not None
                and previous.end == note.start
                and previous.lyric.state is not LyricState.ABSENT
                and previous.lyric.state is not LyricState.INFERRED_PROPOSAL
            )
            together = lead.notes[at].start == note.start and lead.notes[at] is origin
            sustain = not together and touching
            provenance = replace(
                note.lyric.provenance,
                detail=(
                    f"follows the Lead's syllable {text!r} that starts at {origin.start}"
                    + (" (held)" if sustain else "")
                ),
                follows_start=origin.start,
            )
            lyric = NoteLyric(
                state=LyricState.LEAD_SUSTAIN if sustain else LyricState.LEAD_SYLLABLE,
                text=None if sustain else text,
                provenance=provenance,
            )
            notes[i] = replace(note, lyric=lyric)
        result.append(replace(voice, notes=tuple(notes)))
    return tuple(result)
