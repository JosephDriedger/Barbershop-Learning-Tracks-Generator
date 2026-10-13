"""Compare the tension curves of the original tk::spline build and BLT's replacement.

    python host/native/parity/compare.py original.txt blt.txt

Both files hold one case per line (width, sample rate, tension value, f0, then every curve value
at 17 significant digits). The replacement must agree to rounding (1e-12 absolute) everywhere and
return exactly 1.0 for tension 0, which is what BLT renders with.
"""

import sys
from pathlib import Path

TOLERANCE = 1e-12


def main() -> int:
    original = [line.split() for line in Path(sys.argv[1]).read_text().splitlines()]
    replacement = [line.split() for line in Path(sys.argv[2]).read_text().splitlines()]
    if len(original) != len(replacement) or not original:
        print(f"FAIL: {len(original)} cases against {len(replacement)}")
        return 1
    worst = 0.0
    values = identical = 0
    for a, b in zip(original, replacement, strict=True):
        if a[:4] != b[:4] or len(a) != len(b):
            print("FAIL: the cases do not line up")
            return 1
        for text_x, text_y in zip(a[4:], b[4:], strict=True):
            x, y = float(text_x), float(text_y)
            values += 1
            identical += x == y
            worst = max(worst, abs(x - y))
        if a[2] == "0" and any(float(v) != 1.0 for v in b[4:]):
            print(f"FAIL: tension 0 is not exactly 1.0 for case {b[:4]}")
            return 1
    print(
        f"spline parity: {len(original)} cases, {values} values, {identical} identical, "
        f"max |diff| {worst:.2e}"
    )
    if worst > TOLERANCE:
        print(f"FAIL: difference above {TOLERANCE}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
