# GRport runtime source

GRport's runtime (`runtime/GRport-runtime.exe` in the release) is a modified version of the GPL
Windows PS4 runtime by Supermedo, built on shadPS4's renderer. Its full source is that
project's version 1.9.2 plus `grport-runtime.patch`:

```sh
git clone --recursive https://github.com/Supermedo/bloodborne_pc grport-runtime
cd grport-runtime
git checkout de2e38af055f09f819946951075c6bb119e62ae6   # Version 1.9.2
git submodule update --init --recursive
git apply --binary ../grport-runtime.patch
```

Build on Windows with MSYS2 (CLANG64 environment): `bash build.sh`, which writes
`out/bb-probe.exe` (the release names it `GRport-runtime.exe`). The patch adds, among other
things: Gravity Rush support (event flags, fibers, fonts), GRport's own libSceNgs2 audio mixer
(`src/runtime_ngs2.c`), save data dialogs, FSR 4 / DLSS anti-aliasing for Gravity Rush
(`vk_temporal_upscaler.cpp`, `vk_camera_motion.cpp`, `host_shaders/gr_motion.comp`), patch
loading with code caves (`src/probe.c`) and the in-game menu (`gpu/shim/bbport_overlay.cpp`).

The FSR 4 model files are not part of this source; they ship only in the FSR edition release
zip, with their license.

License: GPL-2.0-or-later, as the original runtime (see `LICENSE` in the repository root and
the `licenses` folder of the release zips for the bundled libraries).
