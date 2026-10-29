#!/usr/bin/env bash
# Usage: build.sh [dest]   Builds dist/GRport.exe with PyInstaller and copies it to dest
# (default ../GRport).
set -euo pipefail
cd "$(dirname "$0")"
dest=${1:-../GRport}
python tools/make_icons.py
python -m PyInstaller --noconfirm --onefile --windowed --name GRport --icon assets/grport.ico \
    --exclude-module numpy --add-data "assets;assets" \
    --distpath dist --workpath build grport/__main__.py
mkdir -p "$dest"
cp dist/GRport.exe "$dest/GRport.exe"
ls -l "$dest/GRport.exe"
