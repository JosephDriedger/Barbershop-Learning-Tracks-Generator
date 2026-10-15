"""The pronunciation engine a voicebank was made for, read from the names of its sounds."""

from pathlib import Path

from barbershop_tracks.core.rendering.engine_detect import (
    ARPASING,
    ENGLISH_XSAMPA,
    aliases_of,
    classify,
    detect,
)

XSAMPA = ["@ p", "@ b", "S@", "tS@", "@ N", "p@", "t@", "k@", "m@", "n@", "l@", "r@", "s@"] * 3
ARPABET = [f"{c} {v}" for c in ("k", "p", "t", "m", "n", "s") for v in ("ae", "ih", "iy", "uw")]
ROMAJI = [c + v for c in "kstnhmyrw" for v in "aiueo"]


def make_bank(folder: Path, aliases: list[str], encoding: str = "utf-8") -> Path:
    folder.mkdir(parents=True)
    lines = [f"s{i}.wav={alias},0,100,-200,10,10" for i, alias in enumerate(aliases)]
    (folder / "oto.ini").write_text("\n".join(lines) + "\n", encoding=encoding)
    return folder


def test_x_sampa_names_point_to_the_x_sampa_engine() -> None:
    found = classify(XSAMPA)
    assert found is not None
    assert found.phonemizer == ENGLISH_XSAMPA
    assert "X-SAMPA" in found.why


def test_arpabet_names_point_to_arpasing() -> None:
    found = classify(ARPABET)
    assert found is not None
    assert found.phonemizer == ARPASING


def test_plain_syllables_say_nothing() -> None:
    assert classify(ROMAJI) is None  # the default engine stays


def test_too_few_sounds_say_nothing() -> None:
    assert classify(["@ p", "@ b"]) is None


def test_a_bank_folder_is_read_from_its_oto_ini(tmp_path: Path) -> None:
    bank = make_bank(tmp_path / "bank", XSAMPA)
    assert len(aliases_of(bank)) == len(XSAMPA)
    found = detect(bank)
    assert found is not None
    assert found.phonemizer == ENGLISH_XSAMPA


def test_the_text_encoding_the_bank_names_is_used(tmp_path: Path) -> None:
    bank = make_bank(tmp_path / "bank", XSAMPA, encoding="shift_jis")
    (bank / "character.yaml").write_text("text_file_encoding: shift_jis\n", encoding="utf-8")
    assert detect(bank) is not None


def test_a_missing_or_empty_folder_says_nothing(tmp_path: Path) -> None:
    assert detect(tmp_path / "nowhere") is None
    (tmp_path / "empty").mkdir()
    assert detect(tmp_path / "empty") is None
