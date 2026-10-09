"""A stand-in for blt-render-host used by the deterministic backend tests (run with Python).

It reads the same command line, reads the USTX the backend wrote, and writes one mono 16-bit
44.1 kHz WAV per voiced track with a sine burst inside every note. ``FAKE_HOST_MODE`` makes it
misbehave in specific, named ways; ``FAKE_HOST_DELAY`` slows it down.
"""

import json
import math
import os
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

RATE = 44100


def emit(**fields: object) -> None:
    print(json.dumps(fields), flush=True)


def finish(code: int, status: str, error: str | None = None) -> None:
    emit(event="result", status=status, exit_code=code, **({"error": error} if error else {}))
    sys.exit(code)


def wav_bytes(samples: list[int], rate: int = RATE, channels: int = 1) -> bytes:
    data = struct.pack(f"<{len(samples)}h", *samples)
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * 2 * channels, 2 * channels, 16)
    return header + b"data" + struct.pack("<I", len(data)) + data


def argument(name: str) -> str:
    return sys.argv[sys.argv.index(name) + 1]


def tracks_of(project: dict[str, Any]) -> dict[str, list[tuple[float, float]]]:
    """Track name -> note (start, end) seconds, from the first tempo only (enough for tests)."""
    ticks = project["resolution"]
    bpm = project["tempos"][0]["bpm"]

    def seconds(tick: float) -> float:
        return float(tick / ticks * 60.0 / bpm)

    names = [t["track_name"] for t in project["tracks"]]
    out: dict[str, list[tuple[float, float]]] = {name: [] for name in names}
    for part in project["voice_parts"]:
        for n in part["notes"]:
            out[names[part["track_no"]]].append(
                (seconds(n["position"]), seconds(n["position"] + n["duration"]))
            )
    return {name: notes for name, notes in out.items() if notes}


def render(
    notes: list[tuple[float, float]], *, drop_leading: bool = False, shift_early: bool = False
) -> list[int]:
    end = max(e for _, e in notes)
    samples = [0] * int(end * RATE)
    for start, stop in notes:
        for i in range(int(start * RATE), min(int(stop * RATE), len(samples))):
            samples[i] = int(9000 * math.sin(2 * math.pi * 220 * i / RATE))
    first = int(notes[0][0] * RATE)
    if drop_leading:
        samples = samples[first:]  # the leading silence is cut: the stem gets shorter
    if shift_early:
        samples = samples[first:] + [0] * first  # same length, but the audio starts too early
    return samples


def main() -> None:
    mode = os.environ.get("FAKE_HOST_MODE", "ok")
    emit(event="start", project=Path(argument("--project")).name)
    if "--singers-dir" in sys.argv and not Path(argument("--singers-dir")).is_dir():
        finish(8, "singers_dir_missing", argument("--singers-dir"))
    if mode.startswith("fail:"):
        _, code, status, message = mode.split(":", 3)
        finish(int(code), status, message)
    if mode == "crash":
        print("Unhandled exception: boom", file=sys.stderr)
        sys.exit(134)
    project = yaml.safe_load(Path(argument("--project")).read_text(encoding="utf-8"))
    out = Path(argument("--out"))
    base = argument("--base")
    emit(event="phase", name="init", elapsed_ms=1)
    time.sleep(float(os.environ.get("FAKE_HOST_DELAY", "0")))
    tracks = tracks_of(project)

    if mode == "hang":
        name = next(iter(tracks))
        (out / f"{base}_{name}.wav").write_bytes(wav_bytes(render(tracks[name]))[:5000])  # partial
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        pid_file = os.environ.get("FAKE_HOST_CHILD_PID_FILE")
        if pid_file:
            Path(pid_file).write_text(str(child.pid), encoding="utf-8")
        emit(event="progress", info="Exporting to partial file")
        time.sleep(600)
        sys.exit(0)

    for name, notes in tracks.items():
        data = render(
            notes, drop_leading=mode == "no_leading_silence", shift_early=mode == "shifted_early"
        )
        path = out / f"{base}_{name}.wav"
        if mode == "missing_wav" and name == "Tenor":
            continue
        if mode == "corrupt_wav" and name == "Tenor":
            path.write_bytes(b"this is not a wav file at all")
            continue
        if mode == "truncated_wav" and name == "Tenor":
            path.write_bytes(wav_bytes(data)[:-4000])  # the header claims more than is there
            continue
        if mode == "empty_wav" and name == "Tenor":
            path.write_bytes(wav_bytes([]))
            continue
        if mode == "silent_wav" and name == "Tenor":
            data = [0] * len(data)
        if mode == "silent_note" and name == "Tenor":
            start, stop = notes[1]
            for i in range(int(start * RATE), int(stop * RATE)):
                data[i] = 0
        if mode == "short_wav" and name == "Tenor":
            data = data[: len(data) // 2]
        if mode == "long_wav" and name == "Tenor":
            data = data + [0] * (RATE * 3)
        rate = 48000 if mode == "wrong_rate" and name == "Tenor" else RATE
        path.write_bytes(wav_bytes(data, rate))
        emit(event="progress", info=f"Exported to {path.name}")
    if mode == "extra_file":
        (out / "surprise.txt").write_text("unexpected", encoding="utf-8")
    emit(event="phase", name="render", elapsed_ms=2)
    finish(0, "ok")


if __name__ == "__main__":
    main()
