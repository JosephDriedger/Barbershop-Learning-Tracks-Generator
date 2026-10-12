"""The built-in installation self-test: its score, its voicebank and its failure reporting."""

from pathlib import Path

import pytest

from barbershop_tracks.cli import main
from barbershop_tracks.core.musicxml.parser import parse_musicxml
from barbershop_tracks.selftest import ALIASES, LINES, SINGER_ID, build_voicebank, selftest_score


def test_selftest_score_is_a_four_part_score_with_lyrics(tmp_path: Path) -> None:
    path = tmp_path / "selftest.musicxml"
    path.write_text(selftest_score(), encoding="utf-8")
    parsed = parse_musicxml(path)
    assert parsed.song is not None
    assert not parsed.issues.has_errors
    assert [part.name for part in parsed.song.parts] == ["Tenor", "Lead", "Baritone", "Bass"]
    assert sorted(LINES) == ["baritone", "bass", "lead", "tenor"]


def test_synthetic_voicebank_has_one_wav_per_alias(tmp_path: Path) -> None:
    folder = build_voicebank(tmp_path)
    assert folder.name == SINGER_ID
    for alias in ALIASES:
        assert (folder / f"{alias}.wav").is_file()
        assert f"{alias}.wav={alias}," in (folder / "oto.ini").read_text(encoding="utf-8")


def test_selftest_fails_cleanly_without_a_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("BLT_CONFIG", str(tmp_path / "no-config.json"))
    monkeypatch.delenv("BLT_HOST_DIR", raising=False)
    code = main(
        ["selftest", "--host-dir", str(tmp_path / "nowhere"), "--data-dir", str(tmp_path / "data")]
    )
    assert code == 1
    assert "FAILED" in capsys.readouterr().out
