"""``barbershop-tracks fix``: open a score in MuseScore to correct it before generating."""

import time
from pathlib import Path

import pytest

from barbershop_tracks.cli import main
from cli_scores import quartet_xml
from shims import write_shim

FAKE = Path(__file__).resolve().parents[1] / "fake_converter.py"
PDF_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "pdf"


@pytest.fixture
def started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """MuseScore replaced by a stand-in that writes the file it was started on to a log."""
    log = tmp_path / "started.log"
    monkeypatch.setenv("BLT_MUSESCORE", str(write_shim(tmp_path, "musescore", FAKE)))
    monkeypatch.setenv("FAKE_CONVERTER_SOURCE", str(tmp_path / "unused.musicxml"))
    monkeypatch.setenv("FAKE_CONVERTER_LOG", str(log))
    return log


def _started_on(log: Path) -> str:
    for _ in range(100):  # it runs on its own: wait for its first line
        if log.exists() and log.read_text(encoding="utf-8").strip():
            break
        time.sleep(0.1)
    return log.read_text(encoding="utf-8").strip()


def test_a_musicxml_score_opens_as_it_is(
    tmp_path: Path, started: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    score = tmp_path / "Hymn.musicxml"
    score.write_text(quartet_xml(all_lyrics=True), encoding="utf-8")
    assert main(["fix", str(score), "--no-wait"]) == 0
    assert _started_on(started) == str(score)
    out = capsys.readouterr().out
    assert f"Opened in MuseScore: {score}" in out
    assert "Check it against" not in out


def test_a_pdf_opens_as_an_editable_copy_beside_it(
    tmp_path: Path, started: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pdf = tmp_path / "Quartet.pdf"
    pdf.write_bytes((PDF_FIXTURES / "e3b_four_parts.pdf").read_bytes())
    assert main(["fix", str(pdf), "--no-wait"]) == 0
    copy = tmp_path / "Quartet (from PDF).musicxml"
    assert "<score-partwise" in copy.read_text(encoding="utf-8")
    assert _started_on(started) == str(copy)
    out = capsys.readouterr().out
    assert f"Check it against the original: {pdf}" in out
    assert "add a tempo mark" in out


def test_a_score_that_cannot_be_read_is_an_error(
    tmp_path: Path, started: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["fix", str(tmp_path / "missing.pdf"), "--no-wait"]) == 2
    assert "error:" in capsys.readouterr().err
    assert not started.exists()
