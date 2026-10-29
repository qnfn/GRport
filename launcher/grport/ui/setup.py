# SPDX-License-Identifier: GPL-2.0-or-later
"""SETUP page: each game's window and GPU readbacks for GRport's runtime."""
import tkinter as tk

from grport import games, patches
from grport.settings import FPS_CHOICES, LANGUAGES
from grport.ui import theme

WINDOW_SIZES = ("1280x720", "1600x900", "1920x1080", "2560x1440", "3840x2160")
READBACK_CHOICES = (("off", "Off"), ("relaxed", "Relaxed"), ("precise", "Precise"))
IN_GAME_NOTE = ("Graphics and the upscaler are set in the game: open GRport's in-game "
                "menu with Insert (or L3+R3 on a controller).")
RUNTIME_NOTE = ("The first PLAY prepares the game for GRport's runtime (about a minute). "
                "Experimental: both games play their openings; some starts still crash in the "
                "first seconds (press PLAY again).")
FPS_NOTES = {
    "gr2": ("Gravity Rush 2 (version 1.11) above 30 FPS: Junmin Lee's frame rate patches, "
            "downloaded from his GitHub repository at the first PLAY. The "
            "game runs at a fixed step, so it slows down if your PC cannot hold the rate; a "
            "display with that refresh rate shows all frames. The next PLAY prepares the game "
            "again (about a minute)."),
    "gr1": ("Gravity Rush Remastered runs at 60 FPS on the PS4. Above 60 the game keeps its "
            "speed; Junmin Lee's gravity kick camera fix is added (downloaded at the first "
            "PLAY). A display with that refresh rate shows all frames."),
}
WINDOW_CHOICES = (("fullscreen", "Fullscreen"), ("borderless", "Borderless"), ("window", "Window"))
WINDOW_NOTE = ("Fullscreen takes the monitor (exclusive); Borderless is a window covering it; "
               "Window has a title bar and the size below.")
PATCHES_NOTE = ("Patches by Junmin Lee (his GR2fork patch repository), downloaded at the first "
                "PLAY that needs them. Made for Gravity Rush Remastered 1.00 and Gravity Rush 2 "
                "1.11. A change prepares the game again at the next PLAY (about a minute).")
READBACK_NOTE = ("GPU readbacks: the game gets the GPU's results back exactly when it needs them. "
                 "Precise fixes the rare missing or flickering effect but costs FPS; Off is "
                 "fastest. Off by default.")


class SetupPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._menu = None
        self._status_job = None
        self.board = None
        app.paint(self, bg="bg")

        top = tk.Frame(self)
        app.paint(top, bg="bg")
        top.pack(fill="x", padx=app.px(24), pady=(app.px(4), app.px(10)))
        theme.text_label(top, app, "Settings for", font="body_bold", bg="bg").pack(side="left")
        self.game_choice = theme.Segmented(
            top, app, [(k, g.short) for k, g in games.GAMES.items()], self.select_game,
            bg_role="bg", height=app.px(36))
        self.game_choice.pack(side="left", padx=(app.px(12), 0))

        bar = tk.Frame(self)
        app.paint(bar, bg="bg")
        bar.pack(side="bottom", fill="x", padx=app.px(24), pady=(app.px(10), app.px(18)))
        self.status = theme.text_label(bar, app, "Applies on the next PLAY.", fg="muted",
                                       bg="bg")
        self.status.pack(side="left", fill="x", expand=True)

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
        self.build()

    # ------------------------------------------------------------ helpers

    @property
    def key(self) -> str:
        return self.app.settings.selected

    @property
    def game(self) -> games.Game:
        return games.GAMES[self.key]

    @property
    def g(self):
        return self.app.settings.games[self.key]

    def _wheel(self, event) -> None:
        if self.app.current == "setup" and self.winfo_ismapped():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _wrapping(self, label: tk.Label, master: tk.Misc) -> tk.Label:
        master.bind("<Configure>", lambda e: label.configure(wraplength=max(1, e.width)),
                    add="+")
        return label

    def _row(self, card, label: str, first: bool = False) -> tk.Frame:
        app = self.app
        row = tk.Frame(card)
        app.paint(row, bg="panel")
        row.pack(fill="x", pady=(0 if first else app.px(12), 0))
        theme.text_label(row, app, label, font="body_bold", width=14).pack(side="left")
        return row

    def _note(self, card, text: str) -> tk.Label:
        note = theme.text_label(card, self.app, text, font="small", fg="muted")
        self._wrapping(note, card).pack(fill="x", pady=(self.app.px(12), 0))
        return note

    # ------------------------------------------------------------ building

    def build(self) -> None:
        app = self.app
        if self.board is not None:
            self.board.destroy()
        self.board = theme.CardBoard(self.inner, app, columns=2)
        self.board.pack(fill="x")
        self.game_choice.set(self.key)

        display = self.board.add(0, 0, title="Display")
        row = self._row(display, "Window", first=True)
        self.window_choice = theme.Segmented(row, app, WINDOW_CHOICES, self.set_window_mode)
        self.window_choice.pack(side="left")
        self._note(display, WINDOW_NOTE)
        row = self._row(display, "Window size")
        self.size_box = theme.Dropdown(row, app, lambda: self._popup(
            self.size_box, WINDOW_SIZES, self.app.settings.window_size, self.set_window_size))
        self.size_box.pack(side="left")
        self._note(display, "Window size is used when Window is chosen.")
        row = self._row(display, "Language")
        self.language_box = theme.Dropdown(row, app, lambda: self._popup(
            self.language_box, [(key, name) for key, name, _ in LANGUAGES],
            self.app.settings.language, self.set_language))
        self.language_box.pack(side="left")
        self._note(display, "Menus and subtitles. The voices speak the games' own invented "
                            "language in every version.")

        gfx = self.board.add(0, 1, title="Graphics")
        row = self._row(gfx, "GPU readbacks", first=True)
        self.readback_choice = theme.Segmented(row, app, READBACK_CHOICES, self.set_readbacks)
        self.readback_choice.pack(side="left")
        self._note(gfx, READBACK_NOTE)
        row = self._row(gfx, "Frame rate")
        self.fps_choice = theme.Segmented(row, app, [(f, f"{f} FPS") for f in FPS_CHOICES[self.key]],
                                          self.set_fps)
        self.fps_choice.pack(side="left")
        self._note(gfx, FPS_NOTES[self.key])

        self.patch_choices = {}
        extra = self.board.add(2, 0, span=2, title="Patches")
        for i, (prefix, label, _, note) in enumerate(patches.OPTIONAL.get(self.key, ())):
            row = tk.Frame(extra)
            app.paint(row, bg="panel")
            row.pack(fill="x", pady=(0 if i == 0 else app.px(8), 0))
            choice = theme.Segmented(row, app, ((True, "On"), (False, "Off")),
                                     lambda on, p=prefix: self.set_patch(p, on))
            choice.pack(side="left")
            theme.text_label(row, app, label, font="body_bold").pack(side="left", padx=(app.px(12), 0))
            if note:
                theme.text_label(row, app, note, font="small", fg="muted").pack(
                    side="left", padx=(app.px(10), 0))
            self.patch_choices[prefix] = choice
        self._note(extra, PATCHES_NOTE)

        about = self.board.add(1, 0, span=2, title="In the game")
        self.in_game_note = theme.text_label(about, app, IN_GAME_NOTE, font="body_bold")
        self._wrapping(self.in_game_note, about).pack(fill="x")
        self._note(about, RUNTIME_NOTE)
        self.refresh()

    def _popup(self, box, options, current, command) -> None:
        if self._menu is not None:
            self._menu.destroy()
        menu = self._menu = theme.styled_menu(self, self.app)
        var = tk.StringVar(menu, value=current)
        for value in options:
            label = value if isinstance(value, str) else value[1]
            val = value if isinstance(value, str) else value[0]
            menu.add_radiobutton(label=label, variable=var, value=val,
                                 command=lambda v=val: command(v))
        menu.update_idletasks()
        try:
            menu.tk_popup(box.winfo_rootx(), box.winfo_rooty() + box.winfo_height() +
                          self.app.px(4))
        finally:
            menu.grab_release()

    # ------------------------------------------------------------ showing

    def on_show(self) -> None:
        if self.game_choice.value != self.key:
            self.build()
        else:
            self.refresh()

    def refresh(self) -> None:
        g, s = self.g, self.app.settings
        self.window_choice.set(s.window_mode)
        self.size_box.set(s.window_size, enabled=s.window_mode == "window")
        self.readback_choice.set(g.readbacks)
        self.fps_choice.set(g.fps)
        chosen = patches.extras(s, self.key)
        for prefix, choice in self.patch_choices.items():
            choice.set(prefix in chosen)
        self.language_box.set(dict((k, n) for k, n, _ in LANGUAGES)[s.language])
        self.board.schedule()

    def _saved(self) -> None:
        ok = self.app.save_settings()
        self.flash("Applies on the next PLAY." if ok else
                   "Could not save the settings file (grport.json)", "muted" if ok else "bad")
        self.refresh()
        self.app.pages["play"].refresh()

    def flash(self, text: str, role: str) -> None:
        self.status.configure(text=text, fg=self.app.palette[role])

    # ------------------------------------------------------------ choices

    def select_game(self, key: str) -> None:
        if key != self.key:
            self.app.settings.selected = key
            self.app.save_settings()
            self.build()

    def set_window_mode(self, mode: str) -> None:
        self.app.settings.window_mode = mode
        self._saved()

    def set_patch(self, prefix: str, on: bool) -> None:
        chosen = [p for p in patches.extras(self.app.settings, self.key) if p != prefix]
        self.g.extras = chosen + [prefix] if on else chosen
        self._saved()

    def set_window_size(self, size: str) -> None:
        self.app.settings.window_size = size
        self._saved()

    def set_language(self, key: str) -> None:
        self.app.settings.language = key
        self._saved()

    def set_fps(self, fps: int) -> None:
        self.g.fps = fps
        self._saved()

    def set_readbacks(self, value: str) -> None:
        self.g.readbacks = value
        self._saved()
