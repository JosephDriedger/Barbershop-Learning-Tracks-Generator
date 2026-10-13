// Prints natural-cubic-spline cases for host/native/parity/spec_check.py to verify against the
// mathematical definition (a dense linear solve in NumPy). Contains no code of tk::spline and needs
// none: this is the test a reviewer can run without reading or building the GPL original.
//
// One line per case: n x_0..x_{n-1} y_0..y_{n-1} q q_0..q_{q-1} v_0..v_{q-1}
// (knots, values, number of query points, the query points, then the spline's value at each).
#include <cstdint>
#include <cstdio>
#include <vector>

#include "natural_spline.h"

namespace {
uint64_t state = 0x9E3779B97F4A7C15ull;
double Uniform() {  // xorshift64*, deterministic across platforms
  state ^= state >> 12;
  state ^= state << 25;
  state ^= state >> 27;
  return static_cast<double>((state * 0x2545F4914F6CDD1Dull) >> 11) / 9007199254740992.0;
}
}  // namespace

int main() {
  const int sizes[] = {1, 2, 3, 4, 5, 8, 13, 30, 100};
  for (int n : sizes) {
    for (int repeat = 0; repeat < 40; ++repeat) {
      std::vector<double> x(n), y(n);
      double position = Uniform() * 4.0 - 2.0;
      for (int i = 0; i < n; ++i) {
        x[i] = position;
        position += 0.05 + Uniform() * 3.0;  // strictly increasing, uneven spacing
        y[i] = Uniform() * 6.0 - 3.0;
      }
      blt::NaturalCubicSpline spline(x, y);
      std::vector<double> q;
      for (int i = 0; i < n; ++i) q.push_back(x[i]);  // every knot
      for (int i = 0; i + 1 < n; ++i) q.push_back(0.5 * (x[i] + x[i + 1]));
      for (int k = 0; k < 20; ++k) q.push_back(x.front() + (x.back() - x.front() + 2.0) * Uniform() - 1.0);
      q.push_back(x.front() - 5.0);  // outside on both sides: the linear continuation
      q.push_back(x.back() + 5.0);
      std::printf("%d", n);
      for (double v : x) std::printf(" %.17g", v);
      for (double v : y) std::printf(" %.17g", v);
      std::printf(" %d", static_cast<int>(q.size()));
      for (double v : q) std::printf(" %.17g", v);
      for (double v : q) std::printf(" %.17g", spline(v));
      std::printf("\n");
    }
  }
  return 0;
}
