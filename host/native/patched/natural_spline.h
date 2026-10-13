// Natural cubic spline interpolation, written from the textbook definition (second derivatives from
// the tridiagonal system, Thomas algorithm). Copyright 2026 Joseph Driedger. Licensed under the
// Apache License, Version 2.0.
//
// Replaces the GPL-licensed tk::spline for the one use in worldline's tension curve. Matches its
// default behaviour used there: classical C2 cubic spline, zero second derivative at both end points,
// strictly increasing x, and evaluation outside [x.front(), x.back()] continuing linearly with the end
// slope (the end second derivatives are zero).
#ifndef BLT_NATURAL_SPLINE_H_
#define BLT_NATURAL_SPLINE_H_

#include <algorithm>
#include <cstddef>
#include <vector>

namespace blt {

class NaturalCubicSpline {
 public:
  NaturalCubicSpline(const std::vector<double>& x, const std::vector<double>& y)
      : x_(x), y_(y) {
    const size_t n = x_.size();
    m_.assign(n, 0.0);
    if (n < 3) return;  // below three points the curve is a line (or a constant)
    // Solve for the second derivatives m_[1..n-2] (m_[0] = m_[n-1] = 0):
    //   h[i-1] m[i-1] + 2 (h[i-1] + h[i]) m[i] + h[i] m[i+1] = 6 (s[i] - s[i-1])
    std::vector<double> diag(n, 0.0), upper(n, 0.0), rhs(n, 0.0);
    for (size_t i = 1; i + 1 < n; ++i) {
      const double h0 = x_[i] - x_[i - 1];
      const double h1 = x_[i + 1] - x_[i];
      diag[i] = 2.0 * (h0 + h1);
      upper[i] = h1;
      rhs[i] = 6.0 * ((y_[i + 1] - y_[i]) / h1 - (y_[i] - y_[i - 1]) / h0);
    }
    // forward elimination
    for (size_t i = 2; i + 1 < n; ++i) {
      const double lower = x_[i] - x_[i - 1];
      const double factor = lower / diag[i - 1];
      diag[i] -= factor * upper[i - 1];
      rhs[i] -= factor * rhs[i - 1];
    }
    // back substitution
    for (size_t i = n - 2; i >= 1; --i) {
      m_[i] = (rhs[i] - upper[i] * m_[i + 1]) / diag[i];
      if (i == 1) break;
    }
  }

  double operator()(double x) const {
    const size_t n = x_.size();
    if (n == 0) return 0.0;
    if (n == 1) return y_[0];
    if (x <= x_.front()) return Segment(0, x);
    if (x >= x_.back()) return Segment(n - 2, x);
    // interval i with x_[i] <= x < x_[i+1]
    const size_t i =
        static_cast<size_t>(std::upper_bound(x_.begin(), x_.end(), x) - x_.begin()) - 1;
    return Segment(i, x);
  }

 private:
  // The cubic of interval i evaluated at x; outside the interval it is used only at the two ends,
  // where the curve is continued as the tangent line (the end second derivatives are zero).
  double Segment(size_t i, double x) const {
    const double h = x_[i + 1] - x_[i];
    const double slope = (y_[i + 1] - y_[i]) / h;
    if (x_.size() < 3) return y_[i] + slope * (x - x_[i]);
    const double b = slope - h * (2.0 * m_[i] + m_[i + 1]) / 6.0;
    const double c = m_[i] / 2.0;
    const double d = (m_[i + 1] - m_[i]) / (6.0 * h);
    const bool left = x < x_.front();
    const bool right = x > x_.back();
    if (left) {
      const double t = x - x_[0];
      return y_[0] + b * t;  // m_[0] = 0: linear continuation
    }
    if (right) {
      const size_t last = x_.size() - 1;
      const double t = x - x_[last];
      const double end_slope = slope + h * (m_[i] + 2.0 * m_[i + 1]) / 6.0;
      return y_[last] + end_slope * t;  // m_[last] = 0: linear continuation
    }
    const double t = x - x_[i];
    return y_[i] + t * (b + t * (c + t * d));
  }

  std::vector<double> x_, y_, m_;
};

}  // namespace blt

#endif  // BLT_NATURAL_SPLINE_H_
