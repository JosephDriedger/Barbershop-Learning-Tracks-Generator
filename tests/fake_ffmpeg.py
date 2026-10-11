"""A stand-in for ffmpeg: answers the few invocations the MP3 encoder makes.

``FAKE_FFMPEG_MODE`` selects a failure: fail, garbage, truncated, empty, hang, decode_fail, short,
no_lame, version_fail, noisy_decode.
"""

import math
import os
import struct
import sys
import time
from pathlib import Path

MODE = os.environ.get("FAKE_FFMPEG_MODE", "ok")
FRAME_BYTES = 417  # MPEG-1 Layer III, 128 kbit/s, 44.1 kHz, no padding


def wav_frames(path: Path) -> int:
    data = path.read_bytes()
    position = 12
    while position + 8 <= len(data):
        tag, size = data[position : position + 4], struct.unpack_from("<I", data, position + 4)[0]
        if tag == b"data":
            return int(size) // 2
        position += 8 + size + (size & 1)
    return 0


def mp3_for(frames: int) -> bytes:
    count = math.ceil((frames + 1105) / 1152)
    info = b"\xff\xfb\x90\xc0" + b"\x00" * 17 + b"Info" + b"\x00" * (FRAME_BYTES - 25)
    audio = (b"\xff\xfb\x90\xc0" + b"\x00" * (FRAME_BYTES - 4)) * count
    return info + audio


def main() -> None:
    args = sys.argv[1:]
    if "-version" in args:
        if MODE == "version_fail":
            sys.exit(3)
        print("ffmpeg version fake-1.0 Copyright (c) the tests")
        return
    if "-encoders" in args:
        print(" A....D libvorbis" if MODE == "no_lame" else " A....D libmp3lame  MP3")
        return
    if MODE == "hang":
        time.sleep(600)
    if "-f" in args and args[args.index("-f") + 1] == "s16le":  # decode check
        source = Path(args[args.index("-i") + 1])
        if MODE == "decode_fail":
            print("Header missing", file=sys.stderr)
            sys.exit(1)
        if MODE == "noisy_decode":
            print("[mp3float] Error while decoding", file=sys.stderr)
        frames = max(0, (len(source.read_bytes()) // FRAME_BYTES - 2) * 1152)
        sys.stdout.buffer.write(b"\x00\x00" * frames)
        return
    wav = Path(args[args.index("-i") + 1])
    out = Path(args[-1])
    frames = wav_frames(wav)
    if MODE == "fail":
        print("Conversion failed!", file=sys.stderr)
        sys.exit(1)
    data = mp3_for(frames if MODE != "short" else frames // 4)
    if MODE == "garbage":
        data = b"this is not an mp3 file"
    elif MODE == "truncated":
        data = data[:-100]
    elif MODE == "empty":
        data = b""
    out.write_bytes(data)


if __name__ == "__main__":
    main()
