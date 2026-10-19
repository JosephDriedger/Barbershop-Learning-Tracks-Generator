"""One more change to the patched OpenUtau copy, for the macOS host only.

    python host/patch_macos.py <the patched copy that host/patch_openutau.py wrote>

``OpenUtau.Classic.ResamplerItem`` sizes a note's pitch curve with ``(int)Math.Ceiling(x)`` where ``x`` can be
NaN or beyond the range of an ``int`` for some notes (seen with the synthetic voicebank when a pronunciation is
spelled out for a word). The result of that conversion is not defined by the language: on x64 (Windows and
Intel Macs) the processor gives ``int.MinValue``, ``Math.Max(.., 0)`` turns it into 0 and the note is rendered
without a pitch curve; on Apple silicon the .NET runtime saturates to ``int.MaxValue`` and the next line,
``new int[pitchCount]``, throws "Array dimensions exceeded supported range", which stopped the whole render.

The change makes every platform do what x64 always did: a count that is not a number, or out of range, is 0.
It touches that one line and nothing else, so the same score renders the same on all three platforms.
"""

import sys
from pathlib import Path

OLD = "int pitchCount = (int)Math.Ceiling(MusicMath.TempoMsToTick(tempo, pitchCountMs) / 5.0);"
NEW = (
    "double pitchCountRaw = Math.Ceiling(MusicMath.TempoMsToTick(tempo, pitchCountMs) / 5.0); "
    "int pitchCount = double.IsNaN(pitchCountRaw) || pitchCountRaw > int.MaxValue "
    "|| pitchCountRaw < int.MinValue ? 0 : (int)pitchCountRaw; // BLT: x64 semantics on every platform"
)


def main() -> int:
    path = Path(sys.argv[1]) / "OpenUtau.Core" / "Classic" / "ResamplerItem.cs"
    text = path.read_text(encoding="utf-8-sig")
    if text.count(OLD) != 1:
        raise SystemExit(f"{path}: the line to change is not there exactly once")
    path.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print(f"patched {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
