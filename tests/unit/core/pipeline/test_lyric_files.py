import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from barbershop_tracks.core.pipeline import (
    APPROVALS_SCHEMA,
    REVIEW_SCHEMA,
    ErrorCategory,
    PipelineError,
    read_approvals,
    render_review_text,
    review_report,
)
from barbershop_tracks.models import VoiceRole
from synth_builders import full_lyrics, plan_of, sung

SHA = "ab" * 32


def write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def approvals_file(tmp_path: Path, entries: list[dict[str, Any]], sha: str = SHA) -> Path:
    return write(
        tmp_path / "a.json",
        {"schema": APPROVALS_SCHEMA, "source_sha256": sha, "approvals": entries},
    )


def code_of(path: Path) -> str:
    with pytest.raises(PipelineError) as info:
        read_approvals(path, source_sha256=SHA)
    assert info.value.category is ErrorCategory.CONFIGURATION
    return info.value.code


def test_a_ready_plan_has_an_empty_report() -> None:
    report = review_report(plan_of())
    assert report["schema"] == REVIEW_SCHEMA
    assert report["ready"] is True
    assert report["items"] == []
    assert report["approvals_template"]["approvals"] == []


def test_the_report_names_voice_note_time_and_reason() -> None:
    plan = plan_of(
        voices={**full_lyrics(), "bass": sung(VoiceRole.BASS, ["one", None, "three", None])}
    )
    report = review_report(plan)
    assert report["ready"] is False
    assert [(i["voice"], i["note_index"], i["start"]) for i in report["items"]] == [
        ("bass", 1, "1"),
        ("bass", 3, "3"),
    ]
    first = report["items"][0]
    assert first["reason"] == "lyric_absent"
    assert first["duration"] == "1"
    assert first["proposal"] is None
    assert isinstance(first["midi_pitch"], int)
    assert report["source"]["sha256"] == plan.source.sha256
    template = report["approvals_template"]
    assert template["source_sha256"] == plan.source.sha256
    assert template["approvals"][0] == {
        "voice": "bass",
        "start": "1",
        "text": None,
        "approved_by": None,
    }
    json.dumps(report)


def test_the_text_summary_counts_by_voice_and_truncates() -> None:
    plan = plan_of(voices={**full_lyrics(), "bass": sung(VoiceRole.BASS, [None] * 4)})
    text = render_review_text(review_report(plan), limit=2)
    assert "4 note(s)" in text
    assert "bass: 4" in text
    assert "and 2 more" in text


def test_a_filled_template_becomes_approvals(tmp_path: Path) -> None:
    path = approvals_file(
        tmp_path,
        [
            {"voice": "bass", "start": "1", "text": "la", "approved_by": "Joe"},
            {"voice": "tenor", "start": "3/2", "text": "ba", "approved_by": "Joe"},
        ],
    )
    approvals = read_approvals(path, source_sha256=SHA)
    assert [(a.role, a.start, a.text, a.approved_by) for a in approvals] == [
        (VoiceRole.BASS, Fraction(1), "la", "Joe"),
        (VoiceRole.TENOR, Fraction(3, 2), "ba", "Joe"),
    ]


def test_undecided_template_lines_stay_undecided(tmp_path: Path) -> None:
    path = approvals_file(
        tmp_path,
        [
            {"voice": "bass", "start": "1", "text": None, "approved_by": None},
            {"voice": "bass", "start": "2", "text": "la", "approved_by": "Joe"},
        ],
    )
    assert [a.start for a in read_approvals(path, source_sha256=SHA)] == [Fraction(2)]


def test_approvals_for_another_version_of_the_score_are_rejected(tmp_path: Path) -> None:
    assert code_of(approvals_file(tmp_path, [], sha="cd" * 32)) == "APPROVALS_WRONG_SCORE"


@pytest.mark.parametrize(
    ("entry", "code"),
    [
        ({"voice": "soprano", "start": "1", "text": "a", "approved_by": "x"}, "APPROVALS_INVALID"),
        ({"voice": "bass", "start": "one", "text": "a", "approved_by": "x"}, "APPROVALS_INVALID"),
        ({"voice": "bass", "start": "1", "text": " ", "approved_by": "x"}, "APPROVALS_INVALID"),
        ({"voice": "bass", "start": "1", "text": "a", "approved_by": ""}, "APPROVALS_INVALID"),
        ({"voice": "bass", "start": "1", "text": "a"}, "APPROVALS_INVALID"),
        ("nope", "APPROVALS_INVALID"),
    ],
)
def test_malformed_approvals_are_configuration_errors(
    tmp_path: Path, entry: Any, code: str
) -> None:
    assert code_of(approvals_file(tmp_path, [entry])) == code


def test_unreadable_and_wrong_schema_files(tmp_path: Path) -> None:
    assert code_of(tmp_path / "missing.json") == "APPROVALS_UNREADABLE"
    broken = tmp_path / "b.json"
    broken.write_text("{", encoding="utf-8")
    assert code_of(broken) == "APPROVALS_INVALID"
    assert code_of(write(tmp_path / "w.json", {"schema": "other/1"})) == "APPROVALS_INVALID"
    assert (
        code_of(write(tmp_path / "n.json", {"schema": APPROVALS_SCHEMA, "source_sha256": SHA}))
        == "APPROVALS_INVALID"
    )
