# GRport

One launcher for **Gravity Rush Remastered** and **Gravity Rush 2** (USA and Europe) on
GRport's own native runtime. Yellow and black, built from the DCport launcher.

- PLAY: both games side by side, found next to GRport or chosen by folder; region and version
  read from the game's param.sfo. The first PLAY prepares the game for the runtime (about a
  minute) into `data/<game>`; saves and settings go to `user/<game>`.
- SETUP, per game: fullscreen or window, window size, GPU readbacks. Graphics, upscaler and
  frame rate are set in the game, in GRport's in-game menu (Insert, or L3+R3 on a controller).
- LOG: the last run's log, live while it runs, with a bug report copy.

No game files are included: the games come from the player's own console.

Develop: `python -m pytest`, run with `GRPORT_ROOT=<folder> python -m grport`.
Build: `bash build.sh [dest]` (PyInstaller; icons from `tools/make_icons.py`).
