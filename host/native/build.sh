#!/usr/bin/env bash
# Build BLT's own libworldline.dylib (OpenUtau's native resampler) from the pinned sources, without any
# spline, and check it. The macOS counterpart of host/native/build.ps1; see docs/worldline-provenance.md.
#
#   host/native/build.sh OPENUTAU_SRC OUT_DIR [WORK_DIR]
#
# Steps: prepare the pinned third-party sources (SHA-256 checked) and BLT's patch (prepare.py); build with
# clang and CMake for THIS machine's architecture (arm64 or x86_64; each is built on a Mac of its own kind);
# check that neither the link map nor the library mentions a spline and that the exports are the ones
# OpenUtau.Core calls (verify_dylib.py); run the native test of the tension effect (the neutral envelope).
# Needs the Xcode command line tools (clang, nm, otool), CMake, git and Python 3; Ninja is used when present.
set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "usage: $0 OPENUTAU_SRC OUT_DIR [WORK_DIR]" >&2
    exit 2
fi
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
openutau_src="$1"
out="$2"
work="${3:-$root/research-output/host/native-work}"
python="${BLT_PYTHON:-python3}"

rm -rf "$work"
"$python" "$here/prepare.py" "$work" --openutau-src "$openutau_src"

generator=()
if command -v ninja >/dev/null 2>&1; then generator=(-G Ninja); fi
arch="$(uname -m)"
cmake -S "$work" -B "$work/build" "${generator[@]}" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_OSX_ARCHITECTURES="$arch" >"$work/configure.log" 2>&1 || { cat "$work/configure.log"; exit 1; }
cmake --build "$work/build" --target worldline >"$work/build.log" 2>&1 || { tail -n 80 "$work/build.log"; exit 1; }

library="$work/build/libworldline.dylib"
"$python" "$here/verify_dylib.py" "$library" "$work/build/worldline.map"

# the tension effect: the product's effects.cpp compiled on its own and run over a grid of inputs
tests="$work/tests"
mkdir -p "$tests"
cp "$here/tests/tension_test.cpp" "$tests/"
wl="$work/worldline-src/cpp"
clang++ -O2 -std=c++17 -DNOMINMAX -I"$wl" -I"$wl/worldline/model" "$tests/tension_test.cpp" \
    "$work/patched/worldline/model/effects.cpp" -o "$tests/tension_test" >"$tests/tension.log" 2>&1 \
    || { cat "$tests/tension.log"; exit 1; }
"$tests/tension_test"

mkdir -p "$out"
cp "$library" "$out/libworldline.dylib"
echo "libworldline.dylib ($arch): $out/libworldline.dylib sha256 $(shasum -a 256 "$out/libworldline.dylib" | cut -d' ' -f1)"
