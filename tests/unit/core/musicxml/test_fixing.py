"""Giving a recognised score a name a person knows, and starting MuseScore on a file."""

import time
from pathlib import Path

import pytest

from barbershop_tracks.core.musicxml.fixing import editable_copy, open_in_musescore
from shims import write_shim

FAKE = Path(__file__).resolve().parents[3] / "fake_converter.py"


def _converted(tmp_path: Path) -> Path:
    path = tmp_path / "cache" / "abc123.musicxml"
    path.parent.mkdir(exist_ok=True)
    path.write_text("<score-partwise/>", encoding="utf-8")
    return path


def test_the_copy_is_named_after_the_original_and_sits_beside_it(tmp_path: Path) -> None:
    pdf = tmp_path / "scores" / "What Child.pdf"
    pdf.parent.mkdir()
    copy = editable_copy(_converted(tmp_path), pdf)
    assert copy == pdf.parent / "What Child (recognised).musicxml"
    assert copy.read_text(encoding="utf-8") == "<score-partwise/>"


def test_the_same_content_is_reused(tmp_path: Path) -> None:
    pdf = tmp_path / "Hymn.pdf"
    converted = _converted(tmp_path)
    first = editable_copy(converted, pdf)
    assert editable_copy(converted, pdf) == first
    assert len(list(tmp_path.glob("Hymn (recognised*"))) == 1


def test_a_persons_own_file_is_never_overwritten(tmp_path: Path) -> None:
    pdf = tmp_path / "Hymn.pdf"
    converted = _converted(tmp_path)
    mine = tmp_path / "Hymn (recognised).musicxml"
    mine.write_text("<score-partwise>my corrections</score-partwise>", encoding="utf-8")
    copy = editable_copy(converted, pdf)
    assert copy.name == "Hymn (recognised 2).musicxml"
    assert "my corrections" in mine.read_text(encoding="utf-8")


def test_an_unwritable_folder_falls_back_and_then_to_the_converted_file(tmp_path: Path) -> None:
    converted = _converted(tmp_path)
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    gone = tmp_path / "gone" / "Hymn.pdf"  # its folder does not exist, so nothing can be written
    assert editable_copy(converted, gone, fallback) == fallback / "Hymn (recognised).musicxml"
    assert editable_copy(converted, gone, None) == converted


def test_musescore_is_started_on_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    score = tmp_path / "Hymn.musicxml"
    score.write_text("<score-partwise/>", encoding="utf-8")
    log = tmp_path / "started.log"
    shim = write_shim(tmp_path, "musescore", FAKE)
    monkeypatch.setenv("FAKE_CONVERTER_SOURCE", str(score))  # the program is started in the real
    monkeypatch.setenv("FAKE_CONVERTER_LOG", str(log))  # environment, not in the lookup one below
    assert open_in_musescore(score, {"BLT_MUSESCORE": str(shim), "PATH": ""}) == shim
    for _ in range(100):  # it runs on its own, so wait for its first line
        if log.exists() and log.read_text(encoding="utf-8").strip():
            break
        time.sleep(0.1)
    assert log.read_text(encoding="utf-8").strip() == str(score)  # the file is its only argument


def test_no_musescore_means_none(tmp_path: Path) -> None:
    empty = str(tmp_path / "nowhere")
    environ = {"PATH": "", "ProgramFiles": empty, "LOCALAPPDATA": empty}
    assert open_in_musescore(tmp_path / "x.musicxml", environ) is None
