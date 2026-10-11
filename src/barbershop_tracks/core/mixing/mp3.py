"""MP3 output through an external FFmpeg, validated before it is allowed into a package.

FFmpeg is never bundled and is not needed for WAV output. The user (eventually, the settings
dialog) points BLT at an executable; ``find_ffmpeg`` also checks ``BLT_FFMPEG`` and ``PATH``.

Encoding settings (recorded in the manifest, never the executable's path):

* ``libmp3lame``, variable bit rate, quality ``-q:a 2`` (about 190 kbit/s) by default, mono,
  44.1 kHz, metadata stripped, bit-exact flags so the same input gives the same bytes with the same
  FFmpeg build.
* **Timing is not sample-exact.** An MP3 stream starts with encoder delay and ends with padding to
  a whole frame (1152 samples). Players that read the Xing/LAME gapless data trim most of it; others
  do not. The MP3 is a convenience copy; the WAV is the timing reference.

Validation after every encode: the file is walked frame by frame in Python (MPEG-1 Layer III,
44.1 kHz, mono, every frame header valid and the frames exactly filling the file), its length must
be within three frames of the expected length, and, because FFmpeg is at hand, a full decode must
succeed without a warning and produce a length within the same tolerance.
"""

import os
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from barbershop_tracks.core.mixing.errors import (
    MixCancelledError,
    MixConfigurationError,
    MixEncodingError,
)
from barbershop_tracks.core.rendering.cancel import CancelToken
from barbershop_tracks.core.rendering.process import OwnedProcess

SAMPLES_PER_FRAME = 1152
TOLERANCE_FRAMES = 3  # MP3 frames of difference allowed against the expected length
_BITRATES = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)


def find_ffmpeg(configured: Path | None = None) -> Path | None:
    """An explicit path, else ``BLT_FFMPEG``, else ``ffmpeg`` on ``PATH``; ``None`` if absent."""
    for candidate in (configured, os.environ.get("BLT_FFMPEG")):
        if candidate:
            path = Path(candidate)
            return path if path.is_file() else None
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


@dataclass(frozen=True, slots=True)
class Mp3Info:
    audio_frames: int
    average_kbps: float


def inspect_mp3(path: Path) -> Mp3Info:
    """Walk the MP3 and return its frame count; raises ``MixEncodingError`` if it is not clean."""
    try:
        data = path.read_bytes()
    except OSError as error:
        raise MixEncodingError("MIX_MP3_UNREADABLE", f"cannot read {path.name}: {error}") from error
    position = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
        position = 10 + size
    end = len(data)
    if end >= 128 and data[end - 128 : end - 125] == b"TAG":
        end -= 128
    audio = 0
    kbps_total = 0
    first = True
    while position < end:
        if end - position < 4:
            raise MixEncodingError("MIX_MP3_INVALID", f"{path.name}: trailing bytes at {position}")
        header = data[position : position + 4]
        if header[0] != 0xFF or (header[1] & 0xE0) != 0xE0:
            raise MixEncodingError("MIX_MP3_INVALID", f"{path.name}: lost frame sync at {position}")
        version, layer = (header[1] >> 3) & 3, (header[1] >> 1) & 3
        bitrate_index, rate_index = header[2] >> 4, (header[2] >> 2) & 3
        padding, mode = (header[2] >> 1) & 1, header[3] >> 6
        if version != 3 or layer != 1 or not 0 < bitrate_index < 15 or rate_index != 0:
            raise MixEncodingError(
                "MIX_MP3_INVALID",
                f"{path.name}: frame at {position} is not MPEG-1 Layer III 44.1 kHz",
            )
        if mode != 3:
            raise MixEncodingError("MIX_MP3_INVALID", f"{path.name}: not a mono stream")
        kbps = _BITRATES[bitrate_index]
        length = 144 * kbps * 1000 // 44100 + padding
        if position + length > end:
            raise MixEncodingError("MIX_MP3_INVALID", f"{path.name}: the last frame is cut off")
        body = data[position + 4 : position + length]
        is_info_frame = first and (
            body[17:21] in (b"Xing", b"Info") or body[:4] in (b"Xing", b"Info")
        )
        if not is_info_frame:
            audio += 1
            kbps_total += kbps
        first = False
        position += length
    if audio == 0:
        raise MixEncodingError("MIX_MP3_INVALID", f"{path.name}: no audio frames")
    return Mp3Info(audio, kbps_total / audio)


