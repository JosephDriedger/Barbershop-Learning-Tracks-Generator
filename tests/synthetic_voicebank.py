"""A tiny generated UTAU voicebank for tests: sine "syllables", no real singer, nothing to licence.

It lets the render host run end to end without a user-installed voicebank. Only the aliases listed
in ``ALIASES`` exist; any other lyric is deliberately unsupported (OpenUtau then renders silence
without a host error, which is exactly the failure the stem validation must catch).
"""

import math
import struct
import wave
from pathlib import Path

SINGER_ID = "blt-synthetic"
ALIASES = ("la", "ba")
SAMPLE_RATE = 44100


def _sine(path: Path, frequency: float, seconds: float = 1.0) -> None:
    frames = int(SAMPLE_RATE * seconds)
    fade = int(SAMPLE_RATE * 0.02)
    samples = []
    for i in range(frames):
        envelope = min(1.0, i / fade, (frames - i) / fade)
        samples.append(int(12000 * envelope * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE)))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def build_voicebank(singers_dir: Path) -> Path:
    """Create ``<singers_dir>/blt-synthetic``; returns the singer folder."""
    folder = singers_dir / SINGER_ID
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "character.txt").write_text("name=BLT Synthetic\n", encoding="utf-8")
    lines = []
    for index, alias in enumerate(ALIASES):
        _sine(folder / f"{alias}.wav", 220.0 + 20 * index)
        lines.append(f"{alias}.wav={alias},0,200,-300,50,50")
    (folder / "oto.ini").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder
