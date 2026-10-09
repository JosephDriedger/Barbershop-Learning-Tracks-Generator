"""A strict RIFF/WAVE reader for validating stems (no third-party audio library).

Reads PCM 8/16/24/32-bit and IEEE float 32/64 into floats in [-1, 1] (first channel only) and
refuses anything it cannot fully account for: a data chunk that claims more bytes than the file has,
a missing ``fmt `` or ``data`` chunk, or a format it does not know. The header can be read without
the samples.
"""

import array
import struct
from dataclasses import dataclass
from pathlib import Path


class WavFormatError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class WavInfo:
    channels: int
    sample_rate: int
    bit_depth: int
    is_float: bool
    frames: int

    @property
    def seconds(self) -> float:
        return self.frames / self.sample_rate


@dataclass(frozen=True, slots=True)
class WavAudio:
    info: WavInfo
    samples: array.array[float]  # first channel, normalised


_PCM, _FLOAT, _EXTENSIBLE = 1, 3, 0xFFFE


def _chunks(data: bytes) -> tuple[bytes, bytes, int]:
    """(fmt body, data body, declared data size) of a well-formed file."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise WavFormatError("WAV_NOT_RIFF", "not a RIFF/WAVE file")
    fmt: bytes | None = None
    position = 12
    while position + 8 <= len(data):
        tag = data[position : position + 4]
        size = struct.unpack_from("<I", data, position + 4)[0]
        body_start = position + 8
        if tag == b"data":
            if fmt is None:
                raise WavFormatError("WAV_NO_FMT", "the data chunk comes before any fmt chunk")
            body = data[body_start : body_start + size]
            if len(body) < size:
                raise WavFormatError(
                    "WAV_TRUNCATED", f"data chunk declares {size} bytes but {len(body)} are present"
                )
            return fmt, body, size
        if tag == b"fmt ":
            fmt = data[body_start : body_start + size]
            if len(fmt) < size:
                raise WavFormatError("WAV_TRUNCATED", "the fmt chunk is cut off")
        position = body_start + size + (size & 1)
    raise WavFormatError("WAV_NO_DATA", "no data chunk" if fmt else "no fmt chunk and no data")


def _format(fmt: bytes) -> tuple[int, int, int, int]:
    if len(fmt) < 16:
        raise WavFormatError("WAV_BAD_FMT", "the fmt chunk is too short")
    tag, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", fmt)
    if tag == _EXTENSIBLE and len(fmt) >= 26:
        tag = struct.unpack_from("<H", fmt, 24)[0]
    if tag not in (_PCM, _FLOAT):
        raise WavFormatError("WAV_UNSUPPORTED_FORMAT", f"format tag {tag} is not PCM or float")
    if channels < 1 or rate < 1 or bits not in (8, 16, 24, 32, 64):
        raise WavFormatError(
            "WAV_BAD_FMT", f"{channels} channel(s), {rate} Hz, {bits} bits is not a valid format"
        )
    if tag == _FLOAT and bits not in (32, 64):
        raise WavFormatError("WAV_UNSUPPORTED_FORMAT", f"{bits}-bit float is not supported")
    if tag == _PCM and bits == 64:
        raise WavFormatError("WAV_UNSUPPORTED_FORMAT", "64-bit PCM is not supported")
    return tag, channels, rate, bits


def read_info(path: Path) -> WavInfo:
    return read_wav(path, decode=False).info


def read_wav(path: Path, *, decode: bool = True) -> WavAudio:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise WavFormatError("WAV_UNREADABLE", f"cannot read {path.name}: {error}") from error
    fmt, body, _ = _chunks(data)
    tag, channels, rate, bits = _format(fmt)
    width = bits // 8
    frame_bytes = width * channels
    if len(body) % frame_bytes:
        raise WavFormatError(
            "WAV_TRUNCATED", f"data length {len(body)} is not a whole number of frames"
        )
    frames = len(body) // frame_bytes
    info = WavInfo(channels, rate, bits, tag == _FLOAT, frames)
    if not decode:
        return WavAudio(info, array.array("f"))
    out = array.array("f")
    if tag == _FLOAT:
        floats = array.array("f" if bits == 32 else "d")
        floats.frombytes(body)
        out.extend(floats[::channels])
    elif bits == 16:
        shorts = array.array("h")
        shorts.frombytes(body)
        out.extend(x / 32768.0 for x in shorts[::channels])
    elif bits == 8:
        out.extend((b - 128) / 128.0 for b in body[::channels])
    elif bits == 24:
        for index in range(0, len(body), frame_bytes):
            value = int.from_bytes(body[index : index + 3], "little", signed=True)
            out.append(value / 8388608.0)
    else:  # 32-bit PCM
        ints = array.array("i")
        ints.frombytes(body)
        out.extend(x / 2147483648.0 for x in ints[::channels])
    return WavAudio(info, out)
