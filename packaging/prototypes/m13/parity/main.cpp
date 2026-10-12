#include <cstdio>
#include <vector>
#include "worldline/model/effects.h"
int main() {
  int widths[] = {257, 513, 1025, 2049};
  int fss[] = {22050, 44100, 48000};
  int values[] = {-100, -50, -20, 0, 7, 20, 50, 100};
  double f0s[] = {49.9, 50, 65.4, 110, 220, 440, 880, 1000, 2000};
  for (int w : widths) for (int fs : fss) for (int v : values) for (double f0 : f0s) {
    std::vector<double> r = worldline::GetTensionCoefficients(f0, fs, v, w);
    std::printf("%d %d %d %.1f", w, fs, v, f0);
    for (double d : r) std::printf(" %.17g", d);
    std::printf("\n");
  }
}
