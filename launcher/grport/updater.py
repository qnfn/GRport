# SPDX-License-Identifier: GPL-2.0-or-later
"""Updates from GRport's GitHub releases (v<version> tags of qnfn/GRport).

The launcher checks once per start (worker thread). When the player chooses to update, it
downloads the zip of its own edition (the FSR edition when runtime/fsr4_shaders exists),
checks it against GitHub's size and SHA-256, and swaps the program files in place: GRport.exe,
runtime/ and the README. The player's files stay: saves and settings (user/), grport.json,
the downloaded patches (patches/) and data/ (prepared again by itself, since the runtime
changed). The running launcher renames itself to GRport.exe.old (Windows allows renaming a
running exe); the next start deletes it.

Linux: the AppImage is one file, GRport-x86_64.AppImage on each release. The launcher downloads
it next to the running one, checks it the same way and moves it over the old file (Linux lets
a running file be replaced); the new one starts with the player's own environment.
"""
import hashlib
import json
import os
import re
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

REPO = "qnfn/GRport"
TAG_PREFIX = "v"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
USER_AGENT = "GRport-updater"
# Files of the zip that the player may have changed: kept when they exist.
KEEP_IF_PRESENT = frozenset({"grport.json", "user", "data", "patches"})
STAGE = ".update-new"   # the extracted release, next to the install (same drive)
OLD = ".update-old"     # replaced program files until the swap is complete
OLD_EXE = "GRport.exe.old"


def parse_version(text: str) -> "tuple[int, ...] | None":
    """'0.3.5' -> (0, 3, 5); a suffix ('0.3.5-test') or anything else -> None."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def _current(text: str) -> "tuple[tuple[int, ...], bool] | None":
    """The running version and whether it is a test build ('0.3.7-test' comes before 0.3.7)."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(-.+)?", text.strip())
    return (tuple(int(x) for x in m.groups()[:3]), bool(m.group(4))) if m else None


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    size: int
    sha256: str  # "" when GitHub gave no digest
    notes_url: str


APPIMAGE_ASSET = "GRport-x86_64.AppImage"


def asset_name(version: str, fsr: bool, appimage: bool = False) -> str:
    if appimage:
        return APPIMAGE_ASSET
    return f"GRport-{version}-windows{'-fsr' if fsr else ''}.zip"


def newest(releases: list, current: str, fsr: bool, appimage: bool = False) -> "Release | None":
    """The newest published release above `current` that has this edition's file (the
    Windows zip, or the AppImage on Linux)."""
    mine = _current(current)
    best = None
    for r in releases if isinstance(releases, list) else []:
        if not isinstance(r, dict) or r.get("draft") or r.get("prerelease"):
            continue
        tag = str(r.get("tag_name", ""))
        if not tag.startswith(TAG_PREFIX):
            continue
        version = tag[len(TAG_PREFIX):]
        parsed = parse_version(version)
        if parsed is None:
            continue
        if mine is not None and (parsed < mine[0] or (parsed == mine[0] and not mine[1])):
            continue  # older, or this very release (a test build gets its final release)
        if best is not None and parsed <= parse_version(best.version):
            continue
        for a in r.get("assets", []) or []:
            if isinstance(a, dict) and a.get("name") == asset_name(version, fsr, appimage):
                digest = str(a.get("digest") or "")
                best = Release(version, str(a.get("browser_download_url", "")),
                               int(a.get("size") or 0),
                               digest[7:].lower() if digest.startswith("sha256:") else "",
                               str(r.get("html_url", "")))
    return best if best and best.url.startswith("https://") else None


