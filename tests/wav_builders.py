"""Build WAV files of any shape for the stem-validation tests."""

import math
import struct
from collections.abc import Sequence
from pathlib import Path

RATE = 44100


def chunk(tag: bytes, body: bytes) -> bytes:
    padding = b"\x00" if len(body) % 2 else b""
    return tag + struct.pack("<I", len(body)) + body + padding


def fmt_chunk(
    channels: int = 1, rate: int = RATE, bits: int = 16, *, tag: int = 1, extensible: bool = False
) -> bytes:
    block = channels * bits // 8
    body = struct.pack(
        "<HHIIHH", 0xFFFE if extensible else tag, channels, rate, rate * block, block, bits
    )
    if extensible:
        body += struct.pack("<HHI", 22, bits, 0) + struct.pack("<H", tag) + b"\x00" * 14
    return chunk(b"fmt ", body)


def riff(*chunks: bytes) -> bytes:
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def pcm16(samples: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(samples)}h", *(int(max(-1, min(1, s)) * 32767) for s in samples))


def wav16(samples: Sequence[float], rate: int = RATE, channels: int = 1) -> bytes:
    return riff(fmt_chunk(channels, rate, 16), chunk(b"data", pcm16(samples)))


def tone(
    seconds: float, amplitude: float = 0.3, rate: int = RATE, start: float = 0.0
) -> list[float]:
    """Silence for ``start`` seconds, then a 220 Hz sine, ``seconds`` long in total."""
    total = int(seconds * rate)
    first = int(start * rate)
    return [
        0.0 if i < first else amplitude * math.sin(2 * math.pi * 220 * i / rate)
        for i in range(total)
    ]


def write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path
