"""Adding a voicebank to BLT's voices folder from a folder or a zip."""

import zipfile
from pathlib import Path

import pytest

from barbershop_tracks.core.pipeline import discover_singers
from barbershop_tracks.core.voices import VoiceInstallError, install_voicebank


def make_bank(folder: Path, *, character: bool = True, extra: dict[str, str] | None = None) -> Path:
    folder.mkdir(parents=True)
    if character:
        (folder / "character.txt").write_text(f"name={folder.name}\n", encoding="utf-8")
    (folder / "oto.ini").write_text("a.wav=a,0,100,-200,10,10\n", encoding="utf-8")
    (folder / "a.wav").write_bytes(b"RIFF")
    for name, text in (extra or {}).items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def zip_of(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


def code_of(source: Path, voices: Path) -> str:
    with pytest.raises(VoiceInstallError) as info:
        install_voicebank(source, voices)
    return info.value.code


def test_a_voicebank_folder_is_copied_in_and_found(tmp_path: Path) -> None:
    source = make_bank(tmp_path / "from" / "My Voice (v2)")
    voices = tmp_path / "voices"
    done = install_voicebank(source, voices)
    assert [d.name for d in done] == ["My Voice (v2)"]
    assert discover_singers(voices) == {"My Voice (v2)"}
    assert (source / "a.wav").is_file()  # the person's own copy is left alone
    assert [p.name for p in voices.iterdir()] == ["My Voice (v2)"]  # no scratch folder left


def test_a_zip_with_the_bank_in_a_folder_is_unpacked(tmp_path: Path) -> None:
    files = {
        "Bennett (ENG)/character.txt": b"name=B",
        "Bennett (ENG)/B3/oto.ini": b"",
        "x.txt": b"",
    }
    archive = zip_of(tmp_path / "Bennett.zip", files)
    done = install_voicebank(archive, tmp_path / "voices")
    assert [d.name for d in done] == ["Bennett (ENG)"]
    assert discover_singers(tmp_path / "voices") == {"Bennett (ENG)"}


def test_a_zip_with_the_bank_at_its_top_is_named_after_the_zip(tmp_path: Path) -> None:
    archive = zip_of(tmp_path / "Cool Voice.zip", {"character.txt": b"name=c", "oto.ini": b""})
    assert [d.name for d in install_voicebank(archive, tmp_path / "v")] == ["Cool Voice"]


def test_a_pack_keeps_its_folders_and_every_bank_in_it_is_added(tmp_path: Path) -> None:
    archive = zip_of(
        tmp_path / "pack.zip",
        {"Pack/A/character.txt": b"", "Pack/B/character.txt": b"", "Pack/readme.txt": b""},
    )
    done = install_voicebank(archive, tmp_path / "v")
    assert sorted(d.name for d in done) == ["Pack\\A", "Pack\\B"]
    assert discover_singers(tmp_path / "v") == {"Pack\\A", "Pack\\B"}


def test_a_bank_without_a_character_file_gets_one_in_the_copy_only(tmp_path: Path) -> None:
    source = make_bank(tmp_path / "from" / "bare", character=False)
    done = install_voicebank(source, tmp_path / "voices")
    assert "character.txt" in done[0].notes[0]
    assert (tmp_path / "voices" / "bare" / "character.txt").read_text(encoding="utf-8") == (
        "name=bare\n"
    )
    assert not (source / "character.txt").exists()
    assert discover_singers(tmp_path / "voices") == {"bare"}


def test_a_neural_voice_is_added_with_a_warning(tmp_path: Path) -> None:
    source = make_bank(
        tmp_path / "from" / "ds", extra={"character.yaml": "singer_type: diffsinger"}
    )
    done = install_voicebank(source, tmp_path / "voices")
    assert "DiffSinger" in done[0].notes[0]


def test_nothing_already_there_is_replaced(tmp_path: Path) -> None:
    voices = tmp_path / "voices"
    first = make_bank(tmp_path / "from" / "same")
    install_voicebank(first, voices)
    (voices / "same" / "mine.txt").write_text("keep", encoding="utf-8")
    assert code_of(first, voices) == "VOICE_EXISTS"
    assert (voices / "same" / "mine.txt").read_text(encoding="utf-8") == "keep"
    assert [p.name for p in voices.iterdir()] == ["same"]


@pytest.mark.parametrize("name", ["../evil.txt", "a/../../evil.txt", "C:/evil.txt", "/evil.txt"])
def test_a_zip_cannot_write_outside_the_voices_folder(tmp_path: Path, name: str) -> None:
    archive = zip_of(tmp_path / "bad.zip", {"bank/character.txt": b"", name: b"x"})
    assert code_of(archive, tmp_path / "voices") == "VOICE_UNSAFE_PATH"
    assert not (tmp_path / "evil.txt").exists()
    assert list((tmp_path / "voices").iterdir()) == []


def test_things_that_are_not_voicebanks_are_refused_with_the_reason(tmp_path: Path) -> None:
    voices = tmp_path / "voices"
    assert code_of(tmp_path / "missing.zip", voices) == "VOICE_SOURCE_MISSING"
    other = tmp_path / "bank.7z"
    other.write_bytes(b"7z")
    assert code_of(other, voices) == "VOICE_FORMAT"
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip")
    assert code_of(broken, voices) == "VOICE_NOT_A_ZIP"
    empty = zip_of(tmp_path / "docs.zip", {"readme.txt": b"hello"})
    assert code_of(empty, voices) == "VOICE_NOT_A_VOICEBANK"
    inside = make_bank(voices / "already")
    assert code_of(inside, voices) == "VOICE_ALREADY_THERE"
    assert [p.name for p in voices.iterdir()] == ["already"]


def test_shift_jis_names_in_a_zip_are_read_as_japanese_not_as_mojibake(tmp_path: Path) -> None:
    wav = "あ.wav"
    path = zip_of(tmp_path / "jp.zip", {"bank/character.txt": b"", "bank/XX.wav": b""})
    # as Japanese Windows stores a name: Shift-JIS bytes, with no flag saying so (same length)
    path.write_bytes(path.read_bytes().replace(b"XX.wav", wav.encode("shift_jis")))
    install_voicebank(path, tmp_path / "voices")
    assert (tmp_path / "voices" / "bank" / wav).is_file()
