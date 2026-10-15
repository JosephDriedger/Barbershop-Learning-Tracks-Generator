"""MuseScore projects and PDFs: converted by an installed program; recognition needs consent."""

import hashlib
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from barbershop_tracks.core.errors import ScoreConversionError, ScoreXmlError
from barbershop_tracks.core.musicxml import convert, opened_score, parse_musicxml
from barbershop_tracks.core.musicxml.convert import (
    clean_environment,
    find_audiveris,
    find_musescore,
    is_converted_kind,
    needs_recognition,
)
from barbershop_tracks.core.rendering import CancelToken
from cli_scores import quartet_xml

FAKE = Path(__file__).resolve().parents[3] / "fake_converter.py"
SCORE = quartet_xml(all_lyrics=True)


class Rig:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.log = root / "converter.log"
        self.source = root / "exported.musicxml"
        self.source.write_text(SCORE, encoding="utf-8")
        for name in ("musescore", "audiveris"):
            wrapper = root / f"{name}.cmd"
            wrapper.write_text(f'@"{sys.executable}" "{FAKE}" %*\r\n', encoding="ascii")
        monkeypatch.setenv("BLT_MUSESCORE", str(root / "musescore.cmd"))
        monkeypatch.setenv("BLT_AUDIVERIS", str(root / "audiveris.cmd"))
        monkeypatch.setenv("FAKE_CONVERTER_SOURCE", str(self.source))
        monkeypatch.setenv("FAKE_CONVERTER_LOG", str(self.log))
        self.monkeypatch = monkeypatch

    def mode(self, mode: str) -> None:
        self.monkeypatch.setenv("FAKE_CONVERTER_MODE", mode)

    def file(self, name: str, content: bytes = b"original bytes") -> Path:
        path = self.root / name
        path.write_bytes(content)
        return path

    def runs(self) -> int:
        return len(self.log.read_text(encoding="utf-8").splitlines()) if self.log.is_file() else 0


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    monkeypatch.setenv("FAKE_CONVERTER_MODE", "ok")
    return Rig(tmp_path, monkeypatch)


def leftovers() -> set[str]:
    return {p.name for p in Path(tempfile.gettempdir()).glob("blt-convert-*")}


def test_the_kinds_are_told_by_extension() -> None:
    for name in ("a.MSCZ", "a.mscx", "a.pdf"):
        assert is_converted_kind(name)
    for name in ("a.musicxml", "a.mxl"):
        assert not is_converted_kind(name)
    for name in ("a.pdf", "a.PNG"):
        assert needs_recognition(name)
    assert not needs_recognition("a.mscz")


def test_a_musicxml_file_is_passed_through_untouched(rig: Rig) -> None:
    path = rig.file("score.musicxml", SCORE.encode("utf-8"))
    with opened_score(path) as opened:
        assert opened.parse_path == path
        assert opened.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
        assert opened.conversion is None
        assert opened.display_name == "score.musicxml"
    assert rig.runs() == 0  # no program was started


def test_a_musescore_project_is_exported_by_musescore_and_keeps_its_own_identity(rig: Rig) -> None:
    before = leftovers()
    project = rig.file("Hymn.mscz")
    with opened_score(project) as opened:
        assert opened.parse_path.suffix == ".musicxml"
        assert opened.parse_path != project
        assert (
            parse_musicxml(opened.parse_path).song is not None
        )  # the converted file is read as MusicXML
        # identity is the project's, never the export's (MuseScore dates every export)
        assert opened.sha256 == hashlib.sha256(b"original bytes").hexdigest()
        assert opened.display_name == "Hymn.mscz"
        note = opened.conversion
        assert note is not None
        assert note.tool == "MuseScore"
        assert note.kind == "export"
        assert note.recognised is False
        assert note.converted_sha256 == hashlib.sha256(SCORE.encode("utf-8")).hexdigest()
        assert note.program == "musescore.cmd"
        assert "MuseScore" in note.note
    assert leftovers() == before  # the working copy is gone after the score was read
    args = rig.log.read_text(encoding="utf-8").split()
    assert args[0] == "-o"
    assert args[2].endswith("Hymn.mscz")
    assert args[1].endswith("Hymn.musicxml")


