# GRport for Linux: the runtime (built by bloodborne_pc's build.sh with runtime/grport-runtime.patch,
# copied to linux/build by appimage.sh), the launcher and gr-prepare from their Python sources, Mesa's
# Vulkan drivers and the host's NVIDIA driver (vulkan.py). `bash linux/appimage.sh` makes the
# AppImage. Adapted from bloodborne_pc's packaging/default.nix (Supermedo/deadinside28).
{ pkgs ? import <nixpkgs> { }
  # Store paths the prebuilt runtime loads libraries from (its RUNPATHs), written by appimage.sh.
, runtimePaths ? (if builtins.pathExists ./runtime-paths.nix then import ./runtime-paths.nix else [ ])
}:
let
  lib = pkgs.lib;
  root = ./..;
  keep = [ "launcher" "launcher/grport" "launcher/assets" "prepare" "linux" ];
  src = builtins.path {
    name = "grport-src";
    path = root;
    filter = path: type:
      let rel = lib.removePrefix (toString root + "/") (toString path);
      in !(lib.hasInfix "__pycache__" rel) && (builtins.elem rel keep
        || lib.hasPrefix "launcher/grport/" rel || lib.hasPrefix "launcher/assets/" rel
        || lib.hasPrefix "prepare/" rel || lib.hasPrefix "linux/" rel);
  };
  python = pkgs.python3.withPackages (ps: [ ps.tkinter ps.pillow ps.capstone ps.keystone-engine ]);
  icds = lib.concatMapStringsSep ":" (name: "${pkgs.mesa}/share/vulkan/icd.d/${name}")
    [ "radeon_icd.x86_64.json" "intel_icd.x86_64.json" ];
  fontsConf = pkgs.writeText "grport-fonts.conf" ''
    <?xml version="1.0"?>
    <!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
    <fontconfig>
      <dir>${pkgs.dejavu_fonts}/share/fonts</dir>
      <dir>/usr/share/fonts</dir>
      <dir>/usr/local/share/fonts</dir>
      <dir prefix="xdg">fonts</dir>
      <cachedir prefix="xdg">GRport/fontconfig</cachedir>
      <include ignore_missing="yes">${pkgs.fontconfig.out}/etc/fonts/conf.d</include>
    </fontconfig>
  '';
  home = ''export GRPORT_HOME=''${GRPORT_HOME:-''${XDG_DATA_HOME:-$HOME/.local/share}/GRport}; export BB_DATA_DIR=$GRPORT_HOME; mkdir -p "$GRPORT_HOME"'';
in
pkgs.stdenv.mkDerivation {
  pname = "grport";
  version = "0.2";
  inherit src;
  nativeBuildInputs = [ pkgs.makeShellWrapper ];
  buildInputs = map builtins.storePath runtimePaths;
  dontBuild = true;
  dontConfigure = true;
  stripDebugList = [ "share/grport/bin" ];
  # patchelf corrupts the non-PIE runtime's symbol versions; it finds libbbgpu.so through
  # $ORIGIN/gpu and its other libraries through the build's RUNPATH.
  dontPatchELF = true;
  installPhase = ''
    runHook preInstall
    d=$out/share/grport
    mkdir -p $d/launcher $d/bin/gpu $out/bin $out/libexec
    cp -r launcher/grport launcher/assets $d/launcher/
    cp -r prepare $d/prepare
    install -m644 linux/vulkan.py $d/vulkan.py
    install -m755 linux/build/GRport-runtime $d/bin/GRport-runtime
    install -m755 linux/build/gpu/libbbgpu.so $d/bin/gpu/libbbgpu.so
    runHook postInstall
  '';
  postFixup = ''
    d=$out/share/grport
    makeShellWrapper ${python}/bin/python3 $out/bin/gr-prepare --add-flags "$d/prepare/gr_prepare.py"
    makeShellWrapper ${python}/bin/python3 $out/libexec/grport \
      --add-flags "$d/vulkan.py ${python}/bin/python3 -m grport" \
      --prefix PYTHONPATH : $d/launcher \
      --set GRPORT_RUNTIME_EXE $d/bin/GRport-runtime \
      --set GRPORT_PREPARE_EXE $out/bin/gr-prepare \
      --set BB_SYSTEM_FONT ${pkgs.dejavu_fonts}/share/fonts/truetype/DejaVuSans.ttf \
      --set BB_BUNDLED_VK_DRIVER_FILES ${icds} \
      --set BB_VULKANINFO ${pkgs.vulkan-tools}/bin/vulkaninfo \
      --set-default FONTCONFIG_FILE ${fontsConf} \
      --set-default LC_ALL C.UTF-8 \
      --set-default SSL_CERT_FILE ${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt \
      --prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath [ pkgs.libglvnd pkgs.libx11 pkgs.libxext ]} \
      --prefix PATH : ${lib.makeBinPath [ pkgs.coreutils pkgs.pciutils ]} \
      --run '${home}'
    # A static entry clears Steam's LD_PRELOAD (overlay) and the like before anything dynamic runs.
    gcc -O2 -Wall -Werror -static -L${pkgs.glibc.static}/lib -DTARGET="\"$out/libexec/grport\"" \
      ${./entry.c} -o $out/bin/grport
  '';
  meta.mainProgram = "grport";
}
