from typing import Any

import pytest

from barbershop_tracks.core.pipeline import ErrorCategory, PipelineError
from barbershop_tracks.ui.explain import explain

C = ErrorCategory
INTERNAL = ("USTX", "OpenUtau", "renderer", "worldline", "phonemizer")


def error(category: ErrorCategory, code: str, message: str = "m", **details: Any) -> PipelineError:
    return PipelineError(category, code, message, details)


def findings(code: str) -> dict[str, Any]:
    return {"findings": [{"code": code, "message": "x"}]}


CASES = [
    (error(C.SOURCE, "SCORE_LOAD_FAILED", "bad xml"), "invalid_score"),
    (error(C.SOURCE, "SOURCE_NOT_READY", **findings("TEMPO_MISSING")), "missing_tempo"),
    (error(C.SOURCE, "SOURCE_NOT_READY", **findings("TIME_SIGNATURE_MISSING")), "missing_meter"),
    (error(C.SOURCE, "SOURCE_NOT_READY", **findings("ROLE_UNASSIGNED")), "incomplete_mapping"),
    (error(C.SOURCE, "SOURCE_NOT_READY", **findings("OTHER")), "invalid_score"),
    (error(C.REVIEW, "LYRICS_NEED_REVIEW"), "lyrics"),
    (error(C.CONFIGURATION, "SINGER_NOT_CHOSEN"), "missing_singer"),
    (error(C.CONFIGURATION, "SINGER_NOT_FOUND"), "missing_singer"),
    (error(C.CONFIGURATION, "SINGERS_DIR_MISSING"), "missing_singer"),
    (error(C.CONFIGURATION, "HOST_UNRESOLVED", "singer 'x' is not installed"), "missing_singer"),
    (error(C.CONFIGURATION, "HOST_UNRESOLVED", "'p' did not resolve"), "engine_setting"),
    (error(C.CONFIGURATION, "FFMPEG_NOT_CONFIGURED"), "ffmpeg"),
    (error(C.CONFIGURATION, "MIX_FFMPEG_UNUSABLE"), "ffmpeg"),
    (error(C.CONFIGURATION, "OUTPUT_EXISTS"), "output_exists"),
    (error(C.CONFIGURATION, "OUTPUT_FOREIGN"), "output_foreign"),
    (error(C.CONFIGURATION, "HOST_NOT_FOUND"), "component_missing"),
    (error(C.CONFIGURATION, "WHATEVER"), "configuration"),
    (error(C.SYNTHESIS, "HOST_FAILED"), "synthesis"),
    (error(C.AUDIO, "STEM_SILENT"), "audio_validation"),
    (error(C.AUDIO, "MIX_MP3_FAILED"), "ffmpeg_failed"),
    (error(C.AUDIO, "MIX_CLIPPING"), "audio_failed"),
    (error(C.TIMEOUT, "RENDER_TIMEOUT"), "timeout"),
    (error(C.CANCELLED, "CANCELLED"), "cancelled"),
]


@pytest.mark.parametrize(("failure", "kind"), CASES, ids=[f"{c[0].code}-{c[1]}" for c in CASES])
def test_each_failure_has_a_plain_explanation(failure: PipelineError, kind: str) -> None:
    explanation = explain(failure)
    assert explanation.kind == kind
    assert explanation.title
    assert explanation.summary
    assert failure.code in explanation.technical
    visible = " ".join([explanation.title, explanation.summary, *explanation.steps])
    assert not [word for word in INTERNAL if word.lower() in visible.lower()]


def test_cancellation_and_review_are_flagged() -> None:
    assert explain(error(C.CANCELLED, "CANCELLED")).cancelled
    assert explain(error(C.REVIEW, "LYRICS_NEED_REVIEW")).review
    assert not explain(error(C.AUDIO, "STEM_SILENT")).cancelled


def test_technical_details_list_the_findings() -> None:
    failure = error(
        C.SOURCE,
        "SOURCE_NOT_READY",
        findings=[
            {
                "code": "TEMPO_MISSING",
                "message": "no tempo",
                "voice": "tenor",
                "line": "P1",
                "where": "bar 1",
            }
        ],
    )
    assert "TEMPO_MISSING: no tempo [tenor P1 bar 1]" in explain(failure).technical


def test_every_error_category_is_covered() -> None:
    covered = {explain(error(c, "X")).kind for c in ErrorCategory}
    assert len(covered) >= 6


def test_a_missing_microsoft_runtime_tells_the_user_what_to_install() -> None:
    from barbershop_tracks.core.pipeline import ErrorCategory, PipelineError
    from barbershop_tracks.ui.explain import explain

    error = PipelineError(ErrorCategory.CONFIGURATION, "VC_RUNTIME_MISSING", "not installed")
    explanation = explain(error)
    assert explanation.kind == "vc_runtime"
    assert any("Redistributable" in step for step in explanation.steps)
    assert any("Without internet" in step for step in explanation.steps)
