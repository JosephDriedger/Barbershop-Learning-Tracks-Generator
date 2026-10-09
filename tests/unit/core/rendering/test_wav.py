import struct
from pathlib import Path

import pytest

from barbershop_tracks.core.rendering.wav import WavFormatError, read_info, read_wav
from wav_builders import chunk, fmt_chunk, pcm16, riff, tone, wav16, write


def code_of(path: Path) -> str:
    with pytest.raises(WavFormatError) as info:
        read_wav(path)
    return info.value.code


def test_a_plain_mono_pcm16_file_decodes(tmp_path: Path) -> None:
    audio = read_wav(write(tmp_path / "a.wav", wav16(tone(0.5))))
    assert (audio.info.channels, audio.info.sample_rate, audio.info.bit_depth) == (1, 44100, 16)
    assert audio.info.frames == 22050
    assert not audio.info.is_float
    assert audio.info.seconds == pytest.approx(0.5)
    assert max(audio.samples) == pytest.approx(0.3, abs=0.01)


def test_the_header_alone_can_be_read(tmp_path: Path) -> None:
    info = read_info(write(tmp_path / "a.wav", wav16(tone(0.1), rate=48000)))
    assert info.sample_rate == 48000
    assert info.frames == 4410  # tone() counts samples at 44.1 kHz


def test_extra_chunks_around_the_audio_are_skipped(tmp_path: Path) -> None:
    data = riff(
        chunk(b"LIST", b"INFOabc"),
        fmt_chunk(),
        chunk(b"data", pcm16(tone(0.05))),
        chunk(b"id3 ", b"x"),
    )
    assert read_wav(write(tmp_path / "a.wav", data)).info.frames == 2205


def test_stereo_is_read_as_its_first_channel(tmp_path: Path) -> None:
    frames = [0.5, -0.5, 0.25, -0.25]  # L R L R
    data = riff(fmt_chunk(channels=2), chunk(b"data", pcm16(frames)))
    audio = read_wav(write(tmp_path / "a.wav", data))
    assert audio.info.channels == 2
    assert audio.info.frames == 2
    assert [round(x, 2) for x in audio.samples] == [0.5, 0.25]


def test_24_bit_32_bit_float_and_extensible_formats(tmp_path: Path) -> None:
    int24 = b"".join((v).to_bytes(3, "little", signed=True) for v in (4194304, -4194304))
    a = read_wav(write(tmp_path / "a.wav", riff(fmt_chunk(bits=24), chunk(b"data", int24))))
    assert [round(x, 2) for x in a.samples] == [0.5, -0.5]
    floats = struct.pack("<2f", 0.5, -0.25)
    f = read_wav(write(tmp_path / "f.wav", riff(fmt_chunk(bits=32, tag=3), chunk(b"data", floats))))
    assert f.info.is_float
    assert list(f.samples) == [0.5, -0.25]
    ext = riff(fmt_chunk(extensible=True), chunk(b"data", pcm16([0.5])))
    assert read_wav(write(tmp_path / "e.wav", ext)).info.bit_depth == 16


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", "WAV_NOT_RIFF"),
        (b"this is not a wav file at all", "WAV_NOT_RIFF"),
        (b"RIFF\x04\x00\x00\x00WAVE", "WAV_NO_DATA"),
        (riff(chunk(b"data", b"\x00\x00")), "WAV_NO_FMT"),
        (riff(fmt_chunk()), "WAV_NO_DATA"),
        (riff(fmt_chunk(tag=2), chunk(b"data", b"\x00\x00")), "WAV_UNSUPPORTED_FORMAT"),
        (riff(fmt_chunk(bits=12), chunk(b"data", b"\x00\x00")), "WAV_BAD_FMT"),
        (riff(chunk(b"fmt ", b"\x01\x00"), chunk(b"data", b"\x00\x00")), "WAV_BAD_FMT"),
        (riff(fmt_chunk(), chunk(b"data", b"\x00\x00\x00")), "WAV_TRUNCATED"),  # odd byte count
    ],
)
def test_malformed_files_are_refused_with_a_code(tmp_path: Path, data: bytes, code: str) -> None:
    assert code_of(write(tmp_path / "a.wav", data)) == code


def test_a_data_chunk_that_claims_more_than_the_file_has_is_truncated(tmp_path: Path) -> None:
    good = wav16(tone(0.1))
    assert code_of(write(tmp_path / "a.wav", good[:-1000])) == "WAV_TRUNCATED"


def test_a_missing_file_is_a_wav_error_not_an_os_error(tmp_path: Path) -> None:
    assert code_of(tmp_path / "nope.wav") == "WAV_UNREADABLE"
