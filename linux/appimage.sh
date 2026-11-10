#!/usr/bin/env bash
# Usage: linux/appimage.sh <runtime tree> [dist]   (the runtime built with its build.sh first)
# Makes <dist>/GRport-x86_64.AppImage with nix-appimage (as bloodborne_pc's packaging/appimage.sh).
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
runtime=$(cd -- "$1" && pwd)
dist=$(mkdir -p "${2:-dist}" && cd -- "${2:-dist}" && pwd)
[[ -f $runtime/out/bb-probe && -f $runtime/out/gpu/libbbgpu.so ]] || { echo "Build the runtime first" >&2; exit 1; }
rm -rf "$here/build" && mkdir -p "$here/build/gpu"
install -m755 "$runtime/out/bb-probe" "$here/build/GRport-runtime"
install -m755 "$runtime/out/gpu/libbbgpu.so" "$here/build/gpu/libbbgpu.so"
{
    echo '['
    for elf in "$here/build/GRport-runtime" "$here/build/gpu/libbbgpu.so"; do
        readelf -d "$elf" | sed -n 's/.*\[\(.*\)\]/\1/p' | tr ':' '\n'
    done | grep -o '^/nix/store/[^/]*' | sort -u | grep -v -- '-nix-shell$' | sed 's/.*/  "&"/'
    echo ']'
} > "$here/runtime-paths.nix"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
(cd "$work" && nix bundle --impure --bundler github:ralismark/nix-appimage --expr "import $here {}")
install -m755 "$work"/*.AppImage "$dist/GRport-x86_64.AppImage"
ls -lh "$dist/GRport-x86_64.AppImage"
