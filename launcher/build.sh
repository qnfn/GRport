#!/usr/bin/env bash
# Usage: build.sh [dest]   Builds dist/GRport.exe with PyInstaller and copies it to dest
# (default ../GRport).
set -euo pipefail
cd "$(dirname "$0")"
dest=${1:-../GRport}
python tools/make_icons.py
# The version stamp of the unpacked files (grport/__main__.py: _restart_if_borrowed).
python -c "from grport import __version__; open('assets/version.txt', 'w').write(__version__)"
python -m PyInstaller --noconfirm --onefile --windowed --name GRport --icon assets/grport.ico \
    --exclude-module numpy --add-data "assets;assets" \
    --distpath dist --workpath build grport/__main__.py
mkdir -p "$dest"
cp dist/GRport.exe "$dest/GRport.exe"
ls -l "$dest/GRport.exe"
