# SPDX-License-Identifier: GPL-2.0-or-later
"""PLAY page: one card per game with its art, region, version and a PLAY button."""
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from grport import games, runtime
from grport.ui import theme

ART_HEIGHT = 240  # the least; the art takes whatever height the card has left


def _trim_bars(img: Image.Image) -> Image.Image:
    """Crop the black bars some games bake into their background picture."""
    mask = img.convert("L").point(lambda v: 255 if v > 18 else 0)
    box = mask.getbbox()
    if box is None:
        return img
    w, h = img.size
    l, t, r, b = box
    if (r - l) * (b - t) < 0.98 * w * h and (r - l) > w * 0.5 and (b - t) > h * 0.5:
        return img.crop(box)
    return img


class GameCard:
    """The pieces of one game's card on the board."""

    def __init__(self, page: "HomePage", body: tk.Frame, game: games.Game):
        app = page.app
        self.page, self.app, self.game = page, app, game
        self._photo = None
        self._art_source = None
        self._art_path = None
        self._badge = Image.open(theme.assets_dir() / game.badge).convert("RGBA")

        self.art = tk.Canvas(body, highlightthickness=0, bd=0, height=app.px(ART_HEIGHT))
        app.paint(self.art, bg="panel")
        self.art.pack(fill="both", expand=True)
        self.art.bind("<Configure>", lambda e: self.draw_art())

        head = tk.Frame(body)
        app.paint(head, bg="panel")
        head.pack(fill="x", pady=(app.px(16), 0))
        self.title = theme.text_label(head, app, game.title, font="card_title")
        self.title.pack(side="left")
        self.chip = theme.text_label(head, app, "", font="caps", fg="on_accent", bg="accent",
                                     padx=app.px(8), pady=app.px(3))
        self.chip.pack(side="right")

        self.detail = theme.text_label(body, app, "", fg="muted")
        self.detail.pack(fill="x", pady=(app.px(6), 0))
        self.status = theme.text_label(body, app, "", font="small")
        self.status.pack(fill="x", pady=(app.px(4), 0))

        buttons = tk.Frame(body)
        app.paint(buttons, bg="panel")
        buttons.pack(side="bottom", fill="x", pady=(app.px(16), 0))
        self.play = theme.PillButton(buttons, app, "PLAY", self.on_play, font=app.fonts["play"],
                                     height=app.px(54), padx=app.px(40), bg_role="panel",
                                     icon="play")
        self.play.pack(side="left")
        self.folder = theme.PillButton(buttons, app, "Choose folder", self.on_folder,
                                       kind="secondary", font=app.fonts["button"],
                                       height=app.px(36), padx=app.px(18), bg_role="panel")
        self.folder.pack(side="right")
        self.setup = theme.PillButton(buttons, app, "Setup", self.on_setup, kind="secondary",
                                      font=app.fonts["button"], height=app.px(36),
                                      padx=app.px(18), bg_role="panel")
        self.setup.pack(side="right", padx=(0, app.px(10)))
        app.on_theme(lambda pal: self.draw_art())

    # ------------------------------------------------------------ drawing

    def draw_art(self) -> None:
        app, pal = self.app, self.app.palette
        w, h = self.art.winfo_width(), self.art.winfo_height()
        if w < 20 or h < 20:
            return
        info = app.infos.get(self.game.key)
        path = info.art if info else None
        if path != self._art_path:
            self._art_path = path
            try:
                self._art_source = _trim_bars(Image.open(path).convert("RGB")) if path else None
            except OSError:
                self._art_source = None
        if self._art_source is not None:
            body = theme.cover(self._art_source, w, h, focus_y=0.4)
            shade = Image.new("L", (1, h))
            for y in range(h):
                t = max(0.0, (y / h - 0.35) / 0.65)
                shade.putpixel((0, y), round(200 * t))
            dark = Image.new("RGB", (w, h), pal["panel"])
            body = Image.composite(dark, body, shade.resize((w, h)))
        else:
            body = theme.gradient(w, h, pal["hero"])
        img = Image.new("RGB", (w, h), pal["panel"])
        img.paste(body, (0, 0), theme.rounded_mask(w, h, app.px(14)))
        size = app.px(92)
        badge = self._badge.resize((size, size), Image.LANCZOS)
        pad = app.px(16)
        img.paste(badge, (pad, h - size - pad), badge)
        if info is None:
            draw = ImageDraw.Draw(img)
            draw.text((pad, pad), "No game folder chosen yet", fill=pal["text"])
        self._photo = ImageTk.PhotoImage(img, master=self.art)
        self.art.delete("all")
        self.art.create_image(0, 0, anchor="nw", image=self._photo)

    def refresh(self) -> None:
        app, game = self.app, self.game
        info = app.infos.get(game.key)
        if info is None:
            self.chip.configure(text=" NOT FOUND ")
            self.detail.configure(text="Choose the folder you extracted the game to.")
            self.status.configure(text="", fg=app.palette["muted"])
        else:
            self.chip.configure(text=f" {info.region.upper()} · {info.serial} ")
            version = f"v{info.version}" if info.version else "unknown version"
            self.detail.configure(text=f"{version}  ·  GRport runtime (experimental)")
            if not info.ok:
                self.status.configure(text=info.problem, fg=app.palette["bad"])
            elif runtime.missing(app.paths):
                self.status.configure(text=runtime.missing(app.paths), fg=app.palette["bad"])
            elif not runtime.is_prepared(app.paths, info):
                self.status.configure(text="The first PLAY prepares the game for GRport's "
                                      "runtime (about a minute).", fg=app.palette["muted"])
            elif info.region not in games.SUPPORTED_REGIONS:
                self.status.configure(text=f"{info.region} version: GRport is tested on USA "
                                      "and Europe.", fg=app.palette["warn"])
            else:
                self.status.configure(text=str(info.folder), fg=app.palette["muted"])
        running = app.phase != "idle"
        mine = app.playing == game.key
        if mine and app.phase == "preparing":
            self.play.set("PREPARING…", enabled=False, icon=None)
        elif mine:
            self.play.set("STOP", enabled=True, icon=None)
        else:
            self.play.set("PLAY", enabled=not running and info is not None and info.ok,
                          icon="play")
        self.folder.set(enabled=not running)
        self.draw_art()

    # ------------------------------------------------------------ buttons

    def on_play(self) -> None:
        if self.app.playing == self.game.key:
            self.app.stop()
            return
        error = self.app.play(self.game.key)
        self.page.flash(error or f"Starting {self.game.title}…", "bad" if error else "ok")

    def on_folder(self) -> None:
        error = self.app.choose_folder(self.game.key)
        if error:
            self.page.flash(error, "bad")
        self.refresh()

    def on_setup(self) -> None:
        self.app.settings.selected = self.game.key
        self.app.show("setup")


