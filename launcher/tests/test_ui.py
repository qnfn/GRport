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
    assert set(app.pages) == {"play", "setup", "log"}
    for key in ("gr1", "gr2"):
        app.settings.selected = key
        for tab in ("play", "setup", "log"):
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
    saved = load_settings(app.paths)
    assert saved.window_mode == "window" and saved.window_size == "2560x1440"
    assert "Disable motion blur" not in saved.games["gr2"].extras
    assert saved.games["gr2"].readbacks == "relaxed" and saved.games["gr1"].readbacks == "off"


def test_play_refuses_without_the_runtime(app):
    assert "runtime is missing" in app.play("gr2")


def test_bug_report_names_the_runtime(app):
    text = app.pages["log"].report_text()
    assert text.startswith("GRport ") and "runtime" in text.splitlines()[0]