def test_mscx_is_handled_like_mscz(rig: Rig) -> None:
    with opened_score(rig.file("Hymn.mscx")) as opened:
        assert opened.conversion is not None
        assert opened.conversion.tool == "MuseScore"


def test_the_conversion_is_kept_and_reused_for_the_same_file(rig: Rig) -> None:
    cache = rig.root / "cache"
    project = rig.file("Hymn.mscz")
    with opened_score(project, cache=cache) as first:
        kept = first.parse_path
        assert kept.parent == cache
    with opened_score(project, cache=cache) as second:
        assert second.parse_path == kept
        assert second.sha256 == first.sha256
        assert second.conversion == first.conversion
    assert rig.runs() == 1  # converted once
    assert kept.is_file()
    project.write_bytes(b"edited bytes")
    with opened_score(project, cache=cache) as third:
        assert (
            third.sha256 != first.sha256
        )  # another file content: another identity, converted again
    assert rig.runs() == 2


def test_without_a_cache_every_open_converts_again_and_leaves_nothing(rig: Rig) -> None:
    before = leftovers()
    project = rig.file("Hymn.mscz")
    for _ in range(2):
        with opened_score(project):
            pass
    assert rig.runs() == 2
    assert leftovers() == before


def test_a_missing_musescore_says_where_to_get_it(rig: Rig) -> None:
    rig.monkeypatch.delenv("BLT_MUSESCORE")
    with (
        pytest.raises(ScoreConversionError) as error,
        opened_score(rig.file("Hymn.mscz"), environ={"PATH": ""}),
    ):
        pass
    assert error.value.code == "CONVERTER_NOT_FOUND"
    assert error.value.tool == "MuseScore"
    assert "musescore.org" in error.value.message
    assert "File > Export > MusicXML" in error.value.message


def test_a_converter_that_fails_is_reported_with_what_it_said(rig: Rig) -> None:
    rig.mode("fail")
    before = leftovers()
    with pytest.raises(ScoreConversionError) as error, opened_score(rig.file("Hymn.mscz")):
        pass
    assert error.value.code == "CONVERSION_FAILED"
    assert "code 3" in error.value.message
    assert "newer version" in error.value.message
    assert leftovers() == before


@pytest.mark.parametrize("mode", ["no_output", "empty"])
def test_a_converter_that_writes_nothing_is_reported(rig: Rig, mode: str) -> None:
    rig.mode(mode)
    with pytest.raises(ScoreConversionError) as error, opened_score(rig.file("Hymn.mscz")):
        pass
    assert error.value.code == "CONVERSION_NO_OUTPUT"


def test_an_export_that_is_not_xml_is_refused_by_the_usual_loader(rig: Rig) -> None:
    rig.mode("garbage")
    with opened_score(rig.file("Hymn.mscz")) as opened, pytest.raises(ScoreXmlError):
        parse_musicxml(opened.parse_path)


