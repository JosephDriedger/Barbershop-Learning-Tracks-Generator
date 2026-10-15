"""Pronunciations in the generation pipeline: scoped, checked, recorded, and safe when refused."""

import hashlib
import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from test_coordinator import Rig, error_of

from barbershop_tracks.core.pipeline import (
    EngineChoice,
    GenerateRequest,
    PipelineError,
    check_pronunciations,
)
from barbershop_tracks.core.rendering import CancelToken, PronunciationError
from barbershop_tracks.core.synthesis.openutau import PronunciationOverride, parse_symbols
from barbershop_tracks.models import VoiceRole

ARPASING = "OpenUtau.Plugin.Builtin.ArpasingPhonemizer"
XSAMPA = "OpenUtau.Plugin.Builtin.EnXSampaPhonemizer"


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    made = Rig(tmp_path)
    made.write_score(word="o'er")  # every note of every part sings the same unusual word
    made.config = replace(made.config, phonemizer=ARPASING)
    return made


def sha(rig: Rig) -> str:
    return hashlib.sha256(rig.score.read_bytes()).hexdigest()


def decision(
    rig: Rig,
    *,
    role: VoiceRole = VoiceRole.LEAD,
    start: int = 0,
    word: str = "o'er",
    phonemizer: str = ARPASING,
    symbols: str = "ow er",
    digest: str | None = None,
) -> PronunciationOverride:
    return PronunciationOverride(
        role=role,
        start=Fraction(start),
        word=word,
        phonemizer=phonemizer,
        symbols=parse_symbols(symbols),
        approved_by="A. Singer",
        source_sha256=digest or sha(rig),
    )


def request(rig: Rig, *decided: PronunciationOverride, **more: Any) -> GenerateRequest:
    return replace(
        rig.request(engine=EngineChoice("my-singer", ARPASING, "WORLDLINE-R")),
        pronunciations=tuple(decided),
        **more,
    )


def test_a_decision_reaches_the_renderer_resolved_for_its_voice_and_note(rig: Rig) -> None:
    rig.run(request(rig, decision(rig), decision(rig, role=VoiceRole.TENOR, start=2)))
    (resolved,) = rig.renderer.overrides
    assert {(role, index) for role, index in resolved.by_note} == {
        (VoiceRole.LEAD, 0),
        (VoiceRole.TENOR, 2),
    }
    # the same word at every other note of every voice has no decision of its own
    assert len(resolved.by_note) == 2


def test_the_package_records_each_decision_next_to_the_score_text(rig: Rig) -> None:
    result = rig.run(request(rig, decision(rig), decision(rig, role=VoiceRole.BASS, start=1)))
    manifest = json.loads((result.destination / "manifest.json").read_text(encoding="utf-8"))
    records = manifest["pronunciation"]["overrides"]
    assert [(r["voice"], r["start"]) for r in records] == [("lead", "0"), ("bass", "1")]
    first = records[0]
    assert first["score_lyrics"] == ["o'er"]  # the score's own text is kept
    assert first["word"] == "o'er"
    assert first["symbols"] == "ow er"
    assert first["alphabet"] == "arpabet"
    assert first["approved_by"] == "A. Singer"
    assert first["source_sha256"] == sha(rig)
    assert first["scope"].startswith("this voice, this note")
    assert manifest["source"]["sha256"] == sha(rig)
    assert [r["voice"] for r in result.pronunciations] == ["lead", "bass"]


