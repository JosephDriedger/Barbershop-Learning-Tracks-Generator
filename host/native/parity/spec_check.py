"""Check BLT's natural cubic spline against the mathematical definition.

    python host/native/parity/spec_check.py cases.txt

``cases.txt`` is the output of ``spec_test.cpp``. For every case this recomputes the expected values
independently of the C++ code and of tk::spline, from the definition alone:

* the natural cubic spline through (x_i, y_i) has second derivatives M_i with M_0 = M_{n-1} = 0
  and, for the inner knots,
  h_{i-1} M_{i-1} + 2 (h_{i-1} + h_i) M_i + h_i M_{i+1} = 6 (s_i - s_{i-1}),
  h_i = x_{i+1} - x_i, s_i = (y_{i+1} - y_i) / h_i; the system is solved here as a dense matrix with
  numpy.linalg.solve (the C++ uses the Thomas algorithm);
* inside [x_0, x_{n-1}] the value is the cubic on the interval that contains the point;
* outside, the curve continues as the tangent line of the end point (end second derivative 0);
* with one point the value is that point's y, with two points the straight line through them.

Tolerance: 1e-9 absolute plus 1e-9 relative (the cases have values of order 1 to 100).
"""

import sys
from pathlib import Path

import numpy as np

ABSOLUTE = 1e-9
RELATIVE = 1e-9


def second_derivatives(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    n = len(x)
    m = np.zeros(n)
    if n < 3:
        return m
    h = np.diff(x)
    s = np.diff(y) / h
    matrix = np.zeros((n - 2, n - 2))
    rhs = 6.0 * (s[1:] - s[:-1])
    for row in range(n - 2):
        matrix[row, row] = 2.0 * (h[row] + h[row + 1])
        if row > 0:
            matrix[row, row - 1] = h[row]
        if row < n - 3:
            matrix[row, row + 1] = h[row + 1]
    m[1:-1] = np.linalg.solve(matrix, rhs)
    return m


def expected(x: np.ndarray, y: np.ndarray, q: float) -> float:
    n = len(x)
    if n == 1:
        return float(y[0])
    m = second_derivatives(x, y)
    h = np.diff(x)
    s = np.diff(y) / h
    if n == 2:
        return float(y[0] + s[0] * (q - x[0]))
    if q <= x[0]:
        slope = s[0] - h[0] * (2.0 * m[0] + m[1]) / 6.0
        return float(y[0] + slope * (q - x[0]))
    if q >= x[-1]:
        slope = s[-1] + h[-1] * (m[-2] + 2.0 * m[-1]) / 6.0
        return float(y[-1] + slope * (q - x[-1]))
    i = int(np.searchsorted(x, q, side="right")) - 1
    t = q - x[i]
    b = s[i] - h[i] * (2.0 * m[i] + m[i + 1]) / 6.0
    return float(y[i] + t * (b + t * (m[i] / 2.0 + t * (m[i + 1] - m[i]) / (6.0 * h[i]))))


def main() -> int:
    lines = Path(sys.argv[1]).read_text().splitlines()
    worst = 0.0
    values = 0
    for number, line in enumerate(lines, start=1):
        fields = [float(t) for t in line.split()]
        n = int(fields[0])
        x = np.array(fields[1 : 1 + n])
        y = np.array(fields[1 + n : 1 + 2 * n])
        count = int(fields[1 + 2 * n])
        base = 2 + 2 * n
        queries = fields[base : base + count]
        results = fields[base + count : base + 2 * count]
        for q, got in zip(queries, results, strict=True):
            want = expected(x, y, q)
            error = abs(got - want)
            worst = max(worst, error / (ABSOLUTE + RELATIVE * abs(want)))
            values += 1
            if error > ABSOLUTE + RELATIVE * abs(want):
                print(
                    f"FAIL: case {number} (n={n}) at {q!r}: got {got!r}, definition says {want!r}"
                )
                return 1
    print(
        f"spline matches its mathematical definition: {len(lines)} cases, {values} values, "
        f"worst error {worst:.2g} of the tolerance"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
