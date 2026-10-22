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
from smf_builders import ritardando_from

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


# --- errors let you open the score to fix it ---------------------------------------------------


def test_open_to_fix_is_off_until_a_score_was_chosen(rig: Rig) -> None:
    assert not rig.window.score_section.fix.isEnabled()
    assert not rig.window.validation_section.fix.isEnabled()
    rig.window.open_to_fix()
    assert rig.prompts.informed == ["Choose a score first."]
    assert rig.notated == []
    assert rig.opened == []


def test_a_musicxml_score_opens_as_it_is_in_the_notation_program(rig: Rig) -> None:
    score = rig.load()
    assert rig.window.score_section.fix.isEnabled()
    assert rig.window.validation_section.fix.isEnabled()
    rig.window.validation_section.fix.click()
    assert rig.notated == [score]
    assert rig.opened == []  # no picture to compare with
    assert rig.prompts.informed == []


def test_a_recognised_pdf_opens_as_a_named_copy_next_to_the_pdf_with_the_pdf_to_compare(
    rig: Rig,
) -> None:
    pdf = project(rig, "Hymn.pdf")
    with rig.qtbot.waitSignal(rig.controller.score_loaded, timeout=30000):
        rig.window.open_score(pdf)
    rig.window.score_section.fix.click()
    (copy,) = rig.notated
    assert copy.parent == pdf.parent
    assert copy.name.startswith("Hymn (recognised)")
    assert "<score-partwise" in copy.read_text(encoding="utf-8")  # what BLT read, not the PDF
    assert rig.opened == [pdf]  # the PDF is opened too, to check the music against
    assert "bar by bar against the PDF" in rig.prompts.informed[-1]
    rig.window.score_section.fix.click()  # again: the same copy, not a second one
    assert rig.notated == [copy, copy]
    assert len(list(pdf.parent.glob("Hymn (recognised)*"))) == 1


def test_without_a_notation_program_the_score_opens_in_the_default_program(rig: Rig) -> None:
    rig.notation_available = False
    score = rig.load()
    rig.window.score_section.fix.click()
    assert rig.notated == [score]  # tried first
    assert rig.opened == [score]  # then whatever the system opens .musicxml with
    assert rig.prompts.warnings == []


def test_when_nothing_can_open_it_the_person_is_told_where_the_file_is(rig: Rig) -> None:
    rig.notation_available = False
    rig.window.opener = lambda path: False
    score = rig.load()
    rig.window.open_to_fix()
    assert len(rig.prompts.warnings) == 1
    assert str(score) in rig.prompts.warnings[0]
    assert "MuseScore" in rig.prompts.warnings[0]


def test_a_score_that_could_not_be_read_can_still_be_opened(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_CONVERTER_MODE", "fail")
    path = project(rig, "Broken.mscz")
    with rig.qtbot.waitSignal(rig.controller.score_failed, timeout=30000):
        rig.window.open_score(path)
    assert rig.controller.score is None
    assert rig.window.score_section.fix.isEnabled()
    rig.window.score_section.fix.click()
    assert rig.notated == [path]


def test_a_pdf_that_could_not_be_read_opens_as_a_picture_not_in_the_notation_program(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_CONVERTER_MODE", "fail")
    pdf = project(rig, "Broken.pdf")
    with rig.qtbot.waitSignal(rig.controller.score_failed, timeout=30000):
        rig.window.open_score(pdf)
    rig.window.score_section.fix.click()
    assert rig.opened == [pdf]
    assert rig.notated == []


def test_the_window_says_the_tempo_follows_musescores_playback(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    playback = rig.tmp / "playback.mid"
    playback.write_bytes(ritardando_from(100))  # the stand-in score is at 100 beats a minute
    monkeypatch.setenv("FAKE_CONVERTER_MIDI", str(playback))
    with rig.qtbot.waitSignal(rig.controller.score_loaded, timeout=30000):
        rig.window.open_score(project(rig, "Hymn.mscz"))
    rig.qtbot.waitUntil(lambda: not rig.controller.validating, timeout=20000)
    assert any("The tempo follows MuseScore's playback" in m for m in shown_messages(rig))
    score = rig.controller.score
    assert score is not None
    assert score.conversion is not None
    assert score.conversion["playback_tempo"]["applied"] is True


def test_the_window_says_nothing_about_tempo_when_there_is_no_playback(rig: Rig) -> None:
    with rig.qtbot.waitSignal(rig.controller.score_loaded, timeout=30000):
        rig.window.open_score(project(rig, "Hymn.mscz"))
    rig.qtbot.waitUntil(lambda: not rig.controller.validating, timeout=20000)
    assert not any("playback" in m for m in shown_messages(rig)), shown_messages(rig)
