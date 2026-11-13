# SPDX-License-Identifier: GPL-2.0-or-later
"""SETUP page: each game's window and GPU readbacks for GRport's runtime."""
import os
import tkinter as tk

from grport import games, ini, patches, runtime, settings, shortcuts, steam
from grport.settings import (ASPECTS, DEADZONE_CHOICES, FPS_CHOICES, LANGUAGES, RENDER_GRID,
                             WINDOW_HEIGHTS, aspect_of, resolution_label, resolution_size)
from grport.ui import theme

WINDOW_SIZE_CHOICES = tuple((f"{h}p", {1440: "2K", 2160: "4K"}.get(h, f"{h}p"))
                            for h in WINDOW_HEIGHTS)
READBACK_CHOICES = (("off", "Off"), ("relaxed", "Relaxed"), ("precise", "Precise"))
IN_GAME_NOTE = ("The Picture settings below are also in GRport's in-game menu: Insert (or "
                "L3+R3 on a controller) changes them while you play.")
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
RESOLUTION_NOTE = ("Render: the size the game draws at, {size}, in every window mode (Junmin "
                   "Lee's resolution patches, no upscaling{own}). Aspect ratio: pick your screen's "
                   "shape; 16:10 and wider show more of the view, and a screen of another shape "
                   "gets black bars. Pick your screen's size for a sharp picture, a bigger one for "
                   "supersampling; bigger sizes need a faster GPU and more video memory. The next "
                   "PLAY prepares the game again (about a minute).")
# Render's buttons: the size steps of every aspect ratio (ultrawide starts at 1080p); the note
# names the exact size (1080p is 1920x1200 on 16:10, 2584x1080 on 21:9).
RENDER_STEPS = ("600p", "720p", "1080p", "2K", "4K")
OLD_RESOLUTION_NOTE = (" Now {label}, chosen in an older GRport; it keeps working until you pick "
                       "a Render size.")
# The in-game menu's picture settings (grport.ini, read by the runtime at start): key, label,
# choices, default when the file does not have it yet.
ON_OFF = (("1", "On"), ("0", "Off"))
PICTURE = (
    ("upscaler", "Anti-aliasing", (("off", "Off"), ("fsr3", "FSR 3.1"), ("fsr4", "FSR 4"),
                                   ("taa", "TAA"), ("dlss", "DLSS")), "fsr3"),
    ("sharpen", "Sharpening", ON_OFF, "1"),
    ("fsr1", "FSR 1 to the screen", ON_OFF, "1"),
    ("show_fps", "FPS counter", ON_OFF, "1"),
    ("mute_unfocused", "Mute in background", ON_OFF, "0"),
    ("button_prompts", "Button prompts", (("auto", "Auto (what you play with)"),
                                           ("playstation", "PlayStation"), ("xbox", "Xbox"),
                                           ("switch", "Switch"), ("keyboard", "Keyboard and mouse")), "auto"),
    ("xbox_buttons", "Xbox look", (("0", "Xbox 360"), ("1", "Xbox One")), "0"),
    ("playstation_buttons", "PlayStation look", (("0", "PS4"), ("1", "PS5")), "0"),
)
SHARPNESS = tuple(f"{v / 10:.2f}" for v in range(11))
PICTURE_NOTE = ("The same settings as GRport's in-game menu (Insert / L3+R3), per game. "
                "Anti-aliasing: FSR and DLSS smooth edges using earlier frames (FSR 4 needs a GPU "
                "with fast INT8 math, DLSS an NVIDIA RTX card; without one the game falls back "
                "to FSR 3.1). Off keeps the game's own picture: with a 4K render resolution that "
                "is native 4K without any anti-aliasing. Button prompt changes need a game restart. "
                "FSR 1 scales the picture to the window "
                "with sharp edges.")
