#!/usr/bin/env bash
# Build the BLT render host against the PINNED OpenUtau source on macOS. The counterpart of host/build.ps1,
# which documents the pin, the patch and the two host configurations (read it first).
#
#   host/build.sh [--openutau-src DIR] [--out DIR] [--publish] [--rid osx-arm64|osx-x64]
#                 [--skip-native] [--include-g2p-model]
#
# Without --publish: the framework-dependent development build (research-output/host/build). With it: the
# shipped form, self-contained for the RID of this Mac (the default follows `uname -m`), pruned with
# host/prune.txt (research-output/host/publish). The native resampler is BLT's own build
# (host/native/build.sh: the same sources without any spline) unless --skip-native, which keeps OpenUtau's
# stock universal libworldline.dylib for quick local runs only (never for a package).
# The OpenUtau tag, commit and the bundled .NET runtime version are read from host/build.ps1, so that
# there is one place to change them. Needs a .NET 8 SDK (DOTNET_ROOT, or `dotnet` on PATH), git, Python 3.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
python="${BLT_PYTHON:-python3}"

openutau_src=""
out=""
publish=0
rid=""
skip_native=0
include_g2p=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --openutau-src) openutau_src="$2"; shift 2 ;;
        --out) out="$2"; shift 2 ;;
        --publish) publish=1; shift ;;
        --rid) rid="$2"; shift 2 ;;
        --skip-native) skip_native=1; shift ;;
        --include-g2p-model) include_g2p=1; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

pin() { sed -n "s/^\\\$$1 = \"\\([^\"]*\\)\".*/\\1/p" "$here/build.ps1" | head -n 1; }
tag="$(pin Tag)"
commit="$(pin Commit)"
runtime_version="$(pin RuntimeVersion)"
if [ -z "$tag" ] || [ -z "$commit" ] || [ -z "$runtime_version" ]; then
    echo "could not read the pins from host/build.ps1" >&2
    exit 1
fi
build_commit="$commit+blt-patched"

if [ -z "$rid" ]; then
    case "$(uname -m)" in
        arm64) rid="osx-arm64" ;;
        x86_64) rid="osx-x64" ;;
        *) echo "unsupported machine: $(uname -m)" >&2; exit 1 ;;
    esac
fi
suffix=""
if [ "$include_g2p" = 1 ]; then suffix="-g2p-research"; fi
[ -n "$openutau_src" ] || openutau_src="$root/research-output/openutau-src"
if [ -z "$out" ]; then
    if [ "$publish" = 1 ]; then out="$root/research-output/host/publish$suffix"; else out="$root/research-output/host/build$suffix"; fi
fi

if [ ! -f "$openutau_src/OpenUtau.sln" ]; then
    git clone --branch "$tag" --depth 1 https://github.com/stakira/OpenUtau.git "$openutau_src"
fi
openutau_src="$(cd "$openutau_src" && pwd)"
head="$(git -C "$openutau_src" rev-parse HEAD)"
if [ "$head" != "$commit" ]; then
    echo "OpenUtau source is at $head, expected the pinned $commit" >&2
    exit 1
fi

if [ -n "${DOTNET_ROOT:-}" ]; then export PATH="$DOTNET_ROOT:$PATH"; fi
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1

patched="$root/research-output/host/openutau-patched$suffix"
rm -rf "$patched"
mkdir -p "$(dirname "$patched")"
patch_args=("$openutau_src" "$patched")
if [ "$include_g2p" = 0 ]; then patch_args+=(--exclude-g2p-model); fi
"$python" "$here/patch_openutau.py" "${patch_args[@]}"
# the one change that exists for macOS only (see the file): the same pitch-curve count on every processor
"$python" "$here/patch_macos.py" "$patched"