class FfmpegMp3Encoder:
    """Implements ``package.Mp3Encoder`` with a configurable FFmpeg command."""

    def __init__(
        self,
        command: Sequence[str | Path],
        *,
        quality: int = 2,
        timeout_seconds: float = 300.0,
        poll_seconds: float = 0.05,
    ) -> None:
        if not 0 <= quality <= 9:
            raise MixConfigurationError("MIX_MP3_QUALITY", "the LAME VBR quality must be 0 to 9")
        self.command = [str(part) for part in command]
        self.quality = quality
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self._version = self._probe()

    # --- configuration ---------------------------------------------------------------------

    def _run(self, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(
                [*self.command, *args],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise MixConfigurationError(
                "MIX_FFMPEG_UNUSABLE", f"FFmpeg could not be run: {error}"
            ) from error

    def _probe(self) -> str:
        version = self._run("-hide_banner", "-version")
        if version.returncode != 0:
            raise MixConfigurationError(
                "MIX_FFMPEG_UNUSABLE", f"FFmpeg -version exited with {version.returncode}"
            )
        first = version.stdout.decode("utf-8", errors="replace").splitlines()
        encoders = self._run("-hide_banner", "-encoders")
        if b"libmp3lame" not in encoders.stdout:
            raise MixConfigurationError(
                "MIX_FFMPEG_NO_MP3", "this FFmpeg build has no libmp3lame encoder"
            )
        return first[0].strip() if first else "unknown"

    def settings(self) -> dict[str, Any]:
        return {
            "encoder": "libmp3lame",
            "ffmpeg": self._version,
            "mode": "vbr",
            "quality": self.quality,
            "channels": 1,
            "sample_rate": 44100,
            "metadata": "stripped",
            "bitexact": True,
            "timing": "not sample-exact (encoder delay, padding); the WAV is the timing reference",
        }

    # --- encoding --------------------------------------------------------------------------

    def encode(
        self, wav: Path, mp3: Path, *, expected_frames: int, cancel: CancelToken
    ) -> dict[str, Any]:
        arguments = [
            *self.command,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(wav),
            "-vn",
            "-map_metadata",
            "-1",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            str(self.quality),
            "-id3v2_version",
            "0",
            "-fflags",
            "+bitexact",
            "-flags:a",
            "+bitexact",
            str(mp3),
        ]
        try:
            owned = OwnedProcess(arguments)
        except OSError as error:
            raise MixEncodingError("MIX_MP3_LAUNCH", f"cannot start FFmpeg: {error}") from error
        deadline = time.monotonic() + self.timeout_seconds
        try:
            while owned.poll() is None:
                if cancel.cancelled:
                    owned.terminate_tree()
                    owned.finish()
                    mp3.unlink(missing_ok=True)
                    raise MixCancelledError("MIX_CANCELLED", "cancelled during MP3 encoding")
                if time.monotonic() > deadline:
                    owned.terminate_tree()
                    owned.finish()
                    mp3.unlink(missing_ok=True)
                    raise MixEncodingError(
                        "MIX_MP3_TIMEOUT", f"FFmpeg took longer than {self.timeout_seconds:g} s"
                    )
                time.sleep(self.poll_seconds)
            code = owned.finish()
        except BaseException:
            owned.terminate_tree()
            owned.finish()
            raise
        if code != 0:
            mp3.unlink(missing_ok=True)
            raise MixEncodingError(
                "MIX_MP3_FAILED",
                f"FFmpeg exited with {code} for {wav.name}: {owned.stderr_text.strip()[-500:]}",
                {"exit_code": code},
            )
        return self._validate(mp3, expected_frames)

    def _validate(self, mp3: Path, expected_frames: int) -> dict[str, Any]:
        if not mp3.is_file() or mp3.stat().st_size == 0:
            raise MixEncodingError("MIX_MP3_EMPTY", f"{mp3.name} was not produced or is empty")
        info = inspect_mp3(mp3)
        estimate = info.audio_frames * SAMPLES_PER_FRAME
        if abs(estimate - expected_frames) > TOLERANCE_FRAMES * SAMPLES_PER_FRAME:
            raise MixEncodingError(
                "MIX_MP3_LENGTH",
                f"{mp3.name} holds about {estimate} samples; expected {expected_frames} "
                f"(allowed difference {TOLERANCE_FRAMES} frames)",
            )
        decoded = self._run(
            "-v", "error", "-nostdin", "-i", str(mp3), "-f", "s16le", "-ac", "1", "-", timeout=120
        )
        if decoded.returncode != 0 or decoded.stderr.strip():
            raise MixEncodingError(
                "MIX_MP3_DECODE",
                f"{mp3.name} did not decode cleanly: "
                f"{decoded.stderr.decode(errors='replace')[:300]}",
            )
        samples = len(decoded.stdout) // 2
        if abs(samples - expected_frames) > TOLERANCE_FRAMES * SAMPLES_PER_FRAME:
            raise MixEncodingError(
                "MIX_MP3_LENGTH",
                f"{mp3.name} decodes to {samples} samples; expected about {expected_frames}",
            )
        return {
            "mp3_audio_frames": info.audio_frames,
            "average_kbps": round(info.average_kbps, 1),
            "decoded_samples": samples,
            "decoded_minus_wav_samples": samples - expected_frames,
        }
