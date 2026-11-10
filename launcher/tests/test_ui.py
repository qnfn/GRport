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
    assert set(app.pages) == {"play", "setup", "controls", "log"}
    for key in ("gr1", "gr2"):
        app.settings.selected = key
        for tab in ("play", "setup", "controls", "log"):
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
    assert page.resolution_box.text.startswith("1920x1200")
    assert patches.wanted(30, "gr2", [], "16:10 1920x1200")[-1] == "16:10 1920x1200"


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
