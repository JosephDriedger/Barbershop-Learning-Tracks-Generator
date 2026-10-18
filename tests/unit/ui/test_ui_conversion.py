"""A MuseScore project or a PDF in the window: converted, flagged, never recognised silently."""

import hashlib
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from pytestqt.qtbot import QtBot
from test_ui_window import Rig

from barbershop_tracks.core.pipeline import ErrorCategory, PipelineError
from barbershop_tracks.ui.explain import explain
from cli_scores import quartet_xml
from shims import write_shim

pytestmark = pytest.mark.gui

FAKE = Path(__file__).resolve().parents[2] / "fake_converter.py"


@pytest.fixture
def rig(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    exported = tmp_path / "exported.musicxml"
    exported.write_text(quartet_xml(all_lyrics=True), encoding="utf-8")
    monkeypatch.setenv("BLT_MUSESCORE", str(write_shim(tmp_path, "musescore", FAKE)))
    monkeypatch.setenv("BLT_AUDIVERIS", str(write_shim(tmp_path, "audiveris", FAKE)))
    monkeypatch.setenv("FAKE_CONVERTER_SOURCE", str(exported))
    monkeypatch.setenv("FAKE_CONVERTER_LOG", str(tmp_path / "converter.log"))
    monkeypatch.setenv("FAKE_CONVERTER_MODE", "ok")
    return Rig(qtbot, tmp_path)


def project(rig: Rig, name: str) -> Path:
    path = rig.tmp / name
    path.write_bytes(b"the file as the person has it")
    return path


def shown_messages(rig: Rig) -> list[str]:
    section = rig.window.validation_section
    return [section.list.item(i).text() for i in range(section.list.count())]


def test_a_musescore_project_opens_like_a_score_and_says_how_it_was_read(rig: Rig) -> None:
    path = project(rig, "Hymn.mscz")
    with rig.qtbot.waitSignal(rig.controller.score_loaded, timeout=30000):
        rig.window.open_score(path)
    score = rig.controller.score
    assert score is not None
    assert score.path == path
    assert score.sha256 == hashlib.sha256(b"the file as the person has it").hexdigest()
    assert score.conversion is not None
    assert score.conversion["tool"] == "MuseScore"
    assert score.accepted_recognition is False
    assert "4 parts found" in rig.window.score_section.parts.text()
    assert rig.prompts.confirmations == []  # a project is exported by its own program: no question
    rig.qtbot.waitUntil(lambda: not rig.controller.validating, timeout=20000)
    assert any("Read from a .mscz file by MuseScore" in m for m in shown_messages(rig))


def test_a_pdf_is_not_recognised_when_the_person_says_no(rig: Rig) -> None:
    rig.prompts.confirm_answer = False
    rig.window.open_score(project(rig, "Hymn.pdf"))
    assert rig.prompts.confirmations == ["Recognise the music in this file?"]
    assert rig.controller.score is None
    assert not (rig.tmp / "converter.log").exists()  # the recognising program was never started


def test_a_pdf_the_person_accepts_is_recognised_and_stays_flagged_until_generation(
    rig: Rig,
) -> None:
    rig.prompts.confirm_answer = True
    with rig.qtbot.waitSignal(rig.controller.score_loaded, timeout=30000):
        rig.window.open_score(project(rig, "Hymn.pdf"))
    score = rig.controller.score
    assert score is not None
    assert score.accepted_recognition is True
    assert score.conversion is not None
    assert score.conversion["recognised"] is True
    rig.qtbot.waitUntil(lambda: not rig.controller.validating, timeout=20000)
    warning = next(m for m in shown_messages(rig) if "recognised from a picture" in m)
    assert "Audiveris" in warning
    assert "check the notes, rhythms and words of every part" in warning
    assert rig.controller.build_request().accept_recognition is True


def test_a_musicxml_score_never_asks_and_is_not_flagged(rig: Rig) -> None:
    rig.load()
    assert rig.prompts.confirmations == []
    assert rig.controller.score is not None
    assert rig.controller.score.conversion is None
    assert rig.controller.build_request().accept_recognition is False


def test_dropping_a_musescore_project_or_a_pdf_opens_it(rig: Rig) -> None:
    rig.prompts.confirm_answer = False
    rig.window.handle_drop([QUrl.fromLocalFile(str(project(rig, "Hymn.pdf")))])
    assert rig.prompts.confirmations == ["Recognise the music in this file?"]
    with rig.qtbot.waitSignal(rig.controller.score_loaded, timeout=30000):
        rig.window.handle_drop([QUrl.fromLocalFile(str(project(rig, "Hymn.mscz")))])
    assert rig.controller.score is not None


def test_the_file_chooser_offers_the_new_kinds() -> None:
    from barbershop_tracks.ui.prompts import SCORE_FILTER

    for suffix in ("*.mscz", "*.mscx", "*.pdf", "*.musicxml", "*.mxl"):
        assert suffix in SCORE_FILTER


def test_a_missing_converter_is_explained_with_the_way_out(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BLT_MUSESCORE")
    for name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
        monkeypatch.setenv(name, str(rig.tmp / "nowhere"))
    monkeypatch.setenv("PATH", "")
    with rig.qtbot.waitSignal(rig.controller.score_failed, timeout=30000):
        rig.window.open_score(project(rig, "Hymn.mscz"))
    shown = rig.window.progress_section.result_title.text()
    assert "MuseScore is needed to open this file" in shown
    assert rig.controller.score is None


def test_each_conversion_failure_has_a_plain_explanation() -> None:
    for code, title in (
        ("CONVERTER_NOT_FOUND", "is needed to open this file"),
        ("CONVERSION_FAILED", "could not be turned into a score"),
        ("CONVERSION_TIMEOUT", "could not be turned into a score"),
        ("CONVERSION_NO_OUTPUT", "could not be turned into a score"),
        ("CONVERSION_AMBIGUOUS", "could not be turned into a score"),
        ("RECOGNITION_NOT_CONFIRMED", "has to be accepted first"),
    ):
        said = explain(PipelineError(ErrorCategory.SOURCE, code, "message", {"tool": "Audiveris"}))
        assert title in said.title
        assert said.steps
    ambiguous = explain(
        PipelineError(ErrorCategory.SOURCE, "CONVERSION_AMBIGUOUS", "two", {"tool": "Audiveris"})
    )
    assert "Split the PDF" in ambiguous.steps[0]