def check(current: str, fsr: bool, timeout: float = 10.0, appimage: bool = False) -> "Release | None":
    req = urllib.request.Request(API, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return newest(json.loads(resp.read().decode("utf-8")), current, fsr, appimage)


def download(release: Release, folder: Path, fsr: bool, progress=None,
             name: "str | None" = None) -> Path:
    """The release file in `folder` (checked against GitHub's size and SHA-256), saved as
    `name` (default: the edition's zip name)."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (name or asset_name(release.version, fsr))
    part = target.with_suffix(".part")
    digest = hashlib.sha256()
    done = 0
    req = urllib.request.Request(release.url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp, open(part, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, release.size)
    if release.size and done != release.size:
        part.unlink(missing_ok=True)
        raise ValueError(f"download incomplete ({done} of {release.size} bytes)")
    if release.sha256 and digest.hexdigest() != release.sha256:
        part.unlink(missing_ok=True)
        raise ValueError("download does not match the release's SHA-256")
    part.replace(target)
    return target


def _release_root(stage: Path) -> Path:
    """The zip's top folder (GRport-<version>-windows-fsr) or the stage itself."""
    entries = [p for p in stage.iterdir()]
    if len(entries) == 1 and entries[0].is_dir() and (entries[0] / "runtime").is_dir():
        return entries[0]
    return stage


def stage(zip_path: Path, root: Path, progress=None) -> Path:
    """Extracts the release next to the install; returns the folder holding its files.
    progress(done, total) gets the unpacked bytes after each file."""
    target = root / STAGE
    shutil.rmtree(target, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            parts = Path(name.replace("\\", "/")).parts
            if not parts or Path(name).is_absolute() or ".." in parts:
                raise ValueError(f"unsafe path in the update: {name}")
        members = z.infolist()
        total, done = sum(m.file_size for m in members), 0
        for member in members:
            z.extract(member, target)
            done += member.file_size
            if progress:
                progress(done, total)
    new = _release_root(target)
    if not (new / "GRport.exe").is_file() or not (new / "runtime" / "GRport-runtime.exe").is_file():
        raise ValueError("the update has no GRport.exe")
    return new


def install(new: Path, root: Path, running_exe: "Path | None") -> list[str]:
    """Moves the staged release over the install, keeping the player's files. A failure puts
    the old files back. Returns the top-level names it replaced."""
    old = root / OLD
    shutil.rmtree(old, ignore_errors=True)
    old.mkdir()
    moved: list[tuple[Path, Path]] = []  # (where the old one went, where it was)
    replaced = []
    try:
        for item in sorted(new.iterdir()):
            dest = root / item.name
            if item.name in KEEP_IF_PRESENT and dest.exists():
                continue
            if dest.exists():
                if running_exe is not None and dest.resolve() == running_exe.resolve():
                    aside = root / OLD_EXE
                    aside.unlink(missing_ok=True)
                else:
                    aside = old / item.name
                dest.rename(aside)
                moved.append((aside, dest))
            item.rename(dest)
            replaced.append(item.name)
    except OSError:
        for name in replaced:  # the new ones out again, the old ones back
            target = root / name
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
        for aside, dest in reversed(moved):
            aside.rename(dest)
        raise
    shutil.rmtree(old, ignore_errors=True)
    shutil.rmtree(root / STAGE, ignore_errors=True)
    return replaced


# Set by the AppImage's wrapper (linux/default.nix) for the copy that is running: the new one
# sets its own. Values pointing into the running image are dropped too (its mount goes away).
APPIMAGE_OWN = frozenset({
    "APPDIR", "APPIMAGE", "ARGV0", "OWD", "GRPORT_RUNTIME_EXE", "GRPORT_PREPARE_EXE",
    "BB_SYSTEM_FONT", "BB_BUNDLED_VK_DRIVER_FILES", "BB_VULKANINFO", "BB_DATA_DIR",
    "FONTCONFIG_FILE", "SSL_CERT_FILE", "PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH",
    "DISABLE_VK_LAYER_VALVE_steam_overlay_1", "DISABLE_VK_LAYER_VALVE_steam_fossilize_1",
})
_LIST_VARS = ("PATH", "XDG_DATA_DIRS", "XDG_CONFIG_DIRS")


def appimage_env(environ: dict) -> dict:
    """The environment to start a new AppImage from the running one with: the player's own
    (linux/entry.c kept their LD_PRELOAD... as BB_HOST_<name>), without the running image's."""
    inside = [p for p in (environ.get("APPDIR"), "/nix/store/") if p]
    out = {}
    for key, value in environ.items():
        if key in APPIMAGE_OWN or key.startswith("BB_HOST_"):
            continue
        if key in _LIST_VARS:
            kept = [p for p in value.split(":") if p and not any(i in p for i in inside)]
            if kept:
                out[key] = ":".join(kept)
            continue
        if any(i in value for i in inside):
            continue
        out[key] = value
    for key, value in environ.items():
        if key.startswith("BB_HOST_") and value:
            out[key[len("BB_HOST_"):]] = value
    if "PATH" not in out:
        out["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    return out


def install_appimage(release: Release, target: Path, progress=None) -> Path:
    """Downloads the release's AppImage next to `target` (the running one) and moves it over
    it; returns target. The old file stays until the new one is complete and checked."""
    target = Path(target)
    new = download(release, target.parent, False, progress, name=target.name + ".new")
    try:
        os.chmod(new, 0o755)
        os.replace(new, target)
    except OSError:
        new.unlink(missing_ok=True)
        raise
    return target


def clean_up(root: Path) -> None:
    """Leftovers of an earlier update (the old launcher exe once it is no longer running)."""
    for name in (OLD_EXE,):
        try:
            (root / name).unlink(missing_ok=True)
        except OSError:
            pass
    for name in (OLD, STAGE, "updates"):
        shutil.rmtree(root / name, ignore_errors=True)

def installed_fsr(root: Path) -> bool:
    """The FSR edition is installed (its zip carries runtime/fsr4_shaders)."""
    return (root / "runtime" / "fsr4_shaders").is_dir()