WINDOW_CHOICES = (("fullscreen", "Fullscreen"), ("borderless", "Borderless"), ("window", "Window"))
WINDOW_NOTE = ("Fullscreen takes the monitor (exclusive); Borderless is a window covering it; "
               "Window has a title bar and the Window size below.")
WINDOW_SIZE_NOTE = ("Window size: only the window, in Window mode ({size}, the shape of Render); "
                    "Fullscreen and Borderless use the whole monitor.")
PATCHES_NOTE = ("Game patches by Junmin Lee are downloaded when needed. GR1 cheats are "
                "adapted from GoldHEN codes by Talixme and Skal where noted. Patches target GR1 "
                "1.00 and GR2 1.11. Changes prepare the game again at the next PLAY.")
# Every _row label on the page: the label column fits the longest one.
ROW_LABELS = ("Window", "Window size", "Render", "Aspect ratio", "Language", "GPU readbacks",
              "Threading", "Frame rate", "Skybox seam fix", "PS4 Pro mode", "Stick dead zone", "Controller speaker", "Camera Roll", "Temporal output", "Performance log", "HDR10 output", "HDR white (nits)",
              *(label for _, label, _, _ in PICTURE))
THREADING_CHOICES = (("auto", "Auto"), ("1", "On"), ("0", "Off"))
THREADING_NOTE = ("Threading: the game's GPU work is prepared on extra threads, for much more FPS. "
                  "Auto turns it on (as On does); choose Off if the game crashes.")
DEADZONE_NOTE = ("Stick dead zone: how far a controller stick moves before the game sees it, "
                 "for sticks that drift or wobble (the character walks on its own). Raise it "
                 "until the drift stops; 0% turns it off. Both sticks, keyboard and mouse "
                 "unaffected.")
SKYBOX_NOTE = ("Skybox seam fix: removes the lines where the sky's faces meet (also in reflections). "
               "Its shaders are bigger: on an older GPU (GTX 1050 Ti class), or if the game "
               "crashes or stutters in busy places, try Off. On by default; the first start "
               "after a change builds the shaders again.")
PHOTO_ROLL_CHOICES = (("999", "999 photos"), ("unlimited", "No limit"))
PHOTO_ROLL_NOTE = ("Camera Roll: 999 photos is the game's own limit, as on the PS4: the camera "
                   "stops taking photos when the Camera Roll is full. No limit: keep taking "
                   "photos forever; the Camera Roll then shows your newest 500 (the game can't "
                   "list more than 999, and the rest is room for burst shots). Every photo is "
                   "saved in user/gr2/Capture Gallery either way.")