class HomePage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._status_job = None
        app.paint(self, bg="bg")
        bar = tk.Frame(self)
        app.paint(bar, bg="bg")
        bar.pack(side="bottom", fill="x", padx=app.px(24), pady=(app.px(12), app.px(18)))
        self.status = theme.text_label(bar, app, "", font="body_bold", bg="bg")
        self.status.pack(side="left")
        self.runtime_note = theme.text_label(bar, app, "", font="small", fg="muted", bg="bg")
        self.runtime_note.pack(side="right")
        # A newer GRport on GitHub (App._check_update): shown when found.
        self.update_button = theme.PillButton(bar, app, "Update", app.install_update,
                                              font=app.fonts["button"], height=app.px(32),
                                              padx=app.px(16))
        self._update_bar = bar
        self.board = theme.CardBoard(self, app, columns=2, fill=True, flat=False)
        self.board.pack(fill="both", expand=True)
        self.cards = {}
        for i, game in enumerate(games.GAMES.values()):
            body = self.board.add(0, i)
            self.cards[game.key] = GameCard(self, body, game)

    def show_update(self, version: str) -> None:
        self.update_button.destroy()
        self.update_button = theme.PillButton(self._update_bar, self.app,
                                              f"Update to {version}", self.app.install_update,
                                              font=self.app.fonts["button"],
                                              height=self.app.px(32), padx=self.app.px(16))
        self.update_button.pack(side="right", padx=(0, self.app.px(14)))

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        for card in self.cards.values():
            card.refresh()
        if runtime.missing(self.app.paths):
            self.runtime_note.configure(text="GRport runtime missing", fg=self.app.palette["bad"])
        else:
            self.runtime_note.configure(text="GRport runtime", fg=self.app.palette["muted"])
        self.board.schedule()

    def set_phase(self, phase: str) -> None:
        self.refresh()
        if phase == "idle":
            code = self.app.runner.exit_code()
            if code not in (None, 0) and not self.app.runner.was_stopped():
                self.flash(f"The game stopped with code {code}. See LOG for details.", "bad")
            else:
                self.flash("", "muted")

    def flash(self, text: str, role: str) -> None:
        self.status.configure(text=text, fg=self.app.palette.get(role, self.app.palette["text"]))
        if self._status_job is not None:
            self.app.after_cancel(self._status_job)
            self._status_job = None
        if text and role != "bad":
            self._status_job = self.app.after(5000, lambda: self.flash("", "muted"))