def test_a_package_without_decisions_says_so(rig: Rig) -> None:
    result = rig.run(request(rig))
    manifest = json.loads((result.destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["pronunciation"]["overrides"] == []
    assert "no pronunciation model" in manifest["pronunciation"]["dictionary"]


def test_the_score_file_is_never_changed(rig: Rig) -> None:
    before = rig.score.read_bytes()
    rig.run(request(rig, decision(rig)))
    assert rig.score.read_bytes() == before


def test_a_decision_for_another_version_of_the_score_is_refused_before_anything_renders(
    rig: Rig,
) -> None:
    problem = error_of(rig, request(rig, decision(rig, digest="cd" * 32)))
    assert problem.code == "OVERRIDE_WRONG_SCORE"
    assert rig.renderer.calls == []
    assert rig.staging() == []
    assert not (rig.root / "out").exists()


def test_a_decision_that_the_score_no_longer_matches_is_refused(rig: Rig) -> None:
    problem = error_of(rig, request(rig, decision(rig, word="'neath")))
    assert problem.code == "OVERRIDE_WORD_MISMATCH"
    assert rig.renderer.calls == []


def test_a_decision_written_for_another_engine_is_refused(rig: Rig) -> None:
    problem = error_of(rig, request(rig, decision(rig, phonemizer=XSAMPA, symbols="oU 3")))
    assert problem.code == "OVERRIDE_PHONEMIZER_MISMATCH"
    assert rig.renderer.calls == []


def test_a_decision_for_a_note_that_is_not_there_is_refused(rig: Rig) -> None:
    problem = error_of(rig, request(rig, decision(rig, start=99)))
    assert problem.code == "OVERRIDE_NO_NOTE"


def test_two_decisions_for_one_note_are_refused(rig: Rig) -> None:
    problem = error_of(rig, request(rig, decision(rig), decision(rig, symbols="ao r")))
    assert problem.code == "OVERRIDE_DUPLICATE"


def test_a_refused_pronunciation_leaves_an_earlier_package_exactly_as_it_was(rig: Rig) -> None:
    first = rig.run(request(rig))
    manifest = (first.destination / "manifest.json").read_bytes()
    files = sorted(p.name for p in first.destination.iterdir())
    rig.renderer.error = PronunciationError(
        "PRONUNCIATION_INVALID",
        "1 pronunciation(s) given for this score cannot be used",
        {"invalid_hints": []},
    )
    problem = error_of(rig, request(rig, decision(rig, symbols="zzz"), replace=True))
    assert problem.code == "PRONUNCIATION_INVALID"
    assert (first.destination / "manifest.json").read_bytes() == manifest
    assert sorted(p.name for p in first.destination.iterdir()) == files
    assert rig.staging() == []


def test_a_refused_pronunciation_publishes_nothing_where_there_was_nothing(rig: Rig) -> None:
    rig.renderer.error = PronunciationError("PRONUNCIATION_INVALID", "cannot be used", {})
    problem = error_of(rig, request(rig, decision(rig, symbols="zzz")))
    assert problem.code == "PRONUNCIATION_INVALID"
    assert not (rig.root / "out").exists() or list((rig.root / "out").iterdir()) == []
    assert rig.staging() == []


def test_a_retry_after_a_refusal_works_and_replaces_nothing_it_should_not(rig: Rig) -> None:
    rig.renderer.error = PronunciationError("PRONUNCIATION_INVALID", "cannot be used", {})
    error_of(rig, request(rig, decision(rig, symbols="zzz")))
    rig.renderer.error = None
    result = rig.run(request(rig, decision(rig, symbols="ow er")))
    assert (result.destination / "01_Full_Quartet.wav").is_file()
    assert rig.staging() == []


def test_cancelling_leaves_no_package_and_no_working_files(rig: Rig) -> None:
    token = CancelToken()
    token.cancel()
    with pytest.raises(PipelineError) as info:
        rig.run(request(rig, decision(rig)), cancel=token)
    assert info.value.code == "CANCELLED"
    assert rig.staging() == []
    assert not (rig.root / "out").exists()


# --- the check, which stops before any render ---------------------------------------------------


def test_the_check_hands_the_resolved_decisions_to_the_engine_and_renders_nothing(rig: Rig) -> None:
    result = check_pronunciations(request(rig, decision(rig)), rig.config, services=rig.services())
    assert result["status"] == "ok"
    (resolved,) = rig.renderer.checks
    assert [(role, index) for role, index in resolved.by_note] == [(VoiceRole.LEAD, 0)]
    assert rig.renderer.calls == []  # no render
    assert not (rig.root / "out").exists()


def test_the_check_refuses_a_stale_decision_like_generating_does(rig: Rig) -> None:
    with pytest.raises(PipelineError) as info:
        check_pronunciations(
            request(rig, decision(rig, digest="cd" * 32)), rig.config, services=rig.services()
        )
    assert info.value.code == "OVERRIDE_WRONG_SCORE"
    assert rig.renderer.checks == []


def test_the_check_reports_what_the_engine_refuses(rig: Rig) -> None:
    rig.renderer.error = PronunciationError("PRONUNCIATION_INVALID", "no", {"invalid_hints": []})
    with pytest.raises(PipelineError) as info:
        check_pronunciations(request(rig), rig.config, services=rig.services())
    assert info.value.code == "PRONUNCIATION_INVALID"
    assert rig.staging() == []
