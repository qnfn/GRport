# SPDX-License-Identifier: GPL-2.0-or-later
"""The window opens, every page builds for both games, and choices reach the settings."""
import pytest

from grport.paths import AppPaths
from grport.settings import load_settings
from tests.test_core import make_game


@pytest.fixture
def app(tmp_path):
    from grport.ui.app import App
    paths = AppPaths.for_root(tmp_path / "GRport")
    make_game(tmp_path / "GR1" / "CUSA01113", "CUSA01113", "01.00")
    make_game(tmp_path / "GR2" / "CUSA03694", "CUSA03694", "01.11")
    window = App(paths)
    window.update()
    yield window
    window.destroy()


def test_games_next_to_the_launcher_are_found(app):
    assert set(app.infos) == {"gr1", "gr2"}
    card = app.pages["play"].cards["gr2"]
    assert "USA" in card.chip.cget("text")
    assert "runtime" in card.detail.cget("text")
    assert "runtime is missing" in card.status.cget("text")  # no runtime in the test folder


def test_every_page_builds_for_both_games(app):
    assert set(app.pages) == {"play", "setup", "controls", "trophies", "log"}
    for key in ("gr1", "gr2"):
        app.settings.selected = key
        for tab in ("play", "setup", "controls", "trophies", "log"):
            app.show(tab)
            app.update()


def test_setup_choices_are_saved(app):
    app.settings.selected = "gr2"
    app.show("setup")
    page = app.pages["setup"]
    assert "Insert" in page.in_game_note.cget("text")
    page.set_window_mode("window")
    page.set_patch("Disable motion blur", False)
    page.set_window_size("2560x1440")
    page.set_readbacks("relaxed")
    page.set_ps4_pro(True)
    assert page.deadzone_box.text == "10%"  # the default
    page.set_deadzone(24)
    assert page.deadzone_box.text == "24%"
    saved = load_settings(app.paths)
    assert saved.games["gr2"].stick_deadzone == 24 and saved.games["gr1"].stick_deadzone == 10
    assert saved.window_mode == "window" and saved.window_size == "2560x1440"
    assert "Disable motion blur" not in saved.games["gr2"].extras
    assert saved.games["gr2"].readbacks == "relaxed" and saved.games["gr1"].readbacks == "off"
    assert saved.games["gr2"].ps4_pro and not saved.games["gr1"].ps4_pro


def test_play_refuses_without_the_runtime(app):
    assert "runtime is missing" in app.play("gr2")


def test_bug_report_names_the_runtime(app):
    text = app.pages["log"].report_text()
    assert text.startswith("GRport ") and "runtime" in text.splitlines()[0]
    assert "Stick dead zone: 10%" in text


def test_controls_rebind_writes_that_games_input_ini(app):
    app.show("controls")
    page = app.pages["controls"]
    page.select_game("gr2")
    ini = app.paths.root / "user" / "gr2" / "input.ini"
    assert ini.is_file()  # created from the bundled defaults
    page.start_rebind("cross")
    assert page.press_key("x")
    assert "cross = x" in ini.read_text(encoding="utf-8")
    assert not (app.paths.root / "user" / "gr1" / "input.ini").exists()
    assert page.set_controller("cross", "circle")
    assert "cross = circle" in ini.read_text(encoding="utf-8")


def test_render_resolution_choice_is_saved_and_patched(app):
    from grport import patches
    app.settings.selected = "gr2"
    app.show("setup")
    page = app.pages["setup"]
    page.set_resolution("16:10 1920x1200")
    assert load_settings(app.paths).games["gr2"].resolution == "16:10 1920x1200"
    assert page.aspect_choice.value == "16:10" and page.render_choice.value == "16:10 1920x1200"
    assert "1920x1200" in page.resolution_note.cget("text")
    assert patches.wanted(30, "gr2", [], "16:10 1920x1200")[-1] == "16:10 1920x1200"


def test_aspect_ratio_keeps_the_size_step_and_shapes_the_window(app):
    from grport.settings import window
    app.settings.selected = "gr2"
    app.show("setup")
    page = app.pages["setup"]
    assert page.aspect_choice.value == "16:9" and page.render_choice.value == ""  # 1080p
    page.set_resolution("Resolution 2560x1440")
    page.set_aspect("16:10")
    assert app.settings.games["gr2"].resolution == "16:10 2560x1600"
    page.set_aspect("21:9")
    assert app.settings.games["gr2"].resolution == "Ultrawide 2.39:1 3440x1440"
    page.set_aspect("4:3")
    assert app.settings.games["gr2"].resolution == "GRport 4:3 1920x1440"
    page.set_window_mode("window")
    page.set_window_size("900p")
    assert page.size_choice.value == "900p"
    assert window(load_settings(app.paths), app.settings.games["gr2"]) == (1200, 900)
    # an older GRport's choice keeps working and is named
    page.set_resolution("GRport 5:4 1280x1024")
    assert page.aspect_choice.value == "4:3" and "1280x1024" in page.resolution_note.cget("text")


def test_picture_settings_write_that_games_grport_ini(app):
    from grport import ini
    app.settings.selected = "gr1"
    app.show("setup")
    page = app.pages["setup"]
    page.select_game("gr1")
    page.set_picture("upscaler", "off")
    page.set_picture("sharpness", "0.50")
    values = ini.read_ini(app.paths.root / "user" / "gr1" / "grport.ini")
    assert values["upscaler"] == "off" and values["sharpness"] == "0.50"
    assert page.picture_choices["upscaler"].value == "off"
    assert not (app.paths.root / "user" / "gr2" / "grport.ini").exists()


