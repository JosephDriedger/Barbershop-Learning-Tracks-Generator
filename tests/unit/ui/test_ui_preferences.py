from pathlib import Path

from PySide6.QtCore import QByteArray

from barbershop_tracks.models import VoiceRole
from barbershop_tracks.ui.preferences import Preferences


def test_defaults_are_ordinary(tmp_path: Path) -> None:
    prefs = Preferences.at(tmp_path / "p.ini")
    assert prefs.audio_format == "wav"
    assert prefs.gain_preset == "default"
    assert prefs.mp3_quality == 2
    assert prefs.keep_stems is False
    assert prefs.output_dir == ""
    assert prefs.timeout_minutes == 15
    assert prefs.singer(VoiceRole.LEAD) == ""
    assert prefs.geometry.isEmpty()


def test_values_survive_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "p.ini"
    first = Preferences.at(path)
    first.last_score_dir = "C:/Scores"
    first.output_dir = "C:/Tracks"
    first.audio_format = "both"
    first.gain_preset = "custom"
    first.custom_focus = 0.7
    first.custom_others = 0.1
    first.mp3_quality = 4
    first.keep_stems = True
    first.phonemizer = "Some.Phonemizer"
    first.set_singer(VoiceRole.BASS, "deep-voice")
    first.geometry = QByteArray(b"\x01\x02\x03")
    first.sync()
    second = Preferences.at(path)
    assert second.last_score_dir == "C:/Scores"
    assert second.output_dir == "C:/Tracks"
    assert second.audio_format == "both"
    assert second.gain_preset == "custom"
    assert (second.custom_focus, second.custom_others) == (0.7, 0.1)
    assert second.mp3_quality == 4
    assert second.keep_stems is True
    assert second.phonemizer == "Some.Phonemizer"
    assert second.singer(VoiceRole.BASS) == "deep-voice"
    assert bytes(second.geometry) == b"\x01\x02\x03"


def test_nonsense_values_fall_back_instead_of_breaking_startup(tmp_path: Path) -> None:
    path = tmp_path / "p.ini"
    path.write_text(
        "[output]\nformat=flac\ngain_preset=loud\nmp3_quality=77\ncustom_focus=abc\n"
        "keep_stems=maybe\n[engine]\ntimeout_minutes=-5\n",
        encoding="utf-8",
    )
    prefs = Preferences.at(path)
    assert prefs.audio_format == "wav"
    assert prefs.gain_preset == "default"
    assert prefs.mp3_quality == 9  # clamped
    assert prefs.custom_focus == 0.5
    assert prefs.keep_stems is False
    assert prefs.timeout_minutes == 1


def test_nothing_about_a_score_or_staging_is_stored(tmp_path: Path) -> None:
    path = tmp_path / "p.ini"
    prefs = Preferences.at(path)
    prefs.output_dir = "C:/Tracks"
    prefs.sync()
    stored = path.read_text(encoding="utf-8").lower()
    for word in ("staging", "approval", "assign", "sha"):
        assert word not in stored