PRO_NOTE = ("PS4 Pro mode (experimental): Gravity Rush 2 thinks it runs on a PS4 Pro and uses "
            "its own Pro rendering. Untested on PC: turn it off if the game crashes or looks "
            "wrong. Off by default.")
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
        self.canvas.bind_all("<Button-4>", lambda e: self._wheel_units(-1), add="+")
        self.canvas.bind_all("<Button-5>", lambda e: self._wheel_units(1), add="+")
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

    def _wheel_units(self, units: int) -> None:
        if self.app.current == "setup" and self.winfo_ismapped():
            self.canvas.yview_scroll(units, "units")

    def _wrapping(self, label: tk.Label, master: tk.Misc) -> tk.Label:
        master.bind("<Configure>", lambda e: label.configure(wraplength=max(1, e.width)),
                    add="+")
        return label

    def _label_width(self) -> int:
        """The label column in characters, wide enough for the longest row label."""
        font = self.app.fonts["body_bold"]
        longest = max(font.measure(text) for text in ROW_LABELS)
        return max(14, -(-longest // max(1, font.measure("0"))) + 1)

    def _row(self, card, label: str, first: bool = False) -> tk.Frame:
        app = self.app
        row = tk.Frame(card)
        app.paint(row, bg="panel")
        row.pack(fill="x", pady=(0 if first else app.px(12), 0))
        theme.text_label(row, app, label, font="body_bold", width=self._label_width()).pack(
            side="left")
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

        preset = self.board.add(6, 0, span=2, title="Steam Deck")
        preset_row = tk.Frame(preset)
        app.paint(preset_row, bg="panel")
        preset_row.pack(fill="x")
        for name, mode in (("Quality: 1280x800", "quality"), ("Performance: 960x600 + FSR 4", "performance")):
            theme.PillButton(preset_row, app, name, lambda m=mode: self.apply_deck_preset(m),
                             kind="secondary", font=app.fonts["button"], height=app.px(36),
                             padx=app.px(18), bg_role="panel").pack(side="left", padx=(0, app.px(10)))
        self._note(preset, "Quality draws at the Deck's native 1280x800. Performance draws at 960x600 "
                          "and uses FSR 4 INT8 to reconstruct 1280x800 (FSR 3.1 fallback). "
                          "Choose DLSS under Anti-aliasing on NVIDIA RTX; DLSS is unavailable on Steam Deck. "
                          "Both modes use borderless, relaxed GPU readbacks and PS4 Pro mode off. "
                          "Gravity Rush 2: 30 FPS and Skip intro enabled as a workaround for "
                          "the reported intro black screen (requires game update 1.11). "
                          "Touchpad actions can be assigned in CONTROLS.")

        display = self.board.add(0, 0, title="Display")
        row = self._row(display, "Window", first=True)
        self.window_choice = theme.Segmented(row, app, WINDOW_CHOICES, self.set_window_mode)
        self.window_choice.pack(side="left")
        row = self._row(display, "Window size")
        self.size_choice = theme.Segmented(row, app, WINDOW_SIZE_CHOICES, self.set_window_size)
        self.size_choice.pack(side="left")
        self.window_note = self._note(display, "")
        row = self._row(display, "Render")
        self.render_choice = theme.Segmented(row, app, (), self.set_resolution)
        self.render_choice.pack(side="left")
        row = self._row(display, "Aspect ratio")
        self.aspect_choice = theme.Segmented(row, app, [(a, a) for a in ASPECTS], self.set_aspect)
        self.aspect_choice.pack(side="left")
        self.resolution_note = self._note(display, "")
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
        row = self._row(gfx, "Threading")
        self.threading_choice = theme.Segmented(row, app, THREADING_CHOICES, self.set_threading)
        self.threading_choice.pack(side="left")
        self._note(gfx, THREADING_NOTE)
        row = self._row(gfx, "Frame rate")
        self.fps_choice = theme.Segmented(row, app, [(f, f"{f} FPS") for f in FPS_CHOICES[self.key]],
                                          self.set_fps)
        self.fps_choice.pack(side="left")
        self._note(gfx, FPS_NOTES[self.key])
        row = self._row(gfx, "Skybox seam fix")
        self.skybox_choice = theme.Segmented(row, app, ((True, "On"), (False, "Off")),
                                             self.set_skybox_fix)
        self.skybox_choice.pack(side="left")
        self._note(gfx, SKYBOX_NOTE)
        self.pro_choice = None
        if self.key == "gr2":
            row = self._row(gfx, "PS4 Pro mode")
            self.pro_choice = theme.Segmented(row, app, ((True, "On"), (False, "Off")),
                                              self.set_ps4_pro)
            self.pro_choice.pack(side="left")
            self._note(gfx, PRO_NOTE)

        picture = self.board.add(2, 0, span=2, title="Picture")
        self.picture_choices = {}
        for i, (name, label, choices, _) in enumerate(PICTURE):
            row = self._row(picture, label, first=i == 0)
            choice = theme.Segmented(row, app, choices, lambda v, n=name: self.set_picture(n, v))
            choice.pack(side="left")
            self.picture_choices[name] = choice
            if name == "sharpen":
                theme.text_label(row, app, "Sharpness", font="body").pack(
                    side="left", padx=(app.px(16), app.px(8)))
                self.sharpness_box = theme.Dropdown(row, app, lambda: self._popup(
                    self.sharpness_box, SHARPNESS, self._picture().get("sharpness", "0.30"),
                    lambda v: self.set_picture("sharpness", v)))
                self.sharpness_box.pack(side="left")
        row = self._row(picture, "HDR10 output")
        self.hdr_choice = theme.Segmented(row, app, ((True, "On"), (False, "Off")), self.set_hdr_output)
        self.hdr_choice.pack(side="left")
        row = self._row(picture, "HDR white (nits)")
        self.hdr_white_box = theme.Dropdown(row, app, lambda: self._popup(
            self.hdr_white_box, [(v, str(v)) for v in (100, 150, 200, 250, 300, 400)],
            self.g.hdr_paper_white, self.set_hdr_white))
        self.hdr_white_box.pack(side="left")
        self._note(picture, "Experimental SDR-to-HDR10 mapping. Enable HDR in the operating system "
                          "and use an HDR display. This preserves the game's SDR grade and cannot "
                          "restore clipped highlights. SDR fallback when unsupported. Restart to apply.")
        row = self._row(picture, "Temporal output")
        self.output_box = theme.Dropdown(row, app, lambda: self._popup(
            self.output_box, [(value, value or "Render size (AA)") for value in settings.TEMPORAL_OUTPUTS],
            self.g.temporal_output, self.set_temporal_output))
        self.output_box.pack(side="left")
        row = self._row(picture, "Performance log")
        self.profile_choice = theme.Segmented(row, app, ((True, "On"), (False, "Off")), self.set_performance_log)
        self.profile_choice.pack(side="left")
        self._note(picture, "Performance log records GPU pass times, submission idle time and frame pacing "
                          "to help diagnose slow scenes. GPU idle can mean CPU work or a frame cap. "
                          "Off by default; restart the game to apply.")
        self._note(picture, PICTURE_NOTE + " Temporal output reconstructs a smaller render to the chosen "
                          "size with FSR 3.1, FSR 4 INT8 or DLSS. Render size (AA) filters at the "
                          "game's own resolution. Restart the game after changing Temporal output.")

        controls = self.board.add(3, 0, span=2, title="Controller" if self.key != "gr2"
                                  else "Controller and camera")
        row = self._row(controls, "Stick dead zone", first=True)
        self.deadzone_box = theme.Dropdown(row, app, lambda: self._popup(
            self.deadzone_box, [(v, f"{v}%") for v in DEADZONE_CHOICES], self.g.stick_deadzone,
            self.set_deadzone))
        self.deadzone_box.pack(side="left")
        self._note(controls, DEADZONE_NOTE)
        row = self._row(controls, "Controller speaker")
        self.speaker_choice = theme.Segmented(row, app, ((True, "On"), (False, "Off")), self.set_pad_speaker)
        self.speaker_choice.pack(side="left")
        self._note(controls, "Off silences sounds routed to the controller speaker. Main game audio is unaffected. "
                             "Restart the game to apply.")
        row = self._row(controls, "Low-gravity warning")
        self.beep_choice = theme.Segmented(row, app, ((True, "On"), (False, "Off")),
                                            self.set_low_gravity_beep)
        self.beep_choice.pack(side="left")
        self._note(controls, "Turn off the low-gravity warning beep in both the game mix and controller speaker. "
                             "Restart the game to apply.")
        self.roll_choice = None
        if self.key == "gr2":
            row = self._row(controls, "Camera Roll")
            self.roll_choice = theme.Segmented(row, app, PHOTO_ROLL_CHOICES, self.set_photo_roll)
            self.roll_choice.pack(side="left")
            self._note(controls, PHOTO_ROLL_NOTE)

        links = self.board.add(5, 0, span=2, title="Shortcuts")
        row = tk.Frame(links)
        app.paint(row, bg="panel")
        row.pack(fill="x")
        menu = "Start menu" if os.name == "nt" else "app menu"
        for text, where in (("Add to desktop", "desktop"), (f"Add to {menu}", "start")):
            theme.PillButton(row, app, text, lambda w=where: self.add_shortcut(w),
                             kind="secondary", font=app.fonts["button"], height=app.px(36),
                             padx=app.px(18), bg_role="panel").pack(side="left",
                                                                    padx=(0, app.px(10)))
        theme.PillButton(row, app, "Add to Steam", self.add_to_steam,
                         kind="secondary", font=app.fonts["button"], height=app.px(36),
                         padx=app.px(18), bg_role="panel").pack(side="left")
        self._note(links, f"Start {games.GAMES[self.key].title} directly, including from Steam Game Mode. "
                          "Each game gets its own shortcut. Exit Steam before adding it.")

        self.patch_choices = {}
        extra = self.board.add(4, 0, span=2, title="Patches")
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
        aspect = aspect_of(g.resolution)
        windowed = s.window_mode == "window"
        for value, _ in WINDOW_SIZE_CHOICES:
            self.size_choice.set_enabled(value, windowed)
        w, h = settings.window(s, g)
        self.size_choice.set(f"{h}p")
        self.window_note.configure(text=WINDOW_NOTE + " " + WINDOW_SIZE_NOTE.format(size=f"{w}x{h}"))
        steps = RENDER_STEPS[-len(RENDER_GRID[aspect]):]
        self.render_choice.set_choices(list(zip(RENDER_GRID[aspect], steps)))
        self.render_choice.set(g.resolution)
        self.aspect_choice.set(aspect)
        note = RESOLUTION_NOTE.format(size="{}x{}".format(*resolution_size(g.resolution)),
                                      own=", 1920x1080 is the game's own" if aspect == "16:9" else "")
        if g.resolution not in RENDER_GRID[aspect]:
            note += OLD_RESOLUTION_NOTE.format(label=resolution_label(g.resolution))
        self.resolution_note.configure(text=note)
        self.readback_choice.set(g.readbacks)
        self.fps_choice.set(g.fps)
        self.skybox_choice.set(g.skybox_fix)
        values = self._picture()
        for name, _, choices, default in PICTURE:
            value = values.get(name, default)
            self.picture_choices[name].set(value if value in dict(choices) else default)
        try:
            self.sharpness_box.set(f"{float(values.get('sharpness', '0.3')):.2f}")
        except ValueError:
            self.sharpness_box.set("0.30")
        self.threading_choice.set(g.threading)
        if self.pro_choice is not None:
            self.pro_choice.set(g.ps4_pro)
        self.deadzone_box.set(f"{g.stick_deadzone}%")
        self.speaker_choice.set(g.pad_speaker)
        self.beep_choice.set(g.low_gravity_beep)
        self.output_box.set(g.temporal_output or "Render size (AA)")
        self.profile_choice.set(g.performance_log)
        self.hdr_choice.set(g.hdr_output)
        self.hdr_white_box.set(str(g.hdr_paper_white))
        if self.roll_choice is not None:
            self.roll_choice.set(g.photo_roll)
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

    def add_shortcut(self, where: str) -> None:
        folder = shortcuts.desktop_dir() if where == "desktop" else shortcuts.start_menu_dir()
        place = "desktop" if where == "desktop" else ("Start menu" if os.name == "nt" else "app menu")

        def done(_lnk, error):
            if error is not None:
                self.flash(f"Could not add the shortcut: {error}", "bad")
            else:
                self.flash(f"GRport is now in your {place}.", "muted")
        key = self.key
        self.app.run_task(lambda: shortcuts.create(self.app.paths, folder, key), done)

    def add_to_steam(self) -> None:
        key = self.key
        def done(result, error):
            if error is not None:
                self.flash(f"Could not add to Steam: {error}", "bad")
            else:
                self.flash(f"{games.GAMES[key].title} added. Start Steam to see it in your library.", "muted")
        self.app.run_task(lambda: steam.add_game(self.app.paths, key), done)

    def apply_deck_preset(self, mode: str = "quality") -> None:
        if mode not in ("quality", "performance"):
            raise ValueError("Unknown Steam Deck mode")
        self.g.resolution = "16:10 1280x800" if mode == "quality" else "GRport 16:10 960x600"
        self.g.temporal_output = "1280x800" if mode == "performance" else ""
        ini.update_ini(self._ini(), {"upscaler": "fsr4", "fsr1": "0", "sharpen": "1", "sharpness": "0.30"})
        self.g.readbacks = "relaxed"
        self.g.fps = FPS_CHOICES[self.key][0]
        self.g.ps4_pro = False
        self.app.settings.window_mode = "borderless"
        self.app.settings.window_size = "800p"
        if self.key == "gr2":
            chosen = patches.extras(self.app.settings, self.key)
            self.g.extras = chosen if "Skip Intro" in chosen else chosen + ["Skip Intro"]
        self.app.save_settings()
        self.build()
        self.app.refresh_pages()
        self.flash("Steam Deck preset applied. GPU-heavy scenes may still fall below the target frame rate.", "muted")

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

    def _ini(self):
        return runtime.user_dir(self.app.paths, self.key) / "grport.ini"

    def _picture(self) -> dict:
        return ini.read_ini(self._ini())

    def set_picture(self, name: str, value: str) -> None:
        try:
            ini.update_ini(self._ini(), {name: value})
        except OSError as e:
            self.flash(f"Could not save grport.ini: {e.strerror or e}", "bad")
            return
        self.refresh()

    def set_aspect(self, aspect: str) -> None:
        """The same size step (small, 1080p-ish, 1440p-ish, 4K) in the new shape."""
        old = RENDER_GRID.get(aspect_of(self.g.resolution), ())
        # Preserve the size tier counted down from 4K. This also works when one
        # aspect has an extra small tier (Steam Deck's 600p) or fewer tiers (ultrawide).
        tier = len(old) - old.index(self.g.resolution) - 1 if self.g.resolution in old else 2
        new = RENDER_GRID[aspect]
        self.set_resolution(new[max(0, min(len(new) - 1, len(new) - tier - 1))])

    def set_resolution(self, prefix: str) -> None:
        self.g.resolution = prefix
        self._saved()

    def set_threading(self, value: str) -> None:
        self.g.threading = value
        self._saved()

    def set_skybox_fix(self, on: bool) -> None:
        self.g.skybox_fix = bool(on)
        self._saved()

    def set_ps4_pro(self, on: bool) -> None:
        self.g.ps4_pro = bool(on)
        self._saved()

    def set_hdr_output(self, on: bool) -> None:
        self.g.hdr_output = bool(on)
        self._saved()

    def set_hdr_white(self, nits: int) -> None:
        self.g.hdr_paper_white = nits
        self._saved()

    def set_performance_log(self, on: bool) -> None:
        self.g.performance_log = bool(on)
        self._saved()

    def set_temporal_output(self, value: str) -> None:
        self.g.temporal_output = value
        self._saved()

    def set_pad_speaker(self, on: bool) -> None:
        self.g.pad_speaker = bool(on)
        self._saved()

    def set_low_gravity_beep(self, on: bool) -> None:
        self.g.low_gravity_beep = bool(on)
        self._saved()

    def set_photo_roll(self, value: str) -> None:
        self.g.photo_roll = value
        self._saved()

    def set_deadzone(self, percent: int) -> None:
        self.g.stick_deadzone = int(percent)
        self._saved()

    def set_readbacks(self, value: str) -> None:
        self.g.readbacks = value
        self._saved()
