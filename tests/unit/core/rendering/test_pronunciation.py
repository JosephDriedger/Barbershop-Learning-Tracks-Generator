"""A word the dictionary lacks stops the run and is named by voice and bar; nothing is guessed."""

import sys
from fractions import Fraction
from pathlib import Path

import pytest

from barbershop_tracks.core.pipeline import ErrorCategory
from barbershop_tracks.core.pipeline.coordinator import translate
from barbershop_tracks.core.rendering import (
    OpenUtauRenderBackend,
    PronunciationError,
    RenderSettings,
)
from barbershop_tracks.core.rendering import pronunciation as pron
from barbershop_tracks.core.runtime import RuntimeLayout
from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.explain import explain
from synth_builders import full_lyrics, plan_of, refs

FAKE = Path(__file__).resolve().parents[3] / "fake_render_host.py"


def backend(tmp_path: Path) -> OpenUtauRenderBackend:
    layout = RuntimeLayout.under(tmp_path / "bin", tmp_path / "data")
    (tmp_path / "singers").mkdir()
    return OpenUtauRenderBackend(
        RenderSettings(
            layout=layout,
            singers_dir=tmp_path / "singers",
            host_command=(sys.executable, str(FAKE)),
            extra_env={"FAKE_HOST_MODE": "pronunciation_unknown"},
            timeout_seconds=30,
            poll_seconds=0.01,
        )
    )


def test_the_hosts_refusal_names_each_word_with_its_voices_and_its_bar(tmp_path: Path) -> None:
    plan = plan_of(voices=full_lyrics(("la", "ev'ry", "la", "la", "o'er")), engine_refs=refs())
    with pytest.raises(PronunciationError) as info:
        backend(tmp_path).render(plan, tmp_path / "out")
    error = info.value
    assert error.code == "PRONUNCIATION_UNKNOWN"
    assert "nothing was rendered" in error.message
    assert "BLT does not guess" in error.message
    assert "'ev'ry' (bar 1, beat 2; Tenor, Lead)" in error.message
    assert "'o'er'" in error.message
    found = error.details["unknown_words"]
    assert [(u["voice"], u["word"], u["where"]) for u in found] == [
        ("Tenor", "ev'ry", "bar 1, beat 2"),
        ("Lead", "ev'ry", "bar 1, beat 2"),
        ("Lead", "o'er", "bar 2, beat 1"),
    ]
    assert found[0]["note_index"] == 1
    assert found[0]["start"] == "1"
    assert not (tmp_path / "out").exists()  # nothing was published, nothing half-written


def test_the_error_reaches_the_user_as_a_source_problem_with_a_plain_explanation(
    tmp_path: Path,
) -> None:
    plan = plan_of(voices=full_lyrics(("la", "ev'ry", "la", "la", "o'er")), engine_refs=refs())
    with pytest.raises(PronunciationError) as info:
        backend(tmp_path).render(plan, tmp_path / "out")
    piped = translate(info.value)
    assert piped.category is ErrorCategory.SOURCE
    assert piped.code == "PRONUNCIATION_UNKNOWN"
    explanation = explain(piped)
    assert explanation.kind == "pronunciation_unknown"
    assert "2 words" in explanation.summary
    assert "'ev'ry': bar 1, beat 2 (Tenor, Lead)" in explanation.summary
    assert "nothing was generated" in explanation.summary
    assert any("every" in step and "over" in step for step in explanation.steps)
    assert any("never changes your score" in step for step in explanation.steps)
    assert "Lead" in explanation.technical


def test_a_refusal_without_a_list_is_passed_on_unchanged() -> None:
    bare = PronunciationError("PRONUNCIATION_UNKNOWN", "no list", {"host_result": {"status": "x"}})
    assert (
        pron.with_findings(bare, plan_of(voices=full_lyrics(("la",) * 4), engine_refs=refs()))
        is bare
    )


def test_an_unknown_track_or_tick_is_still_reported_and_never_dropped() -> None:
    plan = plan_of(voices=full_lyrics(("la",) * 4), engine_refs=refs())
    found = pron.locate(
        plan,
        [
            {"track": "Mystery", "position": 480, "lyric": "x", "word": "x"},
            {"track": "Lead", "position": 481, "lyric": "y", "word": "y"},
        ],
    )
    assert [(u.voice, u.word) for u in found] == [("Mystery", "x"), ("Lead", "y")]
    lead = next(u for u in found if u.voice == "Lead")
    assert lead.role == VoiceRole.LEAD.value
    assert lead.note_index is None  # a tick that is not a note start: kept, not matched
    mystery = next(u for u in found if u.voice == "Mystery")
    assert mystery.role is None


def test_many_places_are_summarised_with_a_count() -> None:
    plan = plan_of(voices=full_lyrics(("la",) * 4), engine_refs=refs())
    reported = [
        {"track": "Lead", "position": 480 * n, "lyric": f"w{n}", "word": f"w{n}"} for n in range(12)
    ]
    text = pron.describe(pron.locate(plan, reported), limit=3)
    assert text.count("'w") == 3
    assert text.endswith("and 9 more")
    assert pron.group(pron.locate(plan, reported))[0][0] == "w0"
    assert Fraction(1) == pron.locate(plan, reported)[1].start


def test_a_syllable_of_a_longer_word_is_marked_so_the_singer_knows_why() -> None:
    from barbershop_tracks.core.pipeline import PipelineError
    from barbershop_tracks.models import Lyric, Syllabic
    from readiness_builders import PITCHES, note

    def syl(start: int, text: str, kind: Syllabic) -> object:
        return note(start, 1, PITCHES[VoiceRole.LEAD], lyrics=(Lyric(text=text, syllabic=kind),))

    voices = full_lyrics(("la",) * 4)
    voices["lead"] = [
        syl(0, "to", Syllabic.BEGIN),  # type: ignore[list-item]
        syl(1, "geth", Syllabic.MIDDLE),  # type: ignore[list-item]
        syl(2, "er", Syllabic.END),  # type: ignore[list-item]
        syl(3, "now", Syllabic.SINGLE),  # type: ignore[list-item]
    ]
    plan = plan_of(voices=voices, engine_refs=refs())
    found = pron.locate(plan, [{"track": "Lead", "position": 480, "lyric": "geth", "word": "geth"}])
    assert found[0].fragment is True
    assert "[a syllable of a longer word]" in pron.describe(found)
    error = PronunciationError(
        "PRONUNCIATION_UNKNOWN",
        "x",
        {
            "host_result": {
                "unknown_words": [
                    {"track": "Lead", "position": 480, "lyric": "geth", "word": "geth"}
                ]
            }
        },
    )
    piped = translate(pron.with_findings(error, plan))
    assert isinstance(piped, PipelineError)
    explanation = explain(piped)
    assert "[a syllable of a longer word]" in explanation.summary
    assert any("own lyric on that note" in step for step in explanation.steps)
    whole = pron.locate(plan, [{"track": "Lead", "position": 1440, "lyric": "now", "word": "now"}])
    assert whole[0].fragment is False
