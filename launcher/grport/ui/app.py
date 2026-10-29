# SPDX-License-Identifier: GPL-2.0-or-later
"""The GRport window: PLAY, SETUP and LOG for both games."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

from grport import __version__, games, patches, runtime, sysinfo, updater
from grport.paths import AppPaths
from grport.process import RUNNER
from grport.settings import load_settings, save_settings
from grport.ui import dialogs, theme
from grport.ui.home import HomePage
from grport.ui.log import LogPage
from grport.ui.setup import SetupPage

TABS = ("play", "setup", "log")
PAGES = {"play": HomePage, "setup": SetupPage, "log": LogPage}


def _lookup_gpu(results: "queue.Queue") -> None:
    try:
        results.put(("gpu", sysinfo.gpu_name()))
    except Exception:  # noqa: BLE001 - the GPU name is only a hint
        results.put(("gpu", None))


class App(tk.Tk):
    def __init__(self, paths: AppPaths):
        theme.enable_dpi_awareness()
        super().__init__(className="GRport")
        self.paths = paths
        self.settings = load_settings(paths)
        self.runner = RUNNER
        self.last_log: Path = paths.console_log
        self.gpu: "str | None" = None
        self.phase = "idle"       # idle | preparing | running
        self.playing: "str | None" = None  # the game key that is running
        self.infos: dict = {}     # game key -> games.GameFolder
        self.pages: dict = {}
        self.current: "str | None" = None
        self._after_ids: set = set()
        self._results: "queue.Queue" = queue.Queue()
        self._painted: list = []
        self._theme_hooks: list = []
        self.icon_images: list = []

        self.scale = theme.ui_scale(self)
        self.fonts = theme.make_fonts(self)
        self.title("GRport")
        self._set_icon()
        self._place_window()
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        theme.style_ttk(self.style, self.palette, self.fonts)
        self.configure(bg=self.palette["bg"])

        self.find_games()
        self._build_top()
        self.body = tk.Frame(self)
        self.paint(self.body, bg="bg")
        self.body.pack(fill="both", expand=True)
        self.body.rowconfigure(0, weight=1)
        self.body.columnconfigure(0, weight=1)
        self.body.grid_propagate(False)
        for name in TABS:
            self.pages[name] = PAGES[name](self.body, self)
        self.show("play")
        self.apply_theme()
        self.bind("<Map>", self._on_map, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=_lookup_gpu, args=(self._results,), daemon=True).start()
        self.update_release = None
        if getattr(sys, "frozen", False):  # updates replace the built launcher, not sources
            updater.clean_up(self.paths.root)
            threading.Thread(target=self._check_update, daemon=True).start()
        self.after(150, self._poll)

    def _check_update(self) -> None:
        try:
            release = updater.check(__version__, updater.installed_fsr(self.paths.root))
        except Exception:  # noqa: BLE001 - offline, rate limited: no update shown
            return
        if release is not None:
            self._results.put(("update", release))

    def install_update(self) -> None:
        """Downloads and installs the newer release, then starts the new launcher."""
        release = self.update_release
        if release is None or self.phase != "idle":
            return
        if not dialogs.confirm(self, f"Update to GRport {release.version}",
                               "GRport downloads the new version from GitHub and restarts. "
                               "Your saves, settings and games stay.", "Update"):
            return
        root = self.paths.root
        fsr = updater.installed_fsr(root)
        self.pages["play"].flash(f"Downloading GRport {release.version}...", "muted")

        def work():
            zip_path = updater.download(release, root / "updates", fsr)
            new = updater.stage(zip_path, root)
            return updater.install(new, root, Path(sys.executable))

        def done(_result, error):
            if error is not None:
                self.pages["play"].flash(f"The update failed: {error}", "bad")
                return
            subprocess.Popen([str(root / "GRport.exe")], cwd=str(root))
            self.destroy()
        self.run_task(work, done)

    # ------------------------------------------------------------ helpers

    @property
    def palette(self) -> dict:
        return theme.PALETTES[self.settings.theme]

    def px(self, n: float) -> int:
        return round(n * self.scale)

    def paint(self, widget: tk.Misc, **roles: str) -> None:
        """Colour a widget from the palette now and on every theme change."""
        self._painted.append((widget, roles))
        widget.configure(**{opt: self.palette[role] for opt, role in roles.items()})

    def on_theme(self, hook) -> None:
        """Call hook(palette) now and on every theme change."""
        self._theme_hooks.append(hook)
        hook(self.palette)

    def after(self, ms, func=None, *args):
        """Like Tk.after, but remembered so destroy() can cancel it."""
        if func is None:
            return super().after(ms)
        holder: list = []

        def run():
            self._after_ids.discard(holder[0])
            func(*args)

        aid = super().after(ms, run)
        holder.append(aid)
        self._after_ids.add(aid)
        return aid

    def after_cancel(self, aid) -> None:
        self._after_ids.discard(aid)
        super().after_cancel(aid)

    def destroy(self) -> None:
        for aid in list(self._after_ids):
            try:
                super().after_cancel(aid)
            except tk.TclError:
                pass
        self._after_ids.clear()
        super().destroy()

    def save_settings(self) -> bool:
        try:
            save_settings(self.paths, self.settings)
            return True
        except OSError:
            return False

    def run_task(self, fn, on_done) -> None:
        """Run fn() on a thread; on_done(result, error) runs on the Tk thread."""
        def work():
            try:
                self._results.put(("task", on_done, fn(), None))
            except Exception as e:  # noqa: BLE001 - reported to the page
                self._results.put(("task", on_done, None, e))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self) -> None:
        while True:
            try:
                item = self._results.get_nowait()
            except queue.Empty:
                break
            if item[0] == "gpu":
                self.gpu = item[1]
            elif item[0] == "update":
                self.update_release = item[1]
                self.pages["play"].show_update(item[1].version)
            elif item[0] == "task":
                _, on_done, result, error = item
                on_done(result, error)
        if self.phase == "preparing" and not self.runner.running():
            self._prepared()
        elif self.phase == "running" and not self.runner.running():
            self._finished()
        self.after(150, self._poll)

    # ------------------------------------------------------------ window

    def _set_icon(self) -> None:
        ico = theme.assets_dir() / "grport.ico"
        try:
            self.iconbitmap(default=str(ico))
        except tk.TclError:
            pass
        try:
            img = Image.open(theme.assets_dir() / "grport.png")
            for size in (16, 32, 48, 256):
                self.icon_images.append(ImageTk.PhotoImage(img.resize((size, size)), master=self))
            self.iconphoto(True, *self.icon_images)
        except (OSError, tk.TclError):
            pass

    def _place_window(self) -> None:
        w, h = self.px(1180), self.px(740)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(w, sw - 40), min(h, sh - 80)
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        self.minsize(self.px(900), self.px(600))

    def _build_top(self) -> None:
        top = tk.Frame(self)
        self.paint(top, bg="bg")
        top.pack(fill="x", padx=self.px(24), pady=(self.px(12), self.px(8)))

        self._logo = tk.Canvas(top, highlightthickness=0, bd=0)
        self.paint(self._logo, bg="bg")
        self._logo.pack(side="left", anchor="n", padx=(0, self.px(36)))
        self._logo_mark = None
        self.on_theme(self._draw_logo)

        drop = self.fonts["logo"].metrics("ascent") - self.fonts["tab"].metrics("ascent")
        self._tabs: dict = {}
        for name in TABS:
            cell = tk.Frame(top)
            self.paint(cell, bg="bg")
            cell.pack(side="left", anchor="n", padx=(0, self.px(26)),
                      pady=(max(0, drop) + self.px(4), 0))
            label = tk.Label(cell, text=name.upper(), font=self.fonts["tab"], cursor="hand2",
                             padx=self.px(2), pady=0, bd=0)
            self.paint(label, bg="bg")
            label.pack(side="top")
            bar = tk.Frame(cell, height=self.px(3))
            bar.pack(side="top", fill="x", pady=(self.px(2), 0))
            for w in (label, bar):
                w.bind("<Button-1>", lambda e, n=name: self.show(n))
            label.bind("<Enter>", lambda e, n=name: self._hover_tab(n, True))
            label.bind("<Leave>", lambda e, n=name: self._hover_tab(n, False))
            self._tabs[name] = (label, bar)
        self.on_theme(lambda pal: self._paint_tabs())

        switch = tk.Label(top, text="◐", font=self.fonts["symbol"], cursor="hand2",
                          padx=self.px(4))
        self.paint(switch, bg="bg", fg="text")
        switch.pack(side="right")
        switch.bind("<Button-1>", lambda e: self.toggle_theme())
        switch.bind("<Enter>", lambda e: switch.configure(fg=self.palette["accent"]))
        switch.bind("<Leave>", lambda e: switch.configure(fg=self.palette["text"]))
        version = theme.text_label(top, self, f"v{__version__}", font="small", fg="muted",
                                   bg="bg")
        version.pack(side="right", padx=(0, self.px(14)))

    def _draw_logo(self, pal: dict) -> None:
        c, font = self._logo, self.fonts["logo"]
        c.delete("all")
        size = font.metrics("linespace")
        try:
            mark = Image.open(theme.assets_dir() / "grport.png").resize((size, size),
                                                                       Image.LANCZOS)
            self._logo_mark = ImageTk.PhotoImage(mark, master=c)
            c.create_image(0, 0, anchor="nw", image=self._logo_mark)
            x = size + self.px(10)
        except OSError:
            x = 0
        c.create_text(x, 0, text="GR", anchor="nw", font=font, fill=pal["accent"])
        c.create_text(x + font.measure("GR"), 0, text="PORT", anchor="nw", font=font,
                      fill=pal["text"])
        c.configure(width=x + font.measure("GRPORT") + self.px(6), height=size)

    def _hover_tab(self, name: str, on: bool) -> None:
        if name != self.current:
            pal = self.palette
            self._tabs[name][0].configure(fg=theme.mix(pal["text"], pal["bg"], 0.85 if on else 0.6))

    def _paint_tabs(self) -> None:
        pal = self.palette
        for name, (label, bar) in self._tabs.items():
            active = name == self.current
            label.configure(fg=pal["text"] if active else theme.mix(pal["text"], pal["bg"], 0.6))
            bar.configure(bg=pal["accent"] if active else pal["bg"])

    def show(self, tab: str) -> None:
        if tab not in self.pages:
            raise ValueError(f"unknown tab: {tab}")
        if self.current and self.current != tab:
            old = self.pages[self.current]
            old.grid_remove()
            on_hide = getattr(old, "on_hide", None)
            if on_hide is not None:
                on_hide()
        self.pages[tab].grid(row=0, column=0, sticky="nsew")
        self.current = tab
        self._paint_tabs()
        on_show = getattr(self.pages[tab], "on_show", None)
        if on_show is not None:
            on_show()

    def toggle_theme(self) -> None:
        self.settings.theme = "light" if self.settings.theme == "dark" else "dark"
        self.save_settings()
        self.apply_theme()

    def apply_theme(self) -> None:
        pal = self.palette
        self.configure(bg=pal["bg"])
        theme.style_ttk(self.style, pal, self.fonts)
        alive = []
        for widget, roles in self._painted:
            try:
                widget.configure(**{opt: pal[role] for opt, role in roles.items()})
                alive.append((widget, roles))
            except tk.TclError:
                pass
        self._painted = alive
        hooks = []
        for hook in self._theme_hooks:
            try:
                hook(pal)
                hooks.append(hook)
            except tk.TclError:
                pass
        self._theme_hooks = hooks
        self._style_title_bar()

    def _style_title_bar(self) -> None:
        try:
            theme.style_title_bar(self, self.palette, self.settings.theme == "dark")
        except (OSError, tk.TclError):
            pass

    def _on_map(self, event) -> None:
        if event.widget is self:
            self._style_title_bar()

    # ------------------------------------------------------------ games

    def find_games(self) -> None:
        """Each game's folder: the saved one, else one found next to GRport."""
        found = None
        for key in games.GAMES:
            folder = self.settings.games[key].folder
            info = games.inspect(folder) if folder else None
            if info is None or info.game is None or info.game.key != key:
                if found is None:
                    found = {}
                    for base in (self.paths.root, self.paths.root.parent):
                        for k, v in games.find_games(base).items():
                            found.setdefault(k, v)
                info = found.get(key)
                if info is not None:
                    self.settings.games[key].folder = str(info.folder)
            if info is not None:
                self.infos[key] = info
            else:
                self.infos.pop(key, None)
        self.save_settings()

    def choose_folder(self, key: str) -> "str | None":
        """Ask for a game's folder; returns an error to show, or None."""
        game = games.GAMES[key]
        current = self.settings.games[key].folder
        initial = current if current and Path(current).is_dir() else str(self.paths.root.parent)
        chosen = filedialog.askdirectory(
            parent=self, initialdir=initial, mustexist=True,
            title=f"Choose your {game.title} folder (the one with eboot.bin)")
        if not chosen:
            return None
        info = games.inspect(chosen)
        if info.game is None:
            return info.problem
        if info.game.key != key:
            return f"That folder holds {info.game.title}, not {game.title}."
        self.settings.games[key].folder = str(info.folder)
        self.infos[key] = info
        self.save_settings()
        self.refresh_pages()
        return None

    def refresh_pages(self) -> None:
        for page in self.pages.values():
            refresh = getattr(page, "refresh", None)
            if refresh is not None:
                refresh()

    # ------------------------------------------------------------ playing

    def play(self, key: str) -> "str | None":
        """Start a game; returns an error to show, or None."""
        if self.phase != "idle":
            return "A game is already running."
        info = self.infos.get(key)
        if info is None:
            return "Choose the game folder first."
        if not info.ok:
            return info.problem
        self.settings.selected = key
        self.save_settings()
        return self._play_runtime(key, info)

    def _start(self, key, cmd, env, log, cwd, phase, shown_log) -> "str | None":
        log.parent.mkdir(parents=True, exist_ok=True)
        try:
            started = self.runner.start(cmd, env, log, cwd)
        except OSError as e:
            return f"Could not start {Path(cmd[0]).name}: {e.strerror or e}"
        if not started:
            return "A game is already running."
        self.phase, self.playing = phase, key
        self.last_log = shown_log
        self._phase_changed()
        return None

    def _play_runtime(self, key: str, info) -> "str | None":
        """GRport's runtime: prepare the game once (and after updates), then start it."""
        problem = runtime.missing(self.paths)
        if problem:
            return problem
        runtime.user_dir(self.paths, key).mkdir(parents=True, exist_ok=True)
        try:
            patch = patches.write(self.paths, self.settings, info)
        except (OSError, ValueError) as e:
            return (f"Could not get Gravity Rush 2's frame rate patches (they download from their "
                    f"author's GitHub on first use): {e}")
        if not runtime.is_prepared(self.paths, info, patch):
            runtime.data_dir(self.paths, key).mkdir(parents=True, exist_ok=True)
            return self._start(key, runtime.prepare_command(self.paths, info, patch), dict(os.environ),
                               runtime.prepare_log(self.paths, key), self.paths.root,
                               "preparing", runtime.prepare_log(self.paths, key))
        return self._start(key, runtime.command(self.paths, info, patch),
                           runtime.env(self.paths, self.settings, info),
                           self.paths.console_log, runtime.exe(self.paths).parent, "running",
                           self.paths.console_log)

    def _prepared(self) -> None:
        key = self.playing
        code = self.runner.exit_code()
        self.phase, self.playing = "idle", None
        info = self.infos.get(key) if key else None
        if code == 3 and info is not None and key == "gr2":
            # The frame rate patches do not fit this build of the game: it plays unpatched.
            patches.mark_mismatch(self.paths, info)
            error = self._play_runtime(key, info)
            self.pages["play"].flash(error or "The frame rate patches are made for another build "
                                     "of Gravity Rush 2: it runs at 30 FPS.", "bad" if error else "warn")
            if error:
                self._phase_changed()
            return
        patch = patches.patch_file(self.paths, key) if key == "gr2" else None
        if code == 0 and info is not None and runtime.is_prepared(
                self.paths, info, patch if patch and patch.is_file() else None):
            error = self._play_runtime(key, info)
            if error:
                self.pages["play"].flash(error, "bad")
                self._phase_changed()
            return
        self._phase_changed()
        self.pages["play"].flash("The game could not be prepared. See LOG for details.", "bad")

    def stop(self) -> None:
        if self.phase == "running":
            self.runner.stop()

    def _finished(self) -> None:
        self.phase, self.playing = "idle", None
        self._phase_changed()

    def _phase_changed(self) -> None:
        for page in self.pages.values():
            hook = getattr(page, "set_phase", None)
            if hook is not None:
                hook(self.phase)

    def _on_close(self) -> None:
        self.destroy()
