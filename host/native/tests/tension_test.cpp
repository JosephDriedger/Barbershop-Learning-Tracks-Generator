// Test of BLT's build of worldline's tension effect (see docs/worldline-provenance.md).
//
// The effect is not part of BLT's build: GetTensionCoefficients returns the neutral envelope. BLT only ever
// asks for tension 0 (the supported render path passes 0 on every call, measured over the whole
// integration suite with host/native/trace_tension.ps1), and for 0 the original returns exactly 1.0 as well.
// This test compiles the product effects.cpp (upstream + effects-no-tension-spline.patch) on its own and
// checks, over a grid of widths, sample rates, pitches and tension values, that
//   * the result has `width` elements, and
//   * every element is exactly 1.0 (not 1 - 1e-16, not -0).
// It does not, and cannot, compare against the original spline: that is deliberate, the original is not here.
#include <cmath>
#include <cstdio>
#include <vector>

#include "worldline/model/effects.h"

int main() {
  const int widths[] = {0, 1, 2, 3, 129, 257, 513, 1025, 2049, 4097};
  const int rates[] = {8000, 22050, 44100, 48000, 96000};
  const int values[] = {-100, -99, -50, -20, -1, 0, 1, 7, 20, 50, 99, 100};
  const double pitches[] = {0.0, 1.0, 49.9, 50.0, 65.4, 110.0, 220.0, 440.0, 880.0, 1000.0, 2000.0, 20000.0, 1e9};
  long calls = 0, values_checked = 0, failures = 0;
  for (int w : widths)
    for (int fs : rates)
      for (int v : values)
        for (double f0 : pitches) {
          std::vector<double> r = worldline::GetTensionCoefficients(f0, fs, v, w);
          ++calls;
          if (r.size() != static_cast<size_t>(w)) {
            ++failures;
            std::printf("FAIL: width %d gave %zu elements\n", w, r.size());
            continue;
          }
          for (double d : r) {
            ++values_checked;
            if (d != 1.0 || std::signbit(d)) {
              ++failures;
              std::printf("FAIL: f0 %g fs %d value %d width %d gave %.17g\n", f0, fs, v, w, d);
              break;
            }
          }
        }
  std::printf("tension effect: %ld calls, %ld values, %ld failures\n", calls, values_checked, failures);
  return failures ? 1 : 0;
}