mkdir -p "$out"
out="$(cd "$out" && pwd)"
project="$here/BltRenderHost/BltRenderHost.csproj"
if [ "$publish" = 1 ]; then
    rm -rf "$out"
    log="$out.publish.log"
    if ! dotnet publish "$project" -c Release -r "$rid" --self-contained true -o "$out"         "-p:OpenUtauSrc=$patched" "-p:OpenUtauCommit=$build_commit" -p:DebugType=none -p:DebugSymbols=false         "-p:RuntimeFrameworkVersion=$runtime_version" >"$log" 2>&1; then
        tail -n 60 "$log"
        echo "publish failed" >&2
        exit 1
    fi
    grep -E "error|Build succeeded|Elapsed" "$log" || true
    while IFS= read -r line; do
        name="$(printf '%s' "$line" | tr -d '\r' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        case "$name" in "" | "#"*) continue ;; esac
        rm -f "$out/$name"
    done <"$here/prune.txt"
    if [ "$include_g2p" = 0 ]; then
        # nothing runs a neural model any more: the native runtime (and its third-party notices) is not shipped
        rm -f "$out/libonnxruntime.dylib" "$out/onnxruntime.dylib"
    fi
    # DryWetMidi's native library for Windows, which the macOS publish also copies (the host never reads MIDI)
    rm -f "$out/Melanchall_DryWetMidi_Native64.dll"
else
    log="$out.build.log"
    if ! dotnet build "$project" -c Release -o "$out" "-p:OpenUtauSrc=$patched" "-p:OpenUtauCommit=$build_commit"         >"$log" 2>&1; then
        tail -n 60 "$log"
        echo "build failed" >&2
        exit 1
    fi
    grep -E "error|warn.*BltRenderHost|Build succeeded|Elapsed" "$log" || true
fi
if [ ! -x "$out/blt-render-host" ]; then echo "no host produced in $out" >&2; exit 1; fi

native="stock (OpenUtau's prebuilt universal library: contains GPL tk::spline; not for packages)"
if [ "$skip_native" = 0 ]; then
    native_out="$root/research-output/host/native-out"
    "$here/native/build.sh" "$openutau_src" "$native_out"
    cp -f "$native_out/libworldline.dylib" "$out/libworldline.dylib"
    native="BLT build without any spline"
fi

g2p="excluded"
distribution="proposed release configuration (model-free); not for release until the release gate is open"
if [ "$include_g2p" = 1 ]; then
    g2p="included"
    distribution="INTERNAL RESEARCH ONLY: contains the g2p model of unknown provenance; never distribute"
fi
BLT_INFO_OUT="$out/blt-host-build.json" BLT_INFO_TAG="$tag" BLT_INFO_COMMIT="$commit" BLT_INFO_NATIVE="$native" \
    BLT_INFO_RUNTIME="$runtime_version" BLT_INFO_G2P="$g2p" BLT_INFO_DISTRIBUTION="$distribution" BLT_INFO_RID="$rid" \
    BLT_INFO_DYLIB="$out/libworldline.dylib" "$python" - <<'PYEOF'
import hashlib
import json
import os
from pathlib import Path

env = os.environ
native = env["BLT_INFO_NATIVE"]
info = {
    "schema": "blt.host-build/1",
    "openutau": {
        "tag": env["BLT_INFO_TAG"],
        "commit": env["BLT_INFO_COMMIT"],
        "patched": True,
        "patch_script": "host/patch_openutau.py",
    },
    "worldline": native,
    "worldline_spline_free": native.startswith("BLT build"),
    "worldline_sha256": hashlib.sha256(Path(env["BLT_INFO_DYLIB"]).read_bytes()).hexdigest(),
    "dotnet_runtime": env["BLT_INFO_RUNTIME"],
    "runtime_identifier": env["BLT_INFO_RID"],
    "g2p_model": env["BLT_INFO_G2P"],
    "distribution": env["BLT_INFO_DISTRIBUTION"],
}
Path(env["BLT_INFO_OUT"]).write_text(json.dumps(info, indent=4) + "\n", encoding="utf-8")
PYEOF
echo "host: $out/blt-render-host"