def test_setup_row_labels_fit(app):
    """Every row label is shown whole ('FSR 1 to the screen', 'Mute in background')."""
    import tkinter as tk
    app.show("setup")
    app.update()
    page = app.pages["setup"]
    labels = [w for w in page.inner.winfo_children()]
    stack, seen = list(labels), 0
    while stack:
        w = stack.pop()
        stack += w.winfo_children()
        if isinstance(w, tk.Label) and int(w.cget("width") or 0) > 0:
            text = w.cget("text")
            assert w.winfo_reqwidth() >= w.nametowidget(w).tk.call("font", "measure", w.cget("font"), text), text
            seen += 1
    assert seen >= 10


@pytest.mark.parametrize("cancel", [False, True])
def test_folder_chooser_has_readable_text_and_restores_theme(app, monkeypatch, cancel):
    from grport.ui import app as app_module, theme
    before = app.style.theme_use()
    foreground = app.style.lookup("TEntry", "foreground")
    def choose(**kwargs):
        assert app.style.theme_use() == "default"
        assert app.winfo_rgb(app.style.lookup("TEntry", "foreground")) == (0, 0, 0)
        assert kwargs["mustexist"] is True
        if cancel:
            return ""
        return app.settings.games["gr2"].folder
    monkeypatch.setattr(app_module.filedialog, "askdirectory", choose)
    assert app.choose_folder("gr2") is None
    assert app.style.theme_use() == before
    assert app.style.lookup("TEntry", "foreground") == foreground
    with pytest.raises(RuntimeError):
        with theme.file_dialog_theme(app.style):
            raise RuntimeError("dialog failed")
    assert app.style.theme_use() == before


def test_deck_preset_keeps_other_game_and_enables_intro_workaround(app):
    app.settings.selected = "gr2"
    before = app.settings.games["gr1"].resolution
    page = app.pages["setup"]
    page.apply_deck_preset()
    saved = load_settings(app.paths)
    assert saved.games["gr2"].resolution == "16:10 1280x800"
    assert saved.games["gr2"].fps == 30
    assert saved.games["gr2"].readbacks == "relaxed"
    assert not saved.games["gr2"].ps4_pro
    assert "Skip Intro" in saved.games["gr2"].extras
    assert saved.games["gr1"].resolution == before
    assert saved.window_mode == "borderless"
    page.apply_deck_preset()
    assert load_settings(app.paths).games["gr2"].extras.count("Skip Intro") == 1


def test_all_touchpad_regions_can_be_bound(app):
    page = app.pages["controls"]
    page.select_game("gr2")
    for action, key in (("touchpad_left", "t"), ("touchpad_center", "y"), ("touchpad_right", "u")):
        page.start_rebind(action)
        assert page.press_key(key)
    text = (app.paths.root / "user/gr2/input.ini").read_text()
    assert "touchpad_left = t" in text
    assert "touchpad_center = y" in text
    assert "touchpad_right = u" in text


def test_performance_deck_mode_reduces_render_and_uses_spatial_upscaler(app):
    from grport import ini, patches
    app.settings.selected = "gr2"
    page = app.pages["setup"]
    page.apply_deck_preset("performance")
    saved = load_settings(app.paths)
    assert saved.games["gr2"].resolution == "GRport 16:10 960x600"
    assert page.render_choice.value == "GRport 16:10 960x600"
    values = ini.read_ini(page._ini())
    assert values["upscaler"] == "fsr4" and values["fsr1"] == "0"
    assert saved.games["gr2"].temporal_output == "1280x800"
    assert "GRport 16:10 960x600" in patches.wanted(30, "gr2", [], saved.games["gr2"].resolution)
    page.set_aspect("16:9")
    assert app.settings.games["gr2"].resolution == "Resolution 1280x720"
    page.set_aspect("16:10")
    assert app.settings.games["gr2"].resolution == "16:10 1280x800"


def test_controller_speaker_setting_is_per_game_and_reaches_runtime(app):
    from grport import runtime
    app.settings.selected = "gr2"
    page = app.pages["setup"]
    page.set_pad_speaker(False)
    saved = load_settings(app.paths)
    assert not saved.games["gr2"].pad_speaker and saved.games["gr1"].pad_speaker
    assert runtime.env(app.paths, saved, app.infos["gr2"], base={})["BB_PAD_SPEAKER"] == "0"


def test_performance_logging_and_output_are_in_bug_report(app):
    from grport import runtime
    app.settings.selected = "gr2"
    page = app.pages["setup"]
    page.set_performance_log(True)
    page.set_temporal_output("1280x800")
    saved = load_settings(app.paths)
    env = runtime.env(app.paths, saved, app.infos["gr2"], base={})
    assert env["BB_GPU_PROFILE"] == "1" and env["BB_FRAME_STATS"] == "1"
    assert env["BB_GR_OUTPUT_RES"] == "1280x800"
    report = app.pages["log"].report_text()
    assert "CPU: " in report
    assert "Performance log: on" in report
    assert "Temporal output: 1280x800" in report


def test_hdr_output_is_opt_in_per_game_and_has_sdr_mapping_parameters(app):
    from grport import runtime
    app.settings.selected = "gr2"
    page = app.pages["setup"]
    assert not app.settings.games["gr2"].hdr_output
    page.set_hdr_output(True)
    page.set_hdr_white(300)
    saved = load_settings(app.paths)
    env = runtime.env(app.paths, saved, app.infos["gr2"], base={})
    assert env["BB_HDR"] == "1" and env["BB_SDR_HDR"] == "1"
    assert env["BB_HDR_PAPER_WHITE"] == "300"
    assert not saved.games["gr1"].hdr_output
