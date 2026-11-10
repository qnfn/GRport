# SPDX-License-Identifier: GPL-2.0-or-later
"""Where GRport keeps its files: inside the folder GRport.exe sits in (Windows), or in
$GRPORT_HOME / ~/.local/share/GRport on Linux (the AppImage itself is read-only)."""
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    console_log: Path
    settings_json: Path

    @classmethod
    def for_root(cls, root: Path) -> "AppPaths":
        root = Path(root)
        return cls(
            root=root,
            console_log=root / "last_run.log",
            settings_json=root / "grport.json",
        )

    @classmethod
    def current(cls) -> "AppPaths":
        if os.environ.get("GRPORT_HOME"):
            root = Path(os.environ["GRPORT_HOME"])
        elif getattr(sys, "frozen", False):
            root = Path(sys.executable).parent
        elif os.environ.get("GRPORT_ROOT"):
            root = Path(os.environ["GRPORT_ROOT"])
        else:
            root = Path.cwd()
        return cls.for_root(root)
