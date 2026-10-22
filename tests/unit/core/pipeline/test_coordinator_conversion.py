"""A MuseScore project or a PDF through the whole pipeline: bound to the chosen file, recorded."""

import hashlib
import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from test_coordinator import Rig, error_of

from barbershop_tracks.core.pipeline import PipelineError
from cli_scores import quartet_xml
from shims import write_shim
from smf_builders import ritardando_from

FAKE = Path(__file__).resolve().parents[3] / "fake_converter.py"


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    made = Rig(tmp_path)
    exported = tmp_path / "exported.musicxml"
    exported.write_text(quartet_xml(all_lyrics=True), encoding="utf-8")
    monkeypatch.setenv("BLT_MUSESCORE", str(write_shim(tmp_path, "musescore", FAKE)))
    monkeypatch.setenv("BLT_AUDIVERIS", str(write_shim(tmp_path, "audiveris", FAKE)))
    monkeypatch.setenv("FAKE_CONVERTER_SOURCE", str(exported))
    monkeypatch.setenv("FAKE_CONVERTER_LOG", str(tmp_path / "converter.log"))
    monkeypatch.setenv("FAKE_CONVERTER_MODE", "ok")
    return made


def choose(rig: Rig, name: str) -> Path:
    path = rig.root / name
    path.write_bytes(b"the project as the person has it")
    rig.score = path
    return path


def manifest_of(result: object) -> dict[str, object]:
    destination = result.destination  # type: ignore[attr-defined]
    return json.loads((destination / "manifest.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_a_musescore_project_generates_the_thirteen_tracks(rig: Rig) -> None:
    choose(rig, "Hymn.mscz")
    result = rig.run()
    assert result.destination.name == "Hymn_learning_tracks"
    assert len([p for p in result.destination.iterdir() if p.suffix == ".wav"]) == 13
    assert rig.staging() == []


def test_everything_is_bound_to_the_file_chosen_not_to_the_export(rig: Rig) -> None:
    project = choose(rig, "Hymn.mscz")
    result = rig.run()
    wanted = hashlib.sha256(project.read_bytes()).hexdigest()
    assert result.plan.source.sha256 == wanted  # what approvals and pronunciations are bound to
    assert result.plan.source.display_name == "Hymn.mscz"
    manifest = manifest_of(result)
    source = manifest["source"]
    assert isinstance(source, dict)
    assert source["sha256"] == wanted
    assert source["display_name"] == "Hymn.mscz"
    conversion = source["conversion"]
    assert isinstance(conversion, dict)
    assert conversion["tool"] == "MuseScore"
    assert conversion["kind"] == "export"
    assert conversion["recognised"] is False
    assert (
        conversion["converted_sha256"] != wanted
    )  # the MusicXML that was analysed is recorded too


def test_a_musicxml_score_records_no_conversion(rig: Rig) -> None:
    manifest = manifest_of(rig.run())
    source = manifest["source"]
    assert isinstance(source, dict)
    assert source["conversion"] is None


def test_the_same_project_is_converted_once_across_runs(rig: Rig) -> None:
    choose(rig, "Hymn.mscz")
    rig.run()
    rig.run(replace(rig.request(), replace=True))
    starts = (rig.root / "converter.log").read_text(encoding="utf-8").splitlines()
    # converted once (the second start of that conversion is MuseScore's playback export)
    assert len([s for s in starts if ".mid " not in s + " "]) == 1


def test_a_pdf_is_refused_until_recognition_is_accepted_and_nothing_runs(rig: Rig) -> None:
    choose(rig, "Hymn.pdf")
    problem = error_of(rig)
    assert problem.code == "RECOGNITION_NOT_CONFIRMED"
    assert not (rig.root / "converter.log").exists()
    assert rig.renderer.calls == []


def test_an_accepted_pdf_generates_and_the_package_says_the_notes_were_recognised(rig: Rig) -> None:
    choose(rig, "Hymn.pdf")
    result = rig.run(replace(rig.request(), accept_recognition=True))
    source = manifest_of(result)["source"]
    assert isinstance(source, dict)
    conversion = source["conversion"]
    assert isinstance(conversion, dict)
    assert conversion["tool"] == "Audiveris"
    assert conversion["recognised"] is True
    assert "not checked" in conversion["note"]


def test_a_missing_converter_is_a_source_problem_with_the_tool_named(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    choose(rig, "Hymn.mscz")
    monkeypatch.delenv("BLT_MUSESCORE")
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("ProgramFiles", str(rig.root / "none"))
    monkeypatch.setenv("ProgramFiles(x86)", str(rig.root / "none"))
    monkeypatch.setenv("ProgramW6432", str(rig.root / "none"))
    monkeypatch.setenv("LOCALAPPDATA", str(rig.root / "none"))
    problem = error_of(rig)
    assert problem.code == "CONVERTER_NOT_FOUND"
    assert problem.details["tool"] == "MuseScore"
    assert rig.renderer.calls == []


def test_a_failing_converter_leaves_no_package_and_no_working_files(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    choose(rig, "Hymn.mscz")
    monkeypatch.setenv("FAKE_CONVERTER_MODE", "fail")
    problem = error_of(rig)
    assert problem.code == "CONVERSION_FAILED"
    assert "newer version" in problem.message
    assert not (rig.root / "out").exists()
    assert rig.staging() == []


def test_lyric_approvals_and_pronunciations_follow_the_project_not_the_export(rig: Rig) -> None:
    project = choose(rig, "Hymn.mscz")
    digest = hashlib.sha256(project.read_bytes()).hexdigest()
    result = rig.run()
    assert result.plan.source.sha256 == digest
    # a changed project is a different identity even if its export were identical
    project.write_bytes(b"the project, edited")
    again = rig.run(replace(rig.request(), replace=True))
    assert again.plan.source.sha256 == hashlib.sha256(b"the project, edited").hexdigest()
    assert again.plan.source.sha256 != digest


def test_a_pdf_conversion_that_is_cancelled_publishes_nothing(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from barbershop_tracks.core.rendering import CancelToken

    choose(rig, "Hymn.pdf")
    token = CancelToken()
    token.cancel()
    with pytest.raises(PipelineError) as info:
        rig.run(replace(rig.request(), accept_recognition=True), cancel=token)
    assert info.value.code == "CANCELLED"
    assert not (rig.root / "out").exists()
    assert rig.staging() == []


def test_a_musescore_projects_playback_tempo_reaches_the_plan_the_warnings_and_the_package(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    playback = rig.root / "playback.mid"
    playback.write_bytes(ritardando_from(100))  # the stand-in score is at 100 beats a minute
    monkeypatch.setenv("FAKE_CONVERTER_MIDI", str(playback))
    choose(rig, "Hymn.mscz")
    result = rig.run()
    assert [(t.position, float(t.bpm)) for t in result.plan.tempo] == [
        (0, 100.0),
        (Fraction(3, 2), 90.0),
        (Fraction(2), 75.0),
        (Fraction(4), 100.0),
    ]
    assert any(w.startswith("TEMPO_FROM_PLAYBACK") for w in result.warnings)
    source = manifest_of(result)["source"]
    assert isinstance(source, dict)
    conversion = source["conversion"]
    assert isinstance(conversion, dict)
    assert conversion["playback_tempo"]["applied"] is True
    assert conversion["playback_tempo"]["changes"] == 3


def test_without_a_playback_the_tempo_is_the_scores_own_marks(rig: Rig) -> None:
    choose(rig, "Hymn.mscz")
    result = rig.run()
    assert [float(t.bpm) for t in result.plan.tempo] == [100.0]
    assert not any("TEMPO_" in w for w in result.warnings)