def test_a_converter_that_never_finishes_is_stopped(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.mode("hang")
    monkeypatch.setattr(convert, "MUSESCORE_TIMEOUT_SECONDS", 1.0)
    started = time.monotonic()
    with pytest.raises(ScoreConversionError) as error, opened_score(rig.file("Hymn.mscz")):
        pass
    assert error.value.code == "CONVERSION_TIMEOUT"
    assert time.monotonic() - started < 30


def test_cancelling_stops_the_converter(rig: Rig) -> None:
    rig.mode("hang")
    token = CancelToken()
    threading.Timer(1.0, token.cancel).start()
    with (
        pytest.raises(ScoreConversionError) as error,
        opened_score(rig.file("Hymn.mscz"), cancel=token),
    ):
        pass
    assert error.value.code == "CONVERSION_CANCELLED"


# --- a PDF: recognition, only when accepted ---------------------------------------------------


def test_a_pdf_is_never_recognised_unless_the_person_accepted_it(rig: Rig) -> None:
    with pytest.raises(ScoreConversionError) as error, opened_score(rig.file("Hymn.pdf")):
        pass
    assert error.value.code == "RECOGNITION_NOT_CONFIRMED"
    assert "recognition makes mistakes" in error.value.message
    assert rig.runs() == 0  # nothing was started, not even to look


def test_an_accepted_pdf_is_recognised_and_flagged_as_unchecked(rig: Rig) -> None:
    with opened_score(rig.file("Hymn.pdf"), accept_recognition=True) as opened:
        assert parse_musicxml(opened.parse_path).song is not None
        note = opened.conversion
        assert note is not None
        assert (note.tool, note.kind, note.recognised) == ("Audiveris", "recognition", True)
        assert "not checked" in note.note
        assert opened.sha256 == hashlib.sha256(b"original bytes").hexdigest()
    args = rig.log.read_text(encoding="utf-8").split()
    assert args[:3] == ["-batch", "-export", "-output"]
    assert args[-1].endswith("Hymn.pdf")


def test_a_compressed_result_of_recognition_is_read_too(rig: Rig) -> None:
    rig.mode("mxl")
    with opened_score(rig.file("Hymn.pdf"), accept_recognition=True) as opened:
        assert opened.parse_path.suffix == ".mxl"
        assert parse_musicxml(opened.parse_path).song is not None


def test_several_recognised_pieces_are_never_chosen_between(rig: Rig) -> None:
    rig.mode("two")
    with (
        pytest.raises(ScoreConversionError) as error,
        opened_score(rig.file("Hymn.pdf"), accept_recognition=True),
    ):
        pass
    assert error.value.code == "CONVERSION_AMBIGUOUS"
    assert "mvt1" in error.value.message
    assert "will not choose" in error.value.message


def test_a_missing_audiveris_says_where_to_get_it(rig: Rig) -> None:
    rig.monkeypatch.delenv("BLT_AUDIVERIS")
    with (
        pytest.raises(ScoreConversionError) as error,
        opened_score(rig.file("Hymn.pdf"), accept_recognition=True, environ={"PATH": ""}),
    ):
        pass
    assert error.value.code == "CONVERTER_NOT_FOUND"
    assert error.value.tool == "Audiveris"
    assert "Audiveris" in error.value.message


def test_the_programs_are_found_by_variable_or_by_the_usual_places(tmp_path: Path) -> None:
    program = tmp_path / "MuseScore4.exe"
    program.write_bytes(b"x")
    assert find_musescore({"BLT_MUSESCORE": str(program), "PATH": ""}) == program
    assert find_musescore({"PATH": ""}) is None
    folder = tmp_path / "Programs" / "Audiveris"
    folder.mkdir(parents=True)
    (folder / "Audiveris.exe").write_bytes(b"x")
    assert find_audiveris({"LOCALAPPDATA": str(tmp_path), "PATH": ""}) == folder / "Audiveris.exe"
    assert find_audiveris({"PATH": ""}) is None


# --- the environment the converting program is started in -----------------------------------------


def test_the_converter_is_not_started_with_bltss_qt_or_python_settings(rig: Rig) -> None:
    import json

    log = rig.root / "environment.json"
    rig.monkeypatch.setenv("FAKE_CONVERTER_ENV", str(log))
    rig.monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")  # BLT's own GUI tests set this
    rig.monkeypatch.setenv("QT_PLUGIN_PATH", "C:/somewhere/PySide6/plugins")
    rig.monkeypatch.setenv("PYTHONPATH", "C:/somewhere")
    rig.monkeypatch.setenv("BLT_VISIBLE", "kept")
    with opened_score(rig.file("Hymn.mscz")):
        pass
    seen = json.loads(log.read_text(encoding="utf-8"))
    assert not [k for k in seen if k.upper().startswith(("QT_", "QML", "PYTHON"))]
    assert (
        seen["BLT_VISIBLE"] == "kept"
    )  # everything else of the person's environment is left alone


def test_blts_own_folders_are_taken_out_of_the_path() -> None:
    ours = str(Path(sys.prefix) / "Lib" / "site-packages" / "PySide6")
    elsewhere = r"C:\Program Files\MuseScore 4in"
    env = clean_environment(
        {"PATH": f"{ours};{elsewhere}", "QT_QPA_PLATFORM": "offscreen", "TEMP": "t"}
    )
    assert "QT_QPA_PLATFORM" not in env
    assert env["TEMP"] == "t"
    parts = env["PATH"].split(";")
    assert elsewhere in parts
    assert ours not in parts
