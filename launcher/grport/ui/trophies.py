# SPDX-License-Identifier: GPL-2.0-or-later
"""TROPHIES page: every trophy of the chosen game with its icon, and the ones earned in GRport."""
import time
import tkinter as tk

from PIL import Image, ImageEnhance, ImageTk

from grport import games, runtime, trophies
from grport.ui import theme

ICON = 64
GRADE_COLORS = {"platinum": "#b9c7d8", "gold": "#e8b730", "silver": "#b8b8b8",
                "bronze": "#c27a45"}
NOTE = ("Trophies you earn in GRport, kept per game in user/<game>/trophies. A pop-up shows "
        "each one in the game. They are local to this PC: they don't reach your PSN account.")


class TrophiesPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        app.paint(self, bg="bg")
        self._images: list = []
        self._shown = None

        top = tk.Frame(self)
        app.paint(top, bg="bg")
        top.pack(fill="x", padx=app.px(24), pady=(app.px(4), app.px(10)))
        theme.text_label(top, app, "Trophies for", font="body_bold", bg="bg").pack(side="left")
        self.game_choice = theme.Segmented(
            top, app, [(k, g.short) for k, g in games.GAMES.items()], self.select_game,
            bg_role="bg", height=app.px(36))
        self.game_choice.pack(side="left", padx=(app.px(12), 0))
        self.summary = theme.text_label(top, app, "", font="body_bold", bg="bg")
        self.summary.pack(side="right")

        self.bar = tk.Canvas(self, height=app.px(8), highlightthickness=0, bd=0)
        app.paint(self.bar, bg="bg")
        self.bar.pack(fill="x", padx=app.px(24), pady=(0, app.px(10)))
        self.bar.bind("<Configure>", lambda e: self._draw_bar())
        self._fraction = 0.0

        note = theme.text_label(self, app, NOTE, font="small", fg="muted", bg="bg")
        note.pack(side="bottom", fill="x", padx=app.px(24), pady=(app.px(8), app.px(16)))

        holder = tk.Frame(self)
        app.paint(holder, bg="bg")
        holder.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(holder, highlightthickness=0, bd=0)
        app.paint(self.canvas, bg="bg")
        self.scroll = theme.ThinScrollbar(holder, app, self.canvas.yview, bg_role="bg")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y", padx=(0, app.px(6)))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas)
        app.paint(self.inner, bg="bg")
        self._window = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self._window, width=e.width))
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>", self._wheel, add="+")
        app.on_theme(lambda pal: self._draw_bar())

    @property
    def key(self) -> str:
        return self.app.settings.selected

    def _wheel(self, event) -> None:
        if self.app.current == "trophies" and self.winfo_ismapped():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def select_game(self, key: str) -> None:
        if key != self.key:
            self.app.settings.selected = key
            self.app.save_settings()
            self.refresh()

    def on_show(self) -> None:
        self.refresh()

    def _draw_bar(self) -> None:
        c, pal = self.bar, self.app.palette
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        c.create_rectangle(0, 0, w, h, fill=pal["line"], width=0)
        if self._fraction > 0:
            c.create_rectangle(0, 0, max(h, int(w * self._fraction)), h, fill=pal["accent"], width=0)

    def _icon(self, folder, tid: int, earned: bool):
        try:
            img = Image.open(folder / f"trop{tid:03d}.png").convert("RGBA")
        except OSError:
            return None
        img = img.resize((self.app.px(ICON), self.app.px(ICON)), Image.LANCZOS)
        if not earned:  # not earned yet: grey and dim, as on a PS4
            alpha = img.getchannel("A")
            img = ImageEnhance.Brightness(img.convert("L").convert("RGBA")).enhance(0.45)
            img.putalpha(alpha)
        photo = ImageTk.PhotoImage(img, master=self)
        self._images.append(photo)
        return photo

    def refresh(self) -> None:
        app, key = self.app, self.key
        self.game_choice.set(key)
        for child in self.inner.winfo_children():
            child.destroy()
        self._images.clear()
        info = app.infos.get(key)
        user = runtime.user_dir(app.paths, key)
        trp = trophies.trp_path(info.folder) if info else None
        items = trophies.listing(trp, theme.assets_dir(), key, user) if trp else []
        if not items:
            self._fraction = 0.0
            self._draw_bar()
            self.summary.configure(text="")
            theme.text_label(self.inner, app, f"Choose {games.GAMES[key].title}'s folder on the "
                             "PLAY page to see its trophies.", fg="muted", bg="bg").pack(
                fill="x", padx=app.px(24), pady=app.px(12))
            return
        folder = trophies.extract_icons(trp, runtime.data_dir(app.paths, key) / "trophies")
        got = sum(1 for t in items if t.earned)
        self._fraction = got / len(items)
        self._draw_bar()
        self.summary.configure(text=f"{got} of {len(items)} earned ({100 * got // len(items)}%)")
        # Earned first (newest first), then the rest in the game's order.
        order = sorted(items, key=lambda t: (not t.earned, -t.earned, t.id))
        for t in order:
            row = tk.Frame(self.inner)
            app.paint(row, bg="panel")
            row.pack(fill="x", padx=app.px(24), pady=(0, app.px(8)))
            icon = self._icon(folder, t.id, bool(t.earned))
            pic = tk.Label(row, image=icon, bd=0) if icon else tk.Frame(
                row, width=app.px(ICON), height=app.px(ICON))
            app.paint(pic, bg="panel")
            pic.pack(side="left", padx=app.px(12), pady=app.px(10))
            right = tk.Frame(row)
            app.paint(right, bg="panel")
            right.pack(side="right", padx=app.px(16))
            if t.grade:
                chip = tk.Label(right, text=t.grade.upper(), font=app.fonts["small"],
                                bg=GRADE_COLORS[t.grade], fg="#141414", padx=app.px(8))
                chip.pack(side="top", anchor="e")
            when = time.strftime("%d %b %Y, %H:%M", time.localtime(t.earned)) if t.earned else "Not earned"
            theme.text_label(right, app, when, font="small", fg="ok" if t.earned else "muted").pack(
                side="top", anchor="e", pady=(app.px(4), 0))
            text = tk.Frame(row)
            app.paint(text, bg="panel")
            text.pack(side="left", fill="x", expand=True, pady=app.px(10))
            theme.text_label(text, app, t.name, font="body_bold",
                             fg="text" if t.earned else "muted").pack(fill="x")
            if t.detail:
                detail = theme.text_label(text, app, t.detail, font="small", fg="muted")
                detail.pack(fill="x")
                text.bind("<Configure>", lambda e, d=detail: d.configure(wraplength=max(1, e.width)),
                          add="+")
        self.canvas.yview_moveto(0)
