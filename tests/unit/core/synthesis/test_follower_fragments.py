"""What a voice that follows the Lead sings when it has fewer notes than the Lead's word has syllables.

M19 investigated the "first fragment" behaviour of followers. The findings, pinned here so that they are
facts and not memories:

* it comes from the INFERRED lyric, not from the part's own lyrics and not from the syllable assembly: the
  follow-the-Lead rule gives a note the Lead syllable that STARTS where the note starts, and the assembly
  (words.py) joins syllables into a word only when the voice has one note per consecutive syllable;
* a part with its own complete lyrics, and a part with one note per syllable, get the whole word;
* a part that holds one note under several syllables of the Lead's word keeps the first syllable as a
  fragment (a word of its own for the dictionary, ``to``), and a part that has a note starting under the
  middle of a word keeps that middle fragment (``geth``), which the dictionary lacks, so BLT stops and
  names it (``[a syllable of a longer word]``).

These are alignment limits of a voice that has fewer notes than the word has syllables, not defects of
the rule: which sounds of the word belong on the note is a musical decision the score does not make. The
person can decide it with a pronunciation for that note (the fragment is a word like any other for it).
"""

import tempfile
from pathlib import Path

import pytest

from barbershop_tracks.core.pipeline import prepare
from barbershop_tracks.core.readiness import RoleAssignments
from barbershop_tracks.core.synthesis import LyricState, SourceIdentity, VoiceEngineRef
from barbershop_tracks.core.synthesis.openutau.words import assemble_words
from barbershop_tracks.models import VoiceRole
from xml_builders import (
    attributes,
    lyric_xml,
    measure,
    note,
    parse_text,
    score,
    syl,
    tempo_direction,
    text,
)

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
NAMES = ["Tenor", "Lead", "Baritone", "Bass"]
ROLES = (VoiceRole.TENOR, VoiceRole.LEAD, VoiceRole.BARITONE, VoiceRole.BASS)
# durations are in divisions (2 per quarter note): the Lead sings to / geth / er, one quarter each
LEAD = "".join(
    note(step, 4, 2, lyrics=lyric_xml(syl(kind), text(word)))
    for kind, word, step in (("begin", "to", "E"), ("middle", "geth", "F"), ("end", "er", "G"))
)


def tenor(variant: str) -> str:
    notes = {
        "one held note": [("G", 6)],
        "two notes": [("G", 4), ("A", 2)],
        "one per syllable": [("G", 2), ("A", 2), ("B", 2)],
        "second note on geth": [("G", 2), ("A", 1), ("B", 3)],
    }
    if variant == "own lyrics":
        return "".join(
            note(step, 4, 2, lyrics=lyric_xml(syl(kind), text(word)))
            for kind, word, step in (
                ("begin", "to", "G"),
                ("middle", "geth", "A"),
                ("end", "er", "B"),
            )
        )
    return "".join(note(step, 4, length) for step, length in notes[variant])


def sent(variant: str) -> list[tuple[str, str]]:
    """(state, what the engine receives) for each note of the Tenor, who follows the Lead."""
    parts = []
    for name in NAMES:
        body = tenor(variant) if name == "Tenor" else (LEAD if name == "Lead" else note("C", 3, 6))
        if name in ("Baritone", "Bass"):
            body = note("C", 3, 6)
        marker = tempo_direction("88") if name == "Tenor" else ""
        parts.append(measure(1, marker + body, attrs=attributes()))
    with tempfile.TemporaryDirectory() as folder:
        parsed = parse_text(Path(folder), score(*parts, names=NAMES))
    assignments = RoleAssignments(
        entries=tuple((role, f"P{i}/s1/v1") for i, role in enumerate(ROLES, start=1))
    )
    refs = {
        role: VoiceEngineRef(singer="x", phonemizer=ARPASING, renderer="WORLDLINE-R")
        for role in ROLES
    }
    prepared = prepare(
        parsed,
        assignments,
        identity=SourceIdentity(display_name="e.musicxml", sha256="0" * 64),
        engine_refs=refs,
        follow_lead=True,
    )
    assert prepared.plan is not None
    voice = prepared.plan.voice(VoiceRole.TENOR)
    joined = assemble_words(prepared.plan, voice)
    out = []
    for n in voice.notes:
        if n.lyric.state is LyricState.LEAD_SUSTAIN or n.index in joined.follow:
            out.append((n.lyric.state.value, "+"))
        else:
            out.append((n.lyric.state.value, joined.whole.get(n.index, n.lyric.text or "")))
    return out


def test_a_voice_with_one_note_per_syllable_gets_the_whole_word() -> None:
    assert sent("one per syllable") == [
        ("lead_syllable", "together"),
        ("lead_syllable", "+"),
        ("lead_syllable", "+"),
    ]


def test_a_voice_with_its_own_complete_lyrics_gets_the_whole_word() -> None:
    assert sent("own lyrics") == [
        ("score_lyric", "together"),
        ("score_lyric", "+"),
        ("score_lyric", "+"),
    ]


def test_one_held_note_under_the_whole_word_keeps_the_first_syllable_only() -> None:
    assert sent("one held note") == [("lead_syllable", "to")]


def test_two_notes_for_three_syllables_keep_the_syllables_that_start_under_each_note() -> None:
    assert sent("two notes") == [("lead_syllable", "to"), ("lead_syllable", "er")]


@pytest.mark.parametrize("variant", ["one held note", "two notes"])
def test_the_fragments_that_remain_are_ordinary_syllables_of_the_score(variant: str) -> None:
    # nothing is invented: each is the text of a Lead syllable that starts where the note starts
    for _state, word in sent(variant):
        assert word in {"to", "geth", "er"}


def test_a_second_note_on_a_middle_syllable_sings_it_as_a_fragment_and_the_next_holds() -> None:
    assert sent("second note on geth") == [
        ("lead_syllable", "to"),
        ("lead_syllable", "geth"),  # starts with the Lead's "geth": a fragment, named if unknown
        ("lead_sustain", "+"),
    ]
